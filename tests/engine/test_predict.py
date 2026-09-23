"""Predictor adapters must not depend on a sibling fly-det checkout."""

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from annotation_platform.engine.predict import UltralyticsPredictor


@pytest.mark.parametrize("engine,max_det", [("plain", 600), ("sahi", 1000)])
def test_predictor_uses_public_libraries(monkeypatch, engine, max_det):
    detections = SimpleNamespace(
        is_empty=lambda: False,
        xyxy=np.array([[10, 20, 30, 60]]),
        class_id=np.array([1]),
        confidence=np.array([0.8]),
    )
    model = Mock()
    model.predict.return_value = [object()]
    model_factory = Mock(return_value=model)
    slicer_factory = Mock(side_effect=lambda **kwargs: kwargs["callback"])
    cv2 = SimpleNamespace(setNumThreads=Mock(), imread=Mock(return_value=np.zeros((100, 200, 3))))
    monkeypatch.setitem(sys.modules, "fly_det", None)
    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=model_factory))
    monkeypatch.setitem(
        sys.modules,
        "supervision",
        SimpleNamespace(
            Detections=SimpleNamespace(from_ultralytics=lambda result: detections),
            InferenceSlicer=slicer_factory,
            OverlapFilter=SimpleNamespace(NON_MAX_SUPPRESSION="nms"),
        ),
    )
    predictor = UltralyticsPredictor("trusted.pt", engine=engine)
    boxes = predictor("frame.jpg")
    predictor("frame.jpg")
    model_factory.assert_called_once_with("trusted.pt")
    model.to.assert_called_once_with("cpu")
    assert boxes[0].cls == 1
    assert (boxes[0].cx, boxes[0].cy, boxes[0].w, boxes[0].h) == (0.1, 0.4, 0.1, 0.4)
    assert model.predict.call_args.kwargs == {
        "verbose": False,
        "conf": 0.25,
        "iou": 0.7,
        "imgsz": 1920,
        "device": "cpu",
        "max_det": max_det,
    }
    cv2.setNumThreads.assert_called_with(1)
    if engine == "sahi":
        params = slicer_factory.call_args.kwargs
        assert params["slice_wh"] == (640, 640)
        assert params["overlap_wh"] == (128, 128)
        assert params["thread_workers"] == 1
        assert params["iou_threshold"] == 0.5
        assert params["overlap_filter"] == "nms"
