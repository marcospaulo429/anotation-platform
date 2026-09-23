// STUB de desenvolvimento para a interface CONGELADA do canvas.
// NÃO é o canvas real (dono: subagente anno-web-canvas). É um div colorido
// que desenha caixas como divs absolutas e loga todas as chamadas — serve
// para desenvolver o app shell sem o módulo ../canvas/anno-canvas.js.
//
// Interface consumida pelo shell:
//   createAnnoCanvas(container, options) => handle
//   options: { imageWidth, imageHeight, classes, tilesUrl(x,y), tileSize,
//              boxes, onChange(boxes, op), onClassRequest(), initialTilesSeen }
//   handle: { getBoxes(), getTilesSeen(), setClasses(), setBoxes(), undo(),
//             redo(), setMode("pan"|"draw"), destroy() }
// Box = { id, cls, cx, cy, w, h, origin, model_conf?, edited, edit_ops: [] }

const log = (...a) => console.info("[canvas-stub]", ...a);
const uid = () => crypto.randomUUID();

export function createAnnoCanvas(container, options) {
  log("createAnnoCanvas", options);
  let boxes = structuredClone(options.boxes ?? []);
  let classes = options.classes ?? [];
  let tilesSeen = [...(options.initialTilesSeen ?? [])];
  let mode = "pan";
  const undoStack = [];
  const redoStack = [];

  const stage = document.createElement("div");
  stage.className = "canvas-stub-stage";
  stage.style.cssText =
    "position:relative;width:100%;height:100%;min-height:420px;" +
    "background:repeating-conic-gradient(#2b2f36 0% 25%, #23272e 0% 50%) 0 0/48px 48px;" +
    "overflow:auto;cursor:crosshair;";
  container.append(stage);

  function color(i) {
    const C = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4"];
    return C[i % C.length];
  }

  function emit(op) {
    options.onChange?.(structuredClone(boxes), op);
    render();
  }

  function pushUndo() {
    undoStack.push(structuredClone(boxes));
    redoStack.length = 0;
  }

  function render() {
    stage.querySelectorAll(".canvas-stub-box").forEach((n) => n.remove());
    for (const b of boxes) {
      const d = document.createElement("div");
      d.className = "canvas-stub-box";
      d.style.cssText =
        `position:absolute;border:2px solid ${color(b.cls)};box-sizing:border-box;` +
        `left:${(b.cx - b.w / 2) * 100}%;top:${(b.cy - b.h / 2) * 100}%;` +
        `width:${b.w * 100}%;height:${b.h * 100}%;` +
        `background:${color(b.cls)}22;`;
      d.title = `${classes[b.cls] ?? b.cls} (${b.origin})`;
      d.onclick = (e) => {
        // Clicar na caixa do modelo = aceita (snap de pré-anotação).
        e.stopPropagation();
        if (b.origin === "model" && !b.edited) {
          pushUndo();
          b.edited = true;
          b.edit_ops.push("accept");
          emit({ op: "accept", box: b.id });
        }
      };
      stage.append(d);
    }
  }

  stage.onclick = (e) => {
    if (mode !== "draw") return;
    // Clique no modo draw cria uma caixa humana de tamanho fixo (~40 px).
    const r = stage.getBoundingClientRect();
    pushUndo();
    const box = {
      id: uid(),
      cls: 0,
      cx: (e.clientX - r.left) / r.width,
      cy: (e.clientY - r.top) / r.height,
      w: 40 / options.imageWidth,
      h: 40 / options.imageHeight,
      origin: "human",
      edited: true,
      edit_ops: ["create"],
    };
    boxes.push(box);
    emit({ op: "create", box: box.id });
  };

  render();
  if (tilesSeen.length === 0) tilesSeen = [0]; // stub: finge ter visto o tile 0

  const handle = {
    getBoxes: () => structuredClone(boxes),
    getTilesSeen: () => [...tilesSeen],
    setClasses(next) { log("setClasses", next); if (next) classes = next; render(); },
    setBoxes(next) { log("setBoxes", next); boxes = structuredClone(next ?? []); render(); },
    undo() {
      log("undo");
      if (!undoStack.length) return;
      redoStack.push(structuredClone(boxes));
      boxes = undoStack.pop();
      emit({ op: "undo" });
    },
    redo() {
      log("redo");
      if (!redoStack.length) return;
      undoStack.push(structuredClone(boxes));
      boxes = redoStack.pop();
      emit({ op: "redo" });
    },
    setMode(m) { log("setMode", m); mode = m; stage.style.cursor = m === "draw" ? "crosshair" : "grab"; },
    destroy() { log("destroy"); stage.remove(); },
  };
  log("handle criado com", boxes.length, "caixas");
  return handle;
}
