// Aba Importar/Exportar.
// Import: form images_dir/labels_dir → dry-run primeiro (relatório de
// validação por arquivo) → confirmar grava em manual/ (evento imported).
// Export: POST /export → congela exports/vN e mostra o manifest.
import { el, clear, showError } from "../ui.js";
import * as api from "../api.js";

export async function renderImportExport(root, slug) {
  clear(root);
  root.append(el("h2", { text: "Importar / Exportar" }));

  // ---------- Importação ----------
  const reportBox = el("div", { class: "report-box" });
  const imagesDir = el("input", { type: "text", placeholder: "/raid/user_marcospaulo/.../images" });
  const labelsDir = el("input", { type: "text", placeholder: "/raid/user_marcospaulo/.../labels" });
  let lastDryRun = null;

  const confirmBtn = el("button", {
    class: "btn btn-primary", disabled: true,
    onclick: async () => {
      try {
        const res = await api.importDataset(slug, {
          images_dir: imagesDir.value.trim(),
          labels_dir: labelsDir.value.trim(),
          dry_run: false,
        });
        clear(reportBox);
        reportBox.append(el("div", { class: "alert alert-info", text: `Importação concluída: ${JSON.stringify(res)}` }));
      } catch (err) {
        showError(root, err);
      }
    },
  }, ["Confirmar importação"]);

  const dryBtn = el("button", {
    class: "btn",
    onclick: async () => {
      clear(reportBox);
      reportBox.append(el("p", { class: "muted", text: "Validando (dry-run)…" }));
      try {
        lastDryRun = await api.importDataset(slug, {
          images_dir: imagesDir.value.trim(),
          labels_dir: labelsDir.value.trim(),
          dry_run: true,
        });
        clear(reportBox);
        reportBox.append(
          el("h3", { text: "Relatório de validação (dry-run)" }),
          el("pre", { class: "json-view", text: JSON.stringify(lastDryRun, null, 2) }),
        );
        confirmBtn.disabled = false;
      } catch (err) {
        clear(reportBox);
        showError(root, err);
      }
    },
  }, ["Validar (dry-run)"]);

  const importCard = el("section", { class: "card" }, [
    el("h3", { text: "Importar dados já anotados" }),
    el("p", { class: "muted", text: "Labels válidos são gravados direto em manual/ (fonte da verdade) e as imagens entram como done. Rode o dry-run e confira o relatório antes de confirmar." }),
    el("label", {}, ["Diretório de imagens", imagesDir]),
    el("label", {}, ["Diretório de labels YOLO", labelsDir]),
    el("div", { class: "toolbar" }, [dryBtn, confirmBtn]),
    reportBox,
  ]);

  // ---------- Exportação ----------
  const manifestBox = el("div", { class: "report-box" });
  const exportsList = el("ul", { class: "export-list" });
  const exportBtn = el("button", {
    class: "btn btn-primary",
    onclick: async () => {
      clear(manifestBox);
      manifestBox.append(el("p", { class: "muted", text: "Gerando export (split por placa)…" }));
      try {
        const res = await api.exportProject(slug);
        clear(manifestBox);
        manifestBox.append(
          el("h3", { text: "Manifest do export" }),
          el("pre", { class: "json-view", text: JSON.stringify(res, null, 2) }),
        );
        loadExports();
      } catch (err) {
        clear(manifestBox);
        showError(root, err);
      }
    },
  }, ["Gerar export (exports/vN)"]);

  async function loadExports() {
    clear(exportsList);
    try {
      const res = await api.listExports(slug);
      const items = Array.isArray(res) ? res : res.exports ?? [];
      for (const ex of items) {
        const label = typeof ex === "string" ? ex : ex.version ?? ex.name ?? JSON.stringify(ex);
        exportsList.append(el("li", { text: label }));
      }
      if (items.length === 0) exportsList.append(el("li", { class: "muted", text: "Nenhum export ainda." }));
    } catch {
      exportsList.append(el("li", { class: "muted", text: "Não foi possível listar exports." }));
    }
  }

  const exportCard = el("section", { class: "card" }, [
    el("h3", { text: "Exportar dataset" }),
    el("p", { class: "muted", text: "Snapshot imutável com split por placa/período (nunca aleatório por imagem). Drafts nunca entram no export — só manual/ e pre/ aceitas." }),
    el("div", { class: "toolbar" }, [exportBtn]),
    manifestBox,
    el("h4", { text: "Exports anteriores" }),
    exportsList,
  ]);

  root.append(importCard, exportCard);
  await loadExports();
}
