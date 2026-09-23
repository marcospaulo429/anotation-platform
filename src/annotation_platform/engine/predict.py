"""Predictor protocol + Ultralytics implementation.

Module-level imports are intentionally light (stdlib + contracts only) so that
tests and pure orchestration code can import the ``Predictor`` protocol without
pulling torch/ultralytics. Heavy deps (cv2, numpy, ultralytics via fly_det)
are imported lazily inside ``UltralyticsPredictor``.

Global rules enforced here:
- CPU forced by default (``device="cpu"``); GPU jobs exist only inside the
  Slurm container, never in this dev environment.
- ``cv2.setNumThreads(1)`` on load and per image (shared machine).
- One image at a time; the frame reference is released right after inference.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..contracts.pre_meta import PreBox
from ..contracts.project import PreannotationConfig


@runtime_checkable
class Predictor(Protocol):
    """Callable injected into the orchestrator: image path -> predicted boxes."""

    def __call__(self, image_path: Path) -> list[PreBox]: ...


def _detections_to_preboxes(detections: object, width: int, height: int) -> list[PreBox]:
    """Convert a supervision Detections (absolute xyxy) to normalized PreBox list."""
    import numpy as np

    if detections.is_empty():
        return []
    confidences = (
        detections.confidence
        if detections.confidence is not None
        else np.ones(len(detections), dtype=float)
    )
    boxes: list[PreBox] = []
    for (x1, y1, x2, y2), cls_id, conf in zip(
        detections.xyxy, detections.class_id, confidences, strict=True
    ):
        w = float(x2 - x1) / width
        h = float(y2 - y1) / height
        if w <= 0.0 or h <= 0.0:
            continue  # degenerate box, never emitted
        cx = float(x1 + x2) / 2.0 / width
        cy = float(y1 + y2) / 2.0 / height
        boxes.append(
            PreBox(
                cls=int(cls_id),
                cx=min(max(cx, 0.0), 1.0),
                cy=min(max(cy, 0.0), 1.0),
                w=min(w, 1.0),
                h=min(h, 1.0),
                conf=float(conf),
            )
        )
    return boxes


class UltralyticsPredictor:
    """Real predictor: Ultralytics YOLO, plain or SAHI-sliced (reuses fly_det helpers).

    The checkpoint is loaded lazily exactly once, on the first call.
    """

    def __init__(
        self,
        checkpoint: str | Path,
        *,
        engine: str = "sahi",
        imgsz: int = 1920,
        conf: float = 0.25,
        iou: float = 0.7,
        slice_size: int = 640,
        slice_overlap: float = 0.2,
        device: str = "cpu",
    ) -> None:
        if engine not in ("sahi", "plain"):
            raise ValueError(f"unknown engine {engine!r}: expected 'sahi' or 'plain'")
        self.checkpoint = Path(checkpoint)
        self.engine = engine
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.slice_size = slice_size
        self.slice_overlap = slice_overlap
        self.device = device
        self._model: object | None = None
        self._slicer: object | None = None
        self._run_plain: object | None = None

    @classmethod
    def from_config(cls, cfg: PreannotationConfig, *, device: str = "cpu") -> UltralyticsPredictor:
        """Build from the preannotation section of project.yaml. CPU forced by default."""
        if not cfg.checkpoint:
            raise ValueError("preannotation.checkpoint is not set in project.yaml")
        return cls(
            cfg.checkpoint,
            engine=cfg.engine,
            imgsz=cfg.imgsz,
            conf=cfg.conf_threshold,
            iou=cfg.iou_threshold,
            slice_size=cfg.slice.size,
            slice_overlap=cfg.slice.overlap,
            device=device,
        )

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        import cv2

        cv2.setNumThreads(1)
        from fly_det.utils.sahi_helper import make_slicer, run_plain
        from fly_det.utils.yolo_utils import load_model

        model = load_model(str(self.checkpoint), self.device)
        self._model = model
        self._run_plain = run_plain
        if self.engine == "sahi":
            overlap_px = int(self.slice_size * self.slice_overlap)
            self._slicer = make_slicer(
                model,
                (self.slice_size, self.slice_size),
                (overlap_px, overlap_px),
                1,  # thread workers: 1 (shared machine / GPU-safest)
                self.device,
                self.conf,
                self.iou,
                self.imgsz,
                "NON_MAX_SUPPRESSION",
                0.5,  # cross-tile NMS IoU (fly_det default)
            )

    def __call__(self, image_path: Path) -> list[PreBox]:
        self._ensure_loaded()
        import cv2

        cv2.setNumThreads(1)
        image_path = Path(image_path)
        img = cv2.imread(str(image_path))
        if img is None:
            raise ValueError(f"could not read image: {image_path}")
        try:
            height, width = img.shape[:2]
            if self.engine == "sahi":
                detections = self._slicer(img)
            else:
                detections = self._run_plain(
                    self._model, img, self.device, self.conf, self.iou, self.imgsz
                )
        finally:
            del img  # one image at a time: release the frame immediately
        return _detections_to_preboxes(detections, width, height)
