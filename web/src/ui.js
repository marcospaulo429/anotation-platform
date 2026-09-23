// Helpers de UI sem framework: criação de elementos, badges de status,
// paleta de cores por classe e modal de confirmação.

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") {
      node.addEventListener(k.slice(2), v);
    } else if (k === "dataset") {
      Object.assign(node.dataset, v);
    } else if (k === "style" && typeof v === "object") {
      Object.assign(node.style, v);
    } else node.setAttribute(k, v === true ? "" : String(v));
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined) continue;
    node.append(c.nodeType ? c : document.createTextNode(String(c)));
  }
  return node;
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// Ícones de status por imagem (seção 8).
export const STATUS_ICON = {
  unlabeled: "⚪",
  prelabeled: "🟡",
  in_review: "🔵",
  draft: "🔵",
  done: "🟢",
};
export const statusIcon = (s) => STATUS_ICON[s] ?? "⚪";

// Paleta determinística por índice de classe (ordem YOLO).
const CLASS_COLORS = [
  "#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4",
  "#f032e6", "#bfef45", "#469990", "#9a6324", "#800000", "#000075",
];
export const classColor = (i) => CLASS_COLORS[i % CLASS_COLORS.length];

export function confirmDialog(message, { danger = false, confirmText = "Confirmar" } = {}) {
  return new Promise((resolve) => {
    const close = (v) => { overlay.remove(); resolve(v); };
    const overlay = el("div", { class: "modal-overlay", onclick: (e) => { if (e.target === overlay) close(false); } }, [
      el("div", { class: "modal", role: "dialog" }, [
        el("p", { text: message }),
        el("div", { class: "modal-actions" }, [
          el("button", { class: "btn", onclick: () => close(false) }, ["Cancelar"]),
          el("button", { class: danger ? "btn btn-danger" : "btn btn-primary", onclick: () => close(true) }, [confirmText]),
        ]),
      ]),
    ]);
    document.body.append(overlay);
  });
}

export function showError(root, err) {
  const msg = err && err.message ? err.message : String(err);
  root.prepend(el("div", { class: "alert alert-error", text: msg }));
}

export const fmtPct = (x) => `${Math.round((x ?? 0) * 100)}%`;
export const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = iso instanceof Date ? iso : new Date(iso);
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
};

export const kebab = (s) =>
  s.normalize("NFD").replace(/[̀-ͯ]/g, "")
    .toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
