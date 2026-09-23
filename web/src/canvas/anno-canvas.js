/**
 * anno-canvas.js — Canvas de anotação de bounding boxes (ES module, sem build step).
 *
 * Depende do Konva UMD global (`window.Konva`), carregado antes via
 * <script src="../../vendor/konva.min.js"></script>.
 *
 * O canvas é BURRO sobre rede: não faz fetch. Recebe dados e emite eventos
 * (onChange / onClassRequest). O shell cuida de API, autosave e navegação.
 *
 * Modelo de dados: coordenadas SEMPRE normalizadas [0,1] (formato YOLO cx,cy,w,h).
 * Conversão para pixels nativos só na renderização.
 *
 * Atalhos (seção 8 do PREANNOTATION_PLATFORM.md):
 *   1-9  relabel da caixa selecionada (e define a classe corrente)
 *   W    alterna modo desenho
 *   L    lupa 3x no cursor
 *   C    crosshair
 *   N    pede nova classe ao shell (onClassRequest)
 *   Enter  marca tile atual como visto e avança (modo varredura)
 *   Del/Backspace  apaga caixa selecionada
 *   Ctrl+Z / Ctrl+Y (ou Ctrl+Shift+Z)  undo / redo
 *   Esc  volta ao modo mover e deseleciona
 *   scroll = pan, ctrl+scroll = zoom
 */

const Konva = window.Konva;
if (!Konva) {
  throw new Error('anno-canvas: Konva não encontrado. Carregue web/vendor/konva.min.js antes.');
}

// Ângulo áureo → cores determinísticas e bem separadas por índice de classe.
const HUE_STEP = 137.508;
function classColor(i) {
  return `hsl(${Math.round((i * HUE_STEP) % 360)}, 75%, 55%)`;
}

function uuid() {
  return (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : 'id-' + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

const clone = (b) => JSON.parse(JSON.stringify(b));
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));

// Uma caixa do modelo é "não aceita" (tracejada) enquanto 'accept' não está em edit_ops.
function isPending(b) {
  return b.origin === 'model' && !(b.edit_ops || []).includes('accept');
}

let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const st = document.createElement('style');
  st.textContent = `
.anno-canvas-host { position: relative; overflow: hidden; background: #14161b; }
.anno-canvas-host.anno-mode-draw { cursor: crosshair; }
.anno-canvas-host.anno-mode-pan { cursor: grab; }
.anno-canvas-host.anno-panning { cursor: grabbing; }
.anno-overlay { position: absolute; inset: 0; pointer-events: none; z-index: 10; }
.anno-hud {
  position: absolute; left: 8px; bottom: 8px; z-index: 11;
  background: rgba(0,0,0,.62); color: #e8e8e8; font: 12px/1.5 monospace;
  padding: 4px 10px; border-radius: 6px; pointer-events: none; white-space: pre;
}`;
  document.head.appendChild(st);
}

/**
 * Cria o canvas de anotação dentro de `container` (um <div> com tamanho definido).
 * @returns handle com getBoxes/getTilesSeen/setClasses/setBoxes/undo/redo/setMode/destroy
 */
export function createAnnoCanvas(container, options) {
  injectStyles();
  const {
    imageWidth, imageHeight,
    tilesUrl,
    tileSize = 640,
    onChange = () => {},
    onClassRequest = () => {},
    initialTilesSeen = [],
  } = options;
  if (!imageWidth || !imageHeight || typeof tilesUrl !== 'function') {
    throw new Error('anno-canvas: options precisa de imageWidth, imageHeight e tilesUrl(x,y).');
  }

  let classes = (options.classes || []).slice();
  let boxes = (options.boxes || []).map(clone);

  // ---------------------------------------------------------------- grade de tiles
  const cols = Math.ceil(imageWidth / tileSize);
  const rows = Math.ceil(imageHeight / tileSize);
  const nTiles = cols * rows;
  const tilesSeen = new Set(initialTilesSeen || []);

  // ---------------------------------------------------------------- estrutura Konva
  container.classList.add('anno-canvas-host', 'anno-mode-pan');
  const rect0 = container.getBoundingClientRect();
  const stage = new Konva.Stage({
    container,
    width: Math.max(100, rect0.width || 800),
    height: Math.max(100, rect0.height || 600),
    draggable: false, // pan é manual (arrastar espaço vazio) — evita conflito com Transformer
  });
  const tileLayer = new Konva.Layer();          // imagem (tiles nativos)
  const seenLayer = new Konva.Layer({ listening: false }); // overlay da varredura
  const boxLayer = new Konva.Layer();           // caixas + transformer
  stage.add(tileLayer, seenLayer, boxLayer);

  // Overlay HTML (fora do Konva) para crosshair e lupa, em coordenadas de tela.
  const overlay = document.createElement('canvas');
  overlay.className = 'anno-overlay';
  container.appendChild(overlay);
  const octx = overlay.getContext('2d');

  const hud = document.createElement('div');
  hud.className = 'anno-hud';
  container.appendChild(hud);

  // ---------------------------------------------------------------- estado da UI
  let mode = 'pan';                 // 'pan' | 'draw'
  let currentCls = 0;               // classe corrente (usada ao desenhar)
  let selectedId = null;
  let loupeOn = false;
  let crossOn = false;
  let scanOn = false;               // varredura por tiles é opt-in (tecla T)
  let mouse = null;                 // posição do cursor em px de tela (stage)
  let panning = false;
  let panLast = null;
  let drawStart = null;             // ponto inicial do desenho (coords da imagem)
  let drawRect = null;              // rect temporário do Konva durante o desenho

  const undoStack = [];
  const redoStack = [];

  // ---------------------------------------------------------------- helpers de view
  const scale = () => stage.scaleX();
  function screenToImage(p) {
    const s = scale();
    return { x: (p.x - stage.x()) / s, y: (p.y - stage.y()) / s };
  }
  function fitScale() {
    return Math.min(stage.width() / imageWidth, stage.height() / imageHeight);
  }
  function applyView() {
    loadVisibleTiles();
    updateZoomDependents();
    updateScanHighlight();
    updateHud();
    drawOverlay();
    stage.batchDraw();
  }

  // ---------------------------------------------------------------- tiles (imagem)
  // Cache: "x,y" -> { img, node } | null (carregando)
  const tileCache = new Map();
  function tileW(x) { return Math.min(tileSize, imageWidth - x * tileSize); }
  function tileH(y) { return Math.min(tileSize, imageHeight - y * tileSize); }

  function ensureTile(x, y) {
    if (x < 0 || y < 0 || x >= cols || y >= rows) return;
    const key = x + ',' + y;
    if (tileCache.has(key)) return;
    tileCache.set(key, null);
    const img = new Image();
    img.onload = () => {
      const node = new Konva.Image({
        image: img, x: x * tileSize, y: y * tileSize,
        width: tileW(x), height: tileH(y),
      });
      tileCache.set(key, { img, node });
      tileLayer.add(node);
      tileLayer.batchDraw();
      drawOverlay(); // a lupa usa os tiles já carregados
    };
    img.onerror = () => tileCache.delete(key); // permite retry
    img.src = tilesUrl(x, y);
  }

  function loadVisibleTiles() {
    const s = scale();
    const x0 = clamp(Math.floor((-stage.x() / s) / tileSize) - 1, 0, cols - 1);
    const y0 = clamp(Math.floor((-stage.y() / s) / tileSize) - 1, 0, rows - 1);
    const x1 = clamp(Math.floor(((stage.width() - stage.x()) / s) / tileSize) + 1, 0, cols - 1);
    const y1 = clamp(Math.floor(((stage.height() - stage.y()) / s) / tileSize) + 1, 0, rows - 1);
    for (let y = y0; y <= y1; y++) for (let x = x0; x <= x1; x++) ensureTile(x, y);
  }

  // ---------------------------------------------------------------- varredura (tiles_seen)
  let currentTileMarker = null;
  function tileIndexAtImagePoint(p) {
    const tx = clamp(Math.floor(p.x / tileSize), 0, cols - 1);
    const ty = clamp(Math.floor(p.y / tileSize), 0, rows - 1);
    return ty * cols + tx;
  }
  function currentTileIndex() {
    return tileIndexAtImagePoint(screenToImage({
      x: stage.width() / 2, y: stage.height() / 2,
    }));
  }
  function goToTile(i) {
    i = clamp(i, 0, nTiles - 1);
    const tx = i % cols, ty = Math.floor(i / cols);
    // tile preenche a viewport (sem encolher além da resolução de trabalho)
    const s = clamp(Math.min(stage.width() / tileW(tx), stage.height() / tileH(ty)), 0.05, 4);
    stage.scale({ x: s, y: s });
    stage.position({
      x: stage.width() / 2 - (tx * tileSize + tileW(tx) / 2) * s,
      y: stage.height() / 2 - (ty * tileSize + tileH(ty) / 2) * s,
    });
    applyView();
  }
  function renderSeen() {
    seenLayer.destroyChildren();
    currentTileMarker = null;
    if (!scanOn) { seenLayer.batchDraw(); return; } // varredura é opt-in (tecla T)
    for (const i of tilesSeen) {
      const tx = i % cols, ty = Math.floor(i / cols);
      seenLayer.add(new Konva.Rect({
        x: tx * tileSize, y: ty * tileSize, width: tileW(tx), height: tileH(ty),
        fill: 'rgba(30,180,90,0.10)',
        stroke: 'rgba(40,220,110,0.55)', strokeWidth: 3, strokeScaleEnabled: false,
        name: 'seen-tile', listening: false,
      }));
      const check = new Konva.Text({
        x: tx * tileSize + 4, y: ty * tileSize + 2, text: '✓',
        fontSize: 28, fontStyle: 'bold', fill: 'rgba(40,220,110,0.9)',
        name: 'seen-check', listening: false,
      });
      seenLayer.add(check);
    }
    currentTileMarker = new Konva.Rect({
      stroke: 'rgba(255,210,60,0.95)', strokeWidth: 3, strokeScaleEnabled: false,
      listening: false, name: 'current-tile',
    });
    seenLayer.add(currentTileMarker);
    updateScanHighlight();
  }
  function setScanMode(on) {
    scanOn = !!on;
    renderSeen();
    updateHud();
    if (scanOn) goToTile(currentTileIndex()); // enquadra o tile atual
  }
  function updateScanHighlight() {
    if (!currentTileMarker) return;
    const i = currentTileIndex();
    const tx = i % cols, ty = Math.floor(i / cols);
    currentTileMarker.setAttrs({ x: tx * tileSize, y: ty * tileSize, width: tileW(tx), height: tileH(ty) });
    // checkmarks com tamanho constante em tela
    seenLayer.find('.seen-check').forEach((c) => c.scale({ x: 1 / scale(), y: 1 / scale() }));
    seenLayer.batchDraw();
  }
  function markSeenAndAdvance() {
    const cur = currentTileIndex();
    tilesSeen.add(cur);
    renderSeen();
    updateHud();
    for (let k = 1; k <= nTiles; k++) {
      const nxt = (cur + k) % nTiles;
      if (!tilesSeen.has(nxt)) { goToTile(nxt); return; }
    }
    updateHud(); // todos vistos
  }

  // ---------------------------------------------------------------- caixas
  const groupById = new Map(); // id -> Konva.Group
  const tr = new Konva.Transformer({
    rotateEnabled: false, flipEnabled: false,
    enabledAnchors: ['top-left', 'top-right', 'bottom-left', 'bottom-right'],
    anchorSize: 9, anchorCornerRadius: 2,
    anchorStroke: '#fff', borderStroke: 'rgba(255,255,255,0.9)',
    boundBoxFunc(oldBox, newBox) {
      const minPx = 4 * scale(); // mínimo 4 px nativos
      if (newBox.width < minPx || newBox.height < minPx) return oldBox;
      return newBox;
    },
  });
  boxLayer.add(tr);

  function boxById(id) { return boxes.find((b) => b.id === id); }

  function renderBoxes() {
    tr.nodes([]);
    groupById.clear();
    boxLayer.find('.box').forEach((g) => g.destroy());
    for (const b of boxes) groupById.set(b.id, buildBoxNode(b));
    if (selectedId) {
      const g = groupById.get(selectedId);
      if (g) tr.nodes([g.findOne('.box-rect')]);
      else selectedId = null;
    }
    updateZoomDependents();
    boxLayer.batchDraw();
  }

  function buildBoxNode(b) {
    const color = classColor(b.cls);
    const px = (b.cx - b.w / 2) * imageWidth;
    const py = (b.cy - b.h / 2) * imageHeight;
    const pw = b.w * imageWidth;
    const ph = b.h * imageHeight;

    const g = new Konva.Group({
      name: 'box', id: b.id, x: px, y: py, draggable: true,
      dragBoundFunc(pos) {
        // pos é a posição absoluta (tela) proposta para a origem do grupo
        const s = scale();
        let ix = (pos.x - stage.x()) / s;
        let iy = (pos.y - stage.y()) / s;
        ix = clamp(ix, 0, imageWidth - pw);
        iy = clamp(iy, 0, imageHeight - ph);
        return { x: ix * s + stage.x(), y: iy * s + stage.y() };
      },
    });

    const r = new Konva.Rect({
      name: 'box-rect', width: pw, height: ph,
      stroke: color, strokeWidth: 2.5, strokeScaleEnabled: false,
      dash: isPending(b) ? [8, 5] : undefined,
      dashEnabled: isPending(b),
    });
    g.add(r);

    // rótulo (classe + conf do modelo); escala invertida do zoom p/ tamanho fixo em tela
    const label = (classes[b.cls] ?? String(b.cls)) +
      (b.origin === 'model' && b.model_conf != null ? ` ${(b.model_conf * 100).toFixed(0)}%` : '');
    const tag = new Konva.Group({ name: 'box-tag', listening: false });
    const txt = new Konva.Text({ text: label, fontSize: 12, fontStyle: 'bold', fill: '#fff', padding: 3 });
    const bg = new Konva.Rect({ width: txt.width(), height: txt.height(), fill: color, cornerRadius: 2, opacity: 0.9 });
    tag.add(bg, txt);
    tag.y(py < 30 ? 0 : -txt.height()); // perto da borda superior → rótulo dentro da caixa
    g.add(tag);

    g.on('click tap', (e) => {
      e.cancelBubble = true;
      const bb = boxById(b.id);
      if (!bb) return;
      if (isPending(bb)) acceptBox(bb); // clicar na tracejada = aceitar
      selectBox(b.id);
    });
    g.on('dragend', () => commitMove(b.id, g));
    r.on('transformend', () => commitResize(b.id, g, r));

    boxLayer.add(g);
    return g;
  }

  function updateZoomDependents() {
    const s = scale();
    groupById.forEach((g) => {
      const tag = g.findOne('.box-tag');
      if (tag) tag.scale({ x: 1 / s, y: 1 / s });
      const r = g.findOne('.box-rect');
      if (r && r.dashEnabled()) r.dash([8 / s * 0.999, 5 / s]); // dash constante em tela
    });
  }

  function selectBox(id) {
    selectedId = id;
    const g = id ? groupById.get(id) : null;
    tr.nodes(g ? [g.findOne('.box-rect')] : []);
    const bb = id ? boxById(id) : null;
    if (bb) currentCls = bb.cls;
    updateHud();
    boxLayer.batchDraw();
  }

  // ---- leitura do estado Konva → modelo normalizado
  function nodeToBox(g) {
    const r = g.findOne('.box-rect');
    const px = g.x() + r.x(); // r.x() é 0 fora do transform
    const py = g.y() + r.y();
    const pw = r.width() * r.scaleX();
    const ph = r.height() * r.scaleY();
    return {
      cx: clamp((px + pw / 2) / imageWidth, 0, 1),
      cy: clamp((py + ph / 2) / imageHeight, 0, 1),
      w: clamp(pw / imageWidth, 0, 1),
      h: clamp(ph / imageHeight, 0, 1),
    };
  }

  // ---------------------------------------------------------------- operações (com undo + onChange)
  function record(entry) { // {op, box_id, before, after, index?}
    undoStack.push(entry);
    redoStack.length = 0;
  }
  function emit(op, boxId) {
    onChange(getBoxes(), { op, box_id: boxId });
  }
  function touchBox(b, op) {
    b.edited = true;
    b.edit_ops = b.edit_ops || [];
    b.edit_ops.push(op);
  }

  function acceptBox(b) {
    if (!isPending(b)) return;
    const before = clone(b);
    b.edit_ops = b.edit_ops || [];
    b.edit_ops.push('accept'); // edited mantém (regra da seção 8)
    record({ op: 'accept', box_id: b.id, before, after: clone(b) });
    refresh();
    emit('accept', b.id);
  }

  function commitMove(id, g) {
    const b = boxById(id);
    if (!b) return;
    const before = clone(b);
    const geo = nodeToBox(g);
    if (Math.abs(geo.cx - b.cx) < 1e-6 && Math.abs(geo.cy - b.cy) < 1e-6) return; // só clique
    Object.assign(b, geo);
    touchBox(b, 'move');
    record({ op: 'move', box_id: id, before, after: clone(b) });
    refresh();
    emit('move', id);
  }

  function commitResize(id, g, r) {
    const b = boxById(id);
    if (!b) return;
    const before = clone(b);
    // consolida scale/offset do transformer no tamanho do rect
    const newW = Math.max(4, r.width() * r.scaleX());
    const newH = Math.max(4, r.height() * r.scaleY());
    g.x(clamp(g.x() + r.x(), 0, imageWidth - newW));
    g.y(clamp(g.y() + r.y(), 0, imageHeight - newH));
    r.position({ x: 0, y: 0 });
    r.size({ width: newW, height: newH });
    r.scale({ x: 1, y: 1 });
    Object.assign(b, nodeToBox(g));
    touchBox(b, 'resize');
    record({ op: 'resize', box_id: id, before, after: clone(b) });
    refresh();
    emit('resize', id);
  }

  function relabelSelected(idx) {
    if (idx >= classes.length) return;
    currentCls = idx;
    const b = selectedId ? boxById(selectedId) : null;
    if (!b || b.cls === idx) { updateHud(); return; }
    const before = clone(b);
    b.cls = idx;
    touchBox(b, 'relabel');
    record({ op: 'relabel', box_id: b.id, before, after: clone(b) });
    refresh();
    emit('relabel', b.id);
  }

  function deleteSelected() {
    const b = selectedId ? boxById(selectedId) : null;
    if (!b) return;
    const index = boxes.indexOf(b);
    boxes.splice(index, 1);
    record({ op: 'delete', box_id: b.id, before: clone(b), after: null, index });
    selectedId = null;
    refresh();
    emit('delete', b.id);
  }

  function createBox(px, py, pw, ph) {
    const b = {
      id: uuid(),
      cls: currentCls,
      cx: clamp((px + pw / 2) / imageWidth, 0, 1),
      cy: clamp((py + ph / 2) / imageHeight, 0, 1),
      w: clamp(pw / imageWidth, 0, 1),
      h: clamp(ph / imageHeight, 0, 1),
      origin: 'human',
      edited: true,
      edit_ops: ['create'],
    };
    boxes.push(b);
    record({ op: 'create', box_id: b.id, before: null, after: clone(b) });
    refresh();
    selectBox(b.id);
    emit('create', b.id);
  }

  // ---------------------------------------------------------------- undo / redo
  function applyEntry(e, dir) { // dir: -1 undo, +1 redo
    const snap = dir < 0 ? e.before : e.after;
    if (e.op === 'create') {
      if (dir < 0) boxes = boxes.filter((b) => b.id !== e.box_id);
      else boxes.push(clone(e.after));
    } else if (e.op === 'delete') {
      if (dir < 0) boxes.splice(Math.min(e.index ?? boxes.length, boxes.length), 0, clone(e.before));
      else boxes = boxes.filter((b) => b.id !== e.box_id);
    } else {
      const b = boxById(e.box_id);
      if (b && snap) Object.assign(b, clone(snap));
    }
    if (!boxById(e.box_id)) selectedId = null;
  }
  function undo() {
    const e = undoStack.pop();
    if (!e) return;
    applyEntry(e, -1);
    redoStack.push(e);
    refresh();
    emit('undo', e.box_id);
  }
  function redo() {
    const e = redoStack.pop();
    if (!e) return;
    applyEntry(e, +1);
    undoStack.push(e);
    refresh();
    emit('redo', e.box_id);
  }

  function refresh() {
    renderBoxes();
    updateHud();
    drawOverlay();
  }

  // ---------------------------------------------------------------- interação: pan, zoom, desenho
  function isEmptyTarget(t) {
    return t === stage || t.getLayer() === tileLayer;
  }

  stage.on('mousedown', (e) => {
    if (e.evt.button !== 0) return;
    mouse = stage.getPointerPosition();
    if (mode === 'pan' && isEmptyTarget(e.target)) {
      selectBox(null); // clique no vazio deseleciona
      panning = true;
      panLast = mouse;
      container.classList.add('anno-panning');
    } else if (mode === 'draw' && isEmptyTarget(e.target)) {
      drawStart = screenToImage(mouse);
      drawRect = new Konva.Rect({
        x: drawStart.x, y: drawStart.y, width: 0, height: 0,
        stroke: classColor(currentCls), strokeWidth: 2,
        strokeScaleEnabled: false, dash: [6, 4], listening: false,
      });
      boxLayer.add(drawRect);
      boxLayer.batchDraw();
    }
  });

  function onWinMouseMove(e) {
    const p = stage.getPointerPosition();
    if (!p) return;
    mouse = p;
    if (panning && panLast) {
      stage.x(stage.x() + p.x - panLast.x);
      stage.y(stage.y() + p.y - panLast.y);
      panLast = p; // BUGFIX: sem isso o delta acumulava a cada evento (pan fugia)
      applyView();
    } else if (drawStart && drawRect) {
      const cur = screenToImage(p);
      cur.x = clamp(cur.x, 0, imageWidth);
      cur.y = clamp(cur.y, 0, imageHeight);
      drawRect.setAttrs({
        x: Math.min(drawStart.x, cur.x), y: Math.min(drawStart.y, cur.y),
        width: Math.abs(cur.x - drawStart.x), height: Math.abs(cur.y - drawStart.y),
      });
      boxLayer.batchDraw();
    }
    drawOverlay();
  }

  function onWinMouseUp() {
    if (panning) {
      panning = false;
      container.classList.remove('anno-panning');
    }
    if (drawStart && drawRect) {
      const w = drawRect.width(), h = drawRect.height();
      const x = drawRect.x(), y = drawRect.y();
      drawRect.destroy();
      drawRect = null;
      drawStart = null;
      boxLayer.batchDraw();
      if (w >= 4 && h >= 4) createBox(x, y, w, h); // ignora cliques acidentais
    }
  }

  stage.on('wheel', (e) => {
    e.evt.preventDefault();
    if (e.evt.ctrlKey || e.evt.metaKey) {
      // zoom centrado no cursor
      const old = scale();
      const ptr = stage.getPointerPosition();
      const imgPt = { x: (ptr.x - stage.x()) / old, y: (ptr.y - stage.y()) / old };
      const next = clamp(e.evt.deltaY < 0 ? old * 1.12 : old / 1.12, fitScale() * 0.4, 12);
      stage.scale({ x: next, y: next });
      stage.position({ x: ptr.x - imgPt.x * next, y: ptr.y - imgPt.y * next });
    } else {
      // scroll simples = pan (normalizado: deltaMode 1 = linhas; cap p/ não pular longe)
      const unit = e.evt.deltaMode === 1 ? 16 : 1;
      const dx = clamp(e.evt.deltaX * unit, -48, 48);
      const dy = clamp(e.evt.deltaY * unit, -48, 48);
      stage.x(stage.x() - dx);
      stage.y(stage.y() - dy);
    }
    applyView();
  });

  stage.on('mouseleave', () => { mouse = null; drawOverlay(); });

  // ---------------------------------------------------------------- teclado
  function onKey(e) {
    const tag = e.target && e.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) return;

    if (e.ctrlKey || e.metaKey) {
      const k = e.key.toLowerCase();
      if (k === 'z') { e.preventDefault(); e.shiftKey ? redo() : undo(); }
      else if (k === 'y') { e.preventDefault(); redo(); }
      return;
    }
    switch (e.key) {
      case 'h': case 'H': setMode('pan'); break;          // mão
      case 'b': case 'B': setMode('draw'); break;         // bounding box
      case 'w': case 'W': setMode(mode === 'draw' ? 'pan' : 'draw'); break;
      case 't': case 'T': setScanMode(!scanOn); break;    // varredura por tiles
      case 'l': case 'L': loupeOn = !loupeOn; drawOverlay(); updateHud(); break;
      case 'c': case 'C': crossOn = !crossOn; drawOverlay(); updateHud(); break;
      case 'n': case 'N': onClassRequest(); break;
      case 'Enter': if (scanOn) { e.preventDefault(); markSeenAndAdvance(); } break;
      case 'Delete': case 'Backspace': e.preventDefault(); deleteSelected(); break;
      case 'Escape': setMode('pan'); selectBox(null); break;
      default:
        if (/^[1-9]$/.test(e.key)) relabelSelected(parseInt(e.key, 10) - 1);
    }
  }

  // ---------------------------------------------------------------- overlay: crosshair + lupa
  function drawOverlay() {
    const w = stage.width(), h = stage.height();
    if (overlay.width !== w) overlay.width = w;
    if (overlay.height !== h) overlay.height = h;
    octx.clearRect(0, 0, w, h);
    if (!mouse || (!crossOn && !loupeOn)) return;

    if (crossOn) {
      octx.strokeStyle = 'rgba(255,255,255,0.45)';
      octx.lineWidth = 1;
      octx.beginPath();
      octx.moveTo(0, mouse.y + 0.5); octx.lineTo(w, mouse.y + 0.5);
      octx.moveTo(mouse.x + 0.5, 0); octx.lineTo(mouse.x + 0.5, h);
      octx.stroke();
    }
    if (loupeOn) drawLoupe();
  }

  // Lupa: círculo de raio 120 amplia 3× a região do cursor (precisão de 1–2 px nos cantos).
  function drawLoupe() {
    const R = 120, Z = 3;
    const s = scale();
    const imgPt = screenToImage(mouse);
    const k = Z * s;          // px da lupa por px nativo da imagem
    const srcR = R / k;       // raio da região nativa amostrada
    // círculo deslocado do cursor para não tapar o ponto de trabalho
    const cx = clamp(mouse.x + R + 32, R + 6, stage.width() - R - 6);
    const cy = clamp(mouse.y + R + 32, R + 6, stage.height() - R - 6);

    octx.save();
    octx.beginPath();
    octx.arc(cx, cy, R, 0, Math.PI * 2);
    octx.clip();
    octx.fillStyle = '#101216';
    octx.fillRect(cx - R, cy - R, 2 * R, 2 * R);

    // tiles que intersectam a região amostrada
    const tx0 = clamp(Math.floor((imgPt.x - srcR) / tileSize), 0, cols - 1);
    const tx1 = clamp(Math.floor((imgPt.x + srcR) / tileSize), 0, cols - 1);
    const ty0 = clamp(Math.floor((imgPt.y - srcR) / tileSize), 0, rows - 1);
    const ty1 = clamp(Math.floor((imgPt.y + srcR) / tileSize), 0, rows - 1);
    for (let ty = ty0; ty <= ty1; ty++) {
      for (let tx = tx0; tx <= tx1; tx++) {
        const t = tileCache.get(tx + ',' + ty);
        if (!t || !t.img) continue;
        const ix0 = Math.max(tx * tileSize, imgPt.x - srcR);
        const iy0 = Math.max(ty * tileSize, imgPt.y - srcR);
        const ix1 = Math.min(tx * tileSize + tileW(tx), imgPt.x + srcR);
        const iy1 = Math.min(ty * tileSize + tileH(ty), imgPt.y + srcR);
        if (ix1 <= ix0 || iy1 <= iy0) continue;
        octx.drawImage(
          t.img,
          ix0 - tx * tileSize, iy0 - ty * tileSize, ix1 - ix0, iy1 - iy0,
          cx + (ix0 - imgPt.x) * k, cy + (iy0 - imgPt.y) * k, (ix1 - ix0) * k, (iy1 - iy0) * k,
        );
      }
    }
    // contornos das caixas dentro da lupa
    for (const b of boxes) {
      const px = (b.cx - b.w / 2) * imageWidth;
      const py = (b.cy - b.h / 2) * imageHeight;
      octx.strokeStyle = classColor(b.cls);
      octx.lineWidth = 2;
      octx.setLineDash(isPending(b) ? [6, 4] : []);
      octx.strokeRect(
        cx + (px - imgPt.x) * k, cy + (py - imgPt.y) * k,
        b.w * imageWidth * k, b.h * imageHeight * k,
      );
    }
    octx.setLineDash([]);
    // mira central da lupa
    octx.strokeStyle = 'rgba(255,90,90,0.9)';
    octx.lineWidth = 1;
    octx.beginPath();
    octx.moveTo(cx - 12, cy); octx.lineTo(cx + 12, cy);
    octx.moveTo(cx, cy - 12); octx.lineTo(cx, cy + 12);
    octx.stroke();
    octx.restore();

    octx.beginPath();
    octx.arc(cx, cy, R, 0, Math.PI * 2);
    octx.strokeStyle = 'rgba(255,255,255,0.85)';
    octx.lineWidth = 2;
    octx.stroke();
    octx.fillStyle = 'rgba(255,255,255,0.85)';
    octx.font = '12px monospace';
    octx.fillText(`${Z}×`, cx + R - 26, cy + R - 10);
  }

  // ---------------------------------------------------------------- HUD
  function updateHud() {
    const clsName = classes[currentCls] ?? `#${currentCls}`;
    const scan = scanOn ? `  •  tiles ${tilesSeen.size}/${nTiles}${tilesSeen.size >= nTiles ? ' ✓ imagem varrida' : ''}` : '';
    hud.textContent =
      `modo: ${mode === 'draw' ? 'DESENHAR' : 'mover'}  •  classe: ${clsName} [${currentCls + 1}]  •  ` +
      `zoom ${(scale() * 100).toFixed(0)}%  •  ${boxes.length} caixas${scan}\n` +
      `[H] mão  [B] caixa  [T] varredura ${scanOn ? 'ON (Enter marca tile)' : 'off'}  ` +
      `[L] lupa  [C] mira  [1-9] classe  [Del] apaga  [N] nova classe  [Ctrl+Z/Y]`;
  }

  // ---------------------------------------------------------------- API pública (interface congelada)
  function getBoxes() { return boxes.map(clone); }
  function getTilesSeen() { return [...tilesSeen].sort((a, b) => a - b); }
  function setClasses(next) {
    classes = (next || []).slice();
    currentCls = clamp(currentCls, 0, Math.max(0, classes.length - 1));
    renderBoxes();
    updateHud();
  }
  function setBoxes(next) {
    boxes = (next || []).map(clone);
    selectedId = null;
    undoStack.length = 0; // reset externo invalida o histórico da sessão
    redoStack.length = 0;
    refresh();
  }
  function setMode(m) {
    if (m !== 'pan' && m !== 'draw') return;
    mode = m;
    container.classList.toggle('anno-mode-draw', m === 'draw');
    container.classList.toggle('anno-mode-pan', m === 'pan');
    updateHud();
  }
  function destroy() {
    window.removeEventListener('keydown', onKey);
    window.removeEventListener('mousemove', onWinMouseMove);
    window.removeEventListener('mouseup', onWinMouseUp);
    ro.disconnect();
    stage.destroy();
    overlay.remove();
    hud.remove();
  }

  // ---------------------------------------------------------------- boot
  window.addEventListener('keydown', onKey);
  window.addEventListener('mousemove', onWinMouseMove);
  window.addEventListener('mouseup', onWinMouseUp);
  const ro = new ResizeObserver(() => {
    const r = container.getBoundingClientRect();
    stage.size({ width: Math.max(100, r.width), height: Math.max(100, r.height) });
    applyView();
  });
  ro.observe(container);

  renderSeen();
  renderBoxes();
  // visão inicial: com varredura ON, vai ao primeiro tile não visto; senão, imagem toda
  if (scanOn) {
    let first = 0;
    while (first < nTiles && tilesSeen.has(first)) first++;
    goToTile(Math.min(first, nTiles - 1));
  } else {
    const s = fitScale();
    stage.scale({ x: s, y: s });
    stage.position({
      x: (stage.width() - imageWidth * s) / 2,
      y: (stage.height() - imageHeight * s) / 2,
    });
    applyView();
  }

  return {
    getBoxes, getTilesSeen, setClasses, setBoxes,
    undo, redo, setMode, setScanMode, destroy,
  };
}
