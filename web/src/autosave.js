// Autosave — a peça crítica (seção 9 do PREANNOTATION_PLATFORM.md).
//
// Três camadas:
//  1. Cada op cai ANTES no draft local (IndexedDB, DB "anno-drafts",
//     store por `${slug}/${img}`) — crash do navegador não perde nada.
//  2. Fila de sync com debounce de 500 ms; PUT do draft dispara quando:
//     5 ops acumuladas OU 30 s desde o último sync OU navegação OU
//     visibilitychange=hidden — o que vier primeiro. Retry com backoff
//     exponencial em falha; 409 gera aviso não-destrutivo e mantém o
//     rascunho local.
//  3. Draft ≠ YOLO: o commit (botão Done) é separado e feito pela view.
import { getUserName } from "./auth.js";

const DB_NAME = "anno-drafts";
const STORE = "drafts";
const HISTORY_K = 50;
const EVERY_N_OPS = 5;
const EVERY_SECONDS = 30;
const DEBOUNCE_MS = 500;
const BACKOFF_MAX_MS = 30000;

// ---------- IndexedDB (camada local) ----------
let dbPromise = null;
function openDb() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      if (!req.result.objectStoreNames.contains(STORE)) {
        req.result.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

function tx(mode, fn) {
  return openDb().then((db) => new Promise((resolve, reject) => {
    const t = db.transaction(STORE, mode);
    const store = t.objectStore(STORE);
    const out = fn(store);
    t.oncomplete = () => resolve(out && out.result !== undefined ? out.result : out);
    t.onerror = () => reject(t.error);
  }));
}

const draftKey = (slug, img) => `${slug}/${img}`;

export async function loadLocalDraft(slug, img) {
  try {
    const db = await openDb();
    return await new Promise((resolve, reject) => {
      const req = db.transaction(STORE, "readonly").objectStore(STORE).get(draftKey(slug, img));
      req.onsuccess = () => resolve(req.result?.draft ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch { return null; } // IndexedDB indisponível não derruba a anotação
}

export function saveLocalDraft(slug, img, draft) {
  return tx("readwrite", (s) => s.put({ key: draftKey(slug, img), draft })).catch(() => {});
}

export function deleteLocalDraft(slug, img) {
  return tx("readwrite", (s) => s.delete(draftKey(slug, img))).catch(() => {});
}

// ---------- Controlador de autosave por imagem ----------
// Eventos de status para o indicador: "saved" | "saving" | "retrying" | "conflict"
export function createAutosave({ slug, image, api, onStatus, onConflict }) {
  let boxes = [];
  let baseVersion = null;
  let history = [];
  let opsSinceCommit = 0;
  let pendingOps = 0;
  let lastSyncAt = 0;
  let syncing = false;
  let conflict = false;
  let destroyed = false;
  let debounceTimer = null;
  let periodicTimer = null;
  let backoffMs = 1000;
  let tilesSeen = [];

  const emit = (s) => { if (onStatus) onStatus(s, { lastSyncAt, pendingOps }); };

  function buildDraft() {
    return {
      schema_version: 1,
      image,
      base_version: baseVersion,
      updated_at: new Date().toISOString(),
      updated_by: getUserName(),
      ops_since_commit: opsSinceCommit,
      tiles_seen: tilesSeen,
      boxes,
      history: history.slice(-HISTORY_K),
    };
  }

  async function sync(reason) {
    if (syncing || destroyed) return;
    if (pendingOps === 0 && reason !== "flush-empty") return;
    syncing = true;
    emit("saving");
    const draft = buildDraft();
    try {
      await api.putDraft(slug, image, draft);
      pendingOps = 0;
      lastSyncAt = Date.now();
      backoffMs = 1000;
      conflict = false; // sync bem-sucedido limpa conflito anterior
      syncing = false;
      emit("saved");
    } catch (err) {
      syncing = false;
      if (err && err.status === 409) {
        // Versão divergente no servidor — aviso não-destrutivo, draft local intacto.
        conflict = true;
        emit("conflict");
        if (onConflict) onConflict(err);
        return;
      }
      emit("retrying");
      if (!destroyed) {
        setTimeout(() => sync("retry"), backoffMs);
        backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
      }
    }
  }

  /** Limpa o estado de conflito e força nova tentativa (ex.: após revert). */
  function resetConflict() {
    conflict = false;
    scheduleSync();
  }

  function scheduleSync() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      if (pendingOps >= EVERY_N_OPS) sync("ops");
      else if (Date.now() - lastSyncAt >= EVERY_SECONDS * 1000) sync("time");
      else sync("debounce"); // debounce: manda o que houver após 500 ms parado
    }, DEBOUNCE_MS);
  }

  function onVisibility() {
    if (document.visibilityState === "hidden") flush("tab-hide");
  }

  document.addEventListener("visibilitychange", onVisibility);
  periodicTimer = setInterval(() => {
    if (pendingOps > 0 && Date.now() - lastSyncAt >= EVERY_SECONDS * 1000) sync("time");
  }, 1000);

  return {
    // Abre a imagem: busca merged no servidor e checa rascunho local.
    async open() {
      const res = await api.getLabels(slug, image, "merged");
      boxes = Array.isArray(res) ? res : (res.boxes ?? []);
      baseVersion = (res && !Array.isArray(res) && (res.base_version ?? res.version ?? res.sha256)) || null;
      history = [];
      opsSinceCommit = 0;
      pendingOps = 0;
      lastSyncAt = Date.now();
      emit("saved");
      const local = await loadLocalDraft(slug, image);
      let pendingLocal = null;
      if (local && JSON.stringify(local.boxes) !== JSON.stringify(boxes)) {
        pendingLocal = local; // a view decide: restaurar ou descartar (banner)
      }
      return { boxes, baseVersion, pendingLocal };
    },

    // Chamado no onChange do canvas: grava local ANTES de qualquer rede.
    recordOp(op, nextBoxes, nextTilesSeen) {
      if (nextBoxes) boxes = nextBoxes;
      if (nextTilesSeen) tilesSeen = nextTilesSeen;
      opsSinceCommit += 1;
      pendingOps += 1;
      history.push({ t: new Date().toISOString(), op: op?.op ?? String(op), box: op?.box ?? null });
      saveLocalDraft(slug, image, buildDraft()); // fire-and-forget, camada 1
      emit("saving");
      scheduleSync();
    },

    // Restaura um rascunho local recuperado (banner "Restaurar").
    restoreLocal(draft) {
      boxes = draft.boxes ?? boxes;
      baseVersion = draft.base_version ?? baseVersion;
      history = draft.history ?? history;
      opsSinceCommit = draft.ops_since_commit ?? opsSinceCommit;
      pendingOps += 1;
      scheduleSync();
      return boxes;
    },

    async discardLocal() { await deleteLocalDraft(slug, image); },

    // Força sync imediato (navegação, Done, tab-hide).
    flush(reason) { clearTimeout(debounceTimer); return sync(reason ?? "flush"); },

    // Após commit bem-sucedido: zera contadores e remove rascunho local.
    async afterCommit() {
      opsSinceCommit = 0;
      pendingOps = 0;
      history = [];
      await deleteLocalDraft(slug, image);
      emit("saved");
    },

    getBaseVersion: () => baseVersion,
    buildDraft,
    resetConflict, // limpa conflito 409 e retenta (usado após revert)

    destroy() {
      destroyed = true;
      clearTimeout(debounceTimer);
      clearInterval(periodicTimer);
      document.removeEventListener("visibilitychange", onVisibility);
    },
  };
}
