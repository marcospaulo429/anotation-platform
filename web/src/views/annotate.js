// Aba Anotar — tela em 3 zonas (seção 8):
//   topbar (projeto · img x/y · status de save)
//   strip de thumbs (esq) · canvas (centro) · painel classes+caixas (dir)
//   statusbar (n boxes · última sync)
// Fila inteligente: prelabeled → in_review → unlabeled → done.
// Atalhos globais: D próxima, A anterior. Prefetch da próxima imagem.
// Autosave via ../autosave.js (seção 9). Canvas via interface CONGELADA
// createAnnoCanvas (módulo ../canvas/anno-canvas.js; stub em mocks/ como
// fallback de desenvolvimento).
import { el, clear, showError, statusIcon, classColor, fmtTime, confirmDialog } from "../ui.js";
import * as api from "../api.js";
import { createAutosave } from "../autosave.js";
import { PREFETCH_AHEAD } from "../config.js";

const QUEUE_ORDER = { prelabeled: 0, in_review: 1, unlabeled: 2, done: 3 };
const SAVE_ICON = { saved: "● saved", saving: "○ saving", retrying: "⚠ retrying", conflict: "⚠ conflito" };

async function loadCanvasFactory() {
  try {
    const m = await import("../canvas/anno-canvas.js");
    return m.createAnnoCanvas;
  } catch {
    console.warn("[annotate] canvas real ausente; usando stub de desenvolvimento (web/mocks/anno-canvas-stub.js)");
    const m = await import("../../mocks/anno-canvas-stub.js");
    return m.createAnnoCanvas;
  }
}

export async function renderAnnotate(root, slug, project, { img: startImg } = {}) {
  clear(root);

  // ---- dados base: classes + fila de imagens ----
  let classes = project?.classes ?? [];
  try {
    const res = await api.listClasses(slug);
    classes = (Array.isArray(res) ? res : res.classes ?? []).map((c) => (typeof c === "string" ? c : c.name));
  } catch { /* mantém classes do project.yaml */ }
  classes = classes.map((c) => (typeof c === "string" ? c : c.name));

  const res = await api.listImages(slug).catch((err) => { showError(root, err); return null; });
  if (!res) return () => {};
  const items = (Array.isArray(res) ? res : res.images ?? res.items ?? [])
    .map((i) => ({ name: i.name ?? i.image ?? i, status: i.status ?? "unlabeled" }));
  items.sort((a, b) => (QUEUE_ORDER[a.status] ?? 9) - (QUEUE_ORDER[b.status] ?? 9));
  if (items.length === 0) {
    root.append(el("p", { class: "muted", text: "Sem imagens. Faça upload na aba Imagens." }));
    return () => {};
  }

  let idx = Math.max(0, items.findIndex((i) => i.name === startImg));
  const createAnnoCanvas = await loadCanvasFactory();

  // ---- layout das 3 zonas ----
  const posLabel = el("span", { class: "topbar-pos" });
  const saveLabel = el("span", { class: "save-status saved", text: "● saved" });
  const strip = el("div", { class: "anno-strip" });
  const canvasHost = el("div", { class: "anno-canvas" });
  const classList = el("ul", { class: "class-list" });
  const boxList = el("ul", { class: "box-list" });
  const statusbar = el("div", { class: "anno-statusbar" });
  const bannerHost = el("div", { class: "anno-banners" });

  const undoBtn = el("button", { class: "btn", title: "Desfazer", onclick: () => { handle?.undo(); } }, ["↩"]);
  const redoBtn = el("button", { class: "btn", title: "Refazer", onclick: () => { handle?.redo(); } }, ["↪"]);
  const modePanBtn = el("button", { class: "btn", title: "Navegar (pan)", onclick: () => handle?.setMode("pan") }, ["✋"]);
  const modeDrawBtn = el("button", { class: "btn", title: "Desenhar caixa", onclick: () => handle?.setMode("draw") }, ["▣"]);
  const doneBtn = el("button", { class: "btn btn-primary", onclick: markDone }, ["Done ✓"]);
  const prevBtn = el("button", { class: "btn", title: "Anterior (A)", onclick: () => navigate(-1) }, ["‹ A"]);
  const nextBtn = el("button", { class: "btn", title: "Próxima (D)", onclick: () => navigate(1) }, ["D ›"]);

  const topbar = el("div", { class: "anno-topbar" }, [
    el("a", { class: "btn btn-link", href: `#/p/${encodeURIComponent(slug)}/imagens` }, ["‹ projeto"]),
    posLabel,
    el("span", { class: "spacer" }),
    undoBtn, redoBtn, modePanBtn, modeDrawBtn,
    saveLabel,
    prevBtn, nextBtn, doneBtn,
  ]);
  const panel = el("div", { class: "anno-panel" }, [
    el("h3", { text: "Classes" }), classList,
    el("h3", { text: "Caixas" }), boxList,
  ]);
  const grid = el("div", { class: "anno-grid" }, [strip, canvasHost, panel]);
  root.append(topbar, bannerHost, grid, statusbar);

  // ---- estado por imagem ----
  let handle = null;
  let saver = null;
  const localDrafts = new Set(); // imgs com rascunho local nesta sessão (🔵)

  function renderStrip() {
    clear(strip);
    items.forEach((it, i) => {
      const s = localDrafts.has(it.name) && it.status !== "done" ? "draft" : it.status;
      strip.append(el("button", {
        class: `strip-thumb ${i === idx ? "active" : ""}`,
        title: `${statusIcon(s)} ${it.name}`,
        onclick: () => openImage(i),
      }, [
        el("img", { src: api.thumbUrl(slug, it.name), alt: it.name, loading: "lazy" }),
        el("span", { text: statusIcon(s) }),
      ]));
    });
  }

  function renderClassesPanel() {
    clear(classList);
    classes.forEach((name, i) => {
      classList.append(el("li", {}, [
        el("span", { class: "swatch", style: { background: classColor(i) } }),
        el("span", { text: `${i + 1} · ${name}` }),
      ]));
    });
    classList.append(el("li", {}, [
      el("button", { class: "btn btn-link", onclick: addClassInline }, ["+ nova classe (N)"]),
    ]));
  }

  function renderBoxes(boxes) {
    clear(boxList);
    for (const b of boxes) {
      boxList.append(el("li", { class: "box-item" }, [
        el("span", { class: "swatch", style: { background: classColor(b.cls) } }),
        el("span", {
          text: `${classes[b.cls] ?? `#${b.cls}`} · ${b.origin === "model" ? "modelo" : "humano"}` +
            `${b.model_conf != null ? ` ${(b.model_conf * 100).toFixed(0)}%` : ""}` +
            `${b.edited ? " ✎" : ""}`,
        }),
      ]));
    }
    statusbar.textContent = `${boxes.length} caixas · autosave: última sync ${
      saver ? fmtTime(new Date(lastSyncTs)) : "—"}`;
  }

  let lastSyncTs = Date.now();
  function onSaveStatus(s) {
    saveLabel.textContent = SAVE_ICON[s] ?? s;
    saveLabel.className = `save-status ${s}`;
    if (s === "saved") lastSyncTs = Date.now();
    if (handle) renderBoxes(handle.getBoxes());
  }

  function onConflict() {
    clear(bannerHost);
    bannerHost.append(el("div", {
      class: "alert alert-warn",
      text: "Versão divergente no servidor (409). Seu rascunho local está salvo e não será sobrescrito.",
    }));
  }

  function showRecoveryBanner(local) {
    clear(bannerHost);
    const banner = el("div", { class: "alert alert-info" }, [
      el("span", { text: `Rascunho local de ${fmtTime(local.updated_at)} recuperado. ` }),
      el("button", {
        class: "btn btn-primary",
        onclick: () => {
          const boxes = saver.restoreLocal(local);
          localDrafts.add(items[idx].name);
          handle?.setBoxes(boxes);
          renderBoxes(boxes);
          clear(bannerHost);
          renderStrip();
        },
      }, ["Restaurar"]),
      el("button", {
        class: "btn",
        onclick: async () => { await saver.discardLocal(); clear(bannerHost); },
      }, ["Descartar"]),
    ]);
    bannerHost.append(banner);
  }

  async function openImage(i) {
    if (i < 0 || i >= items.length) return;
    // Navegação dispara flush do rascunho atual ANTES de trocar (seção 9).
    if (saver) { await saver.flush("navigate"); saver.destroy(); saver = null; }
    if (handle) { handle.destroy(); handle = null; }
    clear(bannerHost);
    idx = i;
    const img = items[idx];
    posLabel.textContent = `img ${idx + 1}/${items.length} · ${img.name}`;
    renderStrip();

    saver = createAutosave({ slug, image: img.name, api, onStatus: onSaveStatus, onConflict });
    let base;
    try {
      base = await saver.open();
    } catch (err) {
      showError(root, err);
      return;
    }

    handle = createAnnoCanvas(canvasHost, {
      imageWidth: project?.image_width ?? 1920,
      imageHeight: project?.image_height ?? 1080,
      classes,
      tilesUrl: (x, y) => api.tileUrl(slug, img.name, x, y),
      tileSize: 640,
      boxes: base.boxes,
      initialTilesSeen: [],
      onChange: (boxes, op) => {
        localDrafts.add(img.name);
        saver.recordOp(op, boxes, handle.getTilesSeen());
        renderBoxes(boxes);
      },
      onClassRequest: () => openClassPicker(),
    });
    renderBoxes(base.boxes);
    if (base.pendingLocal) showRecoveryBanner(base.pendingLocal);
    prefetch(idx + 1);
  }

  function navigate(delta) {
    openImage(idx + delta);
  }

  async function markDone() {
    if (!saver || !handle) return;
    const img = items[idx];
    try {
      await saver.flush("commit");
      await api.commitLabels(slug, img.name, saver.buildDraft());
      await saver.afterCommit();
      img.status = "done";
      localDrafts.delete(img.name);
      renderStrip();
      navigate(1); // Done → próxima imagem (fluxo olha → anota → próxima)
    } catch (err) {
      showError(root, err);
    }
  }

  function openClassPicker() {
    clear(bannerHost);
    const overlay = el("div", { class: "modal-overlay" });
    const close = () => overlay.remove();
    overlay.onclick = (e) => { if (e.target === overlay) close(); };
    overlay.append(el("div", { class: "modal" }, [
      el("h3", { text: "Escolher classe" }),
      ...classes.map((name, i) => el("button", {
        class: "btn class-pick",
        onclick: () => close(),
      }, [
        el("span", { class: "swatch", style: { background: classColor(i) } }),
        `${i + 1} · ${name}`,
      ])),
      el("button", { class: "btn", onclick: () => { close(); addClassInline(); } }, ["+ nova classe (entra no final)"]),
    ]));
    document.body.append(overlay);
  }

  async function addClassInline() {
    const name = window.prompt("Nome da nova classe (entra NO FINAL, irreversível):");
    if (!name || !name.trim()) return;
    const ok = await confirmDialog(
      `Adicionar "${name.trim()}" como classe #${classes.length}? Irreversível (append-only).`,
      { danger: true, confirmText: "Adicionar" },
    );
    if (!ok) return;
    try {
      await api.addClass(slug, name.trim());
      classes.push(name.trim());
      handle?.setClasses(classes);
      renderClassesPanel();
    } catch (err) {
      showError(root, err);
    }
  }

  function prefetch(i) {
    for (let k = 0; k < PREFETCH_AHEAD && i + k < items.length; k++) {
      const next = items[i + k];
      api.getLabels(slug, next.name, "merged").catch(() => {});
      const im = new Image();
      im.src = api.thumbUrl(slug, next.name);
    }
  }

  function onKeydown(e) {
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (e.key === "d" || e.key === "D") navigate(1);
    else if (e.key === "a" || e.key === "A") navigate(-1);
    else if (e.key === "n" || e.key === "N") addClassInline();
  }
  document.addEventListener("keydown", onKeydown);

  renderClassesPanel();
  await openImage(idx);

  // cleanup ao trocar de aba/rota (chamado pelo router)
  return () => {
    document.removeEventListener("keydown", onKeydown);
    if (saver) { saver.flush("navigate"); saver.destroy(); }
    if (handle) handle.destroy();
  };
}
