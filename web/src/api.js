// Wrapper de fetch para a API /annotate (contratos da seção 7 do
// PREANNOTATION_PLATFORM.md). Trata X-API-Key, erros JSON e re-prompt de
// chave em 401/403.
import { API_BASE } from "./config.js";
import { getApiKey, ensureApiKey, clearApiKey } from "./auth.js";

export class ApiError extends Error {
  constructor(status, payload) {
    const detail = payload && (payload.detail ?? payload.message);
    const msg =
      detail == null
        ? `Erro HTTP ${status}`
        : typeof detail === "string"
          ? detail
          : JSON.stringify(detail);
    super(msg);
    this.status = status;
    this.payload = payload;
  }
}

async function request(path, { method = "GET", body, headers = {}, _retry = true } = {}) {
  const key = ensureApiKey();
  const h = { ...headers };
  if (key) h["X-API-Key"] = key;
  let payload = body;
  if (body !== undefined && !(body instanceof FormData)) {
    h["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, { method, headers: h, body: payload });
  if ((res.status === 401 || res.status === 403) && _retry) {
    clearApiKey();
    ensureApiKey();
    return request(path, { method, body, headers, _retry: false });
  }
  if (!res.ok) {
    let data = null;
    try { data = await res.json(); } catch { /* corpo não-JSON */ }
    throw new ApiError(res.status, data);
  }
  if (res.status === 204) return null;
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

const enc = encodeURIComponent;

// ---- Projetos ----
export const listProjects = () => request("/projects");
export const createProject = (body) => request("/projects", { method: "POST", body });
export const getProject = (slug) => request(`/projects/${enc(slug)}`);
export const patchProject = (slug, body) =>
  request(`/projects/${enc(slug)}`, { method: "PATCH", body });

// ---- Classes (append-only) ----
export const listClasses = (slug) => request(`/projects/${enc(slug)}/classes`);
export const addClass = (slug, name) =>
  request(`/projects/${enc(slug)}/classes`, { method: "POST", body: { name } });

// ---- Imagens ----
export const listImages = (slug, { status, cursor } = {}) => {
  const q = new URLSearchParams();
  if (status) q.set("status", status);
  if (cursor) q.set("cursor", cursor);
  const qs = q.toString();
  return request(`/projects/${enc(slug)}/images${qs ? `?${qs}` : ""}`);
};

// Upload multipart com barra de progresso (fetch não expõe progresso de upload).
export function uploadImages(slug, files, onProgress) {
  return new Promise((resolve, reject) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f, f.name);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/projects/${enc(slug)}/images`);
    const k = getApiKey();
    if (k) xhr.setRequestHeader("X-API-Key", k);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      let data = null;
      try { data = JSON.parse(xhr.responseText); } catch { /* vazio */ }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data);
      else reject(new ApiError(xhr.status, data));
    };
    xhr.onerror = () => reject(new ApiError(0, null));
    xhr.send(fd);
  });
}

// URLs de imagem (thumb/full/tiles). <img>/canvas não enviam headers, então a
// chave vai como ?api_key= (backend deve aceitar como alternativa ao header).
function withKey(url) {
  const k = getApiKey();
  return k ? `${url}${url.includes("?") ? "&" : "?"}api_key=${enc(k)}` : url;
}
export const thumbUrl = (slug, img) =>
  withKey(`${API_BASE}/projects/${enc(slug)}/images/${enc(img)}/thumb`);
export const fullUrl = (slug, img) =>
  withKey(`${API_BASE}/projects/${enc(slug)}/images/${enc(img)}/full`);
export const tileUrl = (slug, img, x, y, w = 640) =>
  withKey(`${API_BASE}/projects/${enc(slug)}/images/${enc(img)}/tiles/${x}/${y}?w=${w}`);

// ---- Labels / draft / commit ----
export const getLabels = (slug, img, source = "merged") =>
  request(`/projects/${enc(slug)}/labels/${enc(img)}?source=${enc(source)}`);
export const putDraft = (slug, img, draft) =>
  request(`/projects/${enc(slug)}/labels/${enc(img)}/draft`, { method: "PUT", body: draft });
export const commitLabels = (slug, img, body = {}) =>
  request(`/projects/${enc(slug)}/labels/${enc(img)}/commit`, { method: "POST", body });
export const revertLabels = (slug, img, to = "pre") =>
  request(`/projects/${enc(slug)}/labels/${enc(img)}/revert?to=${enc(to)}`, { method: "POST" });

// ---- Pré-anotação / jobs ----
export const preannotate = (slug, images = "all") =>
  request(`/projects/${enc(slug)}/preannotate`, { method: "POST", body: { images } });
export const listJobs = (slug) => request(`/projects/${enc(slug)}/jobs`);

// ---- Importação / exportação ----
export const importDataset = (slug, { images_dir, labels_dir, dry_run = true }) =>
  request(`/projects/${enc(slug)}/import`, {
    method: "POST",
    body: { images_dir, labels_dir, dry_run },
  });
export const exportProject = (slug) =>
  request(`/projects/${enc(slug)}/export`, { method: "POST" });
export const listExports = (slug) => request(`/projects/${enc(slug)}/exports`);

// ---- Stats ----
export const getStats = (slug) => request(`/projects/${enc(slug)}/stats`);
