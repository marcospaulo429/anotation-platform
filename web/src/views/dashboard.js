// Dashboard: lista de projetos com nome, total de imagens, % done e último
// export; botão "+ Novo projeto".
import { el, clear, showError, fmtPct } from "../ui.js";
import * as api from "../api.js";

export async function renderDashboard(root) {
  clear(root);
  root.append(el("h1", { text: "Projetos" }));
  const grid = el("div", { class: "card-grid" });
  root.append(
    el("div", { class: "toolbar" }, [
      el("a", { class: "btn btn-primary", href: "#/new" }, ["+ Novo projeto"]),
    ]),
    grid,
  );

  let projects;
  try {
    projects = await api.listProjects();
  } catch (err) {
    showError(root, err);
    return;
  }
  clear(grid);
  const list = Array.isArray(projects) ? projects : projects.projects ?? [];
  if (list.length === 0) {
    grid.append(el("p", { class: "muted", text: "Nenhum projeto ainda. Crie o primeiro!" }));
    return;
  }
  for (const p of list) {
    const total = p.total_images ?? p.images ?? p.stats?.total ?? 0;
    const done = p.done ?? p.stats?.done ?? 0;
    const pct = total > 0 ? done / total : 0;
    grid.append(el("a", { class: "card project-card", href: `#/p/${encodeURIComponent(p.slug)}` }, [
      el("h2", { text: p.name ?? p.slug }),
      el("p", { class: "muted", text: p.slug }),
      el("div", { class: "progress" }, [
        el("div", { class: "progress-fill", style: { width: fmtPct(pct) } }),
      ]),
      el("p", { class: "card-stats", text: `${done}/${total} imagens · ${fmtPct(pct)} concluído` }),
      el("p", { class: "muted", text: `Último export: ${p.last_export ?? p.stats?.last_export ?? "—"}` }),
    ]));
  }
}
