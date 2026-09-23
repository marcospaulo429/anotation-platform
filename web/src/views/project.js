// Página do projeto: header com progresso + tabs
// [Anotar] [Imagens] [Classes] [Importar/Exportar] [Jobs] [Config].
import { el, clear, showError, fmtPct } from "../ui.js";
import * as api from "../api.js";
import { renderAnnotate } from "./annotate.js";
import { renderImages } from "./images.js";
import { renderClasses } from "./classes.js";
import { renderImportExport } from "./importExport.js";
import { renderJobs } from "./jobs.js";
import { renderSettings } from "./settings.js";

const TABS = [
  ["anotar", "Anotar"],
  ["imagens", "Imagens"],
  ["classes", "Classes"],
  ["importar", "Importar/Exportar"],
  ["jobs", "Jobs"],
  ["config", "Config"],
];

export async function renderProject(root, slug, tab, params) {
  clear(root);
  const project = await api.getProject(slug).catch(() => null);
  const stats = await api.getStats(slug).catch(() => null);

  const total = stats?.total ?? project?.total_images ?? 0;
  const done = stats?.done ?? 0;
  const pct = total > 0 ? done / total : 0;

  const enc = encodeURIComponent(slug);
  const header = el("div", { class: "project-header" }, [
    el("h1", { text: project?.name ?? slug }),
    el("div", { class: "progress progress-lg" }, [
      el("div", { class: "progress-fill", style: { width: fmtPct(pct) } }),
    ]),
    el("p", { class: "muted", text: `${done}/${total} imagens · ${fmtPct(pct)} concluído${stats?.correction_rate != null ? ` · correction rate ${stats.correction_rate}` : ""}` }),
    el("nav", { class: "tabs" }, TABS.map(([id, label]) =>
      el("a", { class: `tab ${tab === id ? "active" : ""}`, href: `#/p/${enc}/${id}` }, [label])
    )),
  ]);
  const body = el("div", { class: "project-body" });
  root.append(header, body);

  switch (tab) {
    case "anotar": return await renderAnnotate(body, slug, project, { img: params.get("img") });
    case "imagens": return await renderImages(body, slug);
    case "classes": return await renderClasses(body, slug, project);
    case "importar": return await renderImportExport(body, slug);
    case "jobs": return await renderJobs(body, slug);
    case "config": return await renderSettings(body, slug, project);
    default:
      body.append(el("p", { text: "Aba desconhecida." }));
  }
  return null;
}

export { showError };
