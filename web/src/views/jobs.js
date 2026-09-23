// Aba Jobs: status dos jobs de pré-anotação/export (GET /jobs), com refresh
// automático enquanto a aba está visível. Na Fase 1 a submissão ao Slurm é
// manual/aprovada — aqui só se observa.
import { el, clear, showError } from "../ui.js";
import * as api from "../api.js";

export async function renderJobs(root, slug) {
  clear(root);
  root.append(
    el("h2", { text: "Jobs" }),
    el("p", { class: "alert alert-info", text: "Fase 1: jobs ficam registrados aqui; a submissão ao cluster (Slurm) é manual e aprovada caso a caso." }),
  );
  const tableHost = el("div", {});
  const refreshBtn = el("button", { class: "btn", onclick: load }, ["Atualizar"]);
  root.append(el("div", { class: "toolbar" }, [refreshBtn]), tableHost);

  async function load() {
    clear(tableHost);
    let jobs;
    try {
      const res = await api.listJobs(slug);
      jobs = Array.isArray(res) ? res : res.jobs ?? [];
    } catch (err) {
      showError(tableHost, err);
      return;
    }
    if (jobs.length === 0) {
      tableHost.append(el("p", { class: "muted", text: "Nenhum job registrado." }));
      return;
    }
    tableHost.append(el("table", { class: "table" }, [
      el("thead", {}, [el("tr", {}, ["ID", "Tipo", "Status", "Criado em"].map((h) => el("th", { text: h })))]),
      el("tbody", {}, jobs.map((j) => el("tr", {}, [
        el("td", { text: String(j.id ?? j.job_id ?? "—") }),
        el("td", { text: j.type ?? j.kind ?? "preannotate" }),
        el("td", { text: j.status ?? "pending" }),
        el("td", { text: j.created_at ?? "—" }),
      ]))),
    ]));
  }

  await load();
  const timer = setInterval(() => {
    if (document.visibilityState === "visible") load();
  }, 15000);
  return () => clearInterval(timer);
}
