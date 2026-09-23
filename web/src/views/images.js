// Aba Imagens: grade de thumbs com status, filtro, paginação por cursor,
// upload por drag-and-drop (multipart, barra de progresso) e botão
// "Pré-anotar" (registra o job; a submissão ao Slurm é manual/aprovada).
import { el, clear, showError, statusIcon } from "../ui.js";
import * as api from "../api.js";

export async function renderImages(root, slug) {
  clear(root);
  root.append(el("h2", { text: "Imagens" }));

  let statusFilter = "";
  let cursor = null;
  const enc = encodeURIComponent(slug);

  const grid = el("div", { class: "thumb-grid" });
  const moreBtn = el("button", { class: "btn", style: { display: "none" }, onclick: loadMore }, ["Carregar mais"]);
  const progress = el("div", { class: "upload-progress", style: { display: "none" } }, [
    el("div", { class: "progress" }, [el("div", { class: "progress-fill" })]),
    el("span", { class: "muted" }),
  ]);

  const drop = el("div", { class: "dropzone", text: "Arraste imagens aqui para upload (ou clique para escolher)" });
  const fileInput = el("input", { type: "file", multiple: true, accept: "image/*", style: { display: "none" } });
  drop.onclick = () => fileInput.click();
  fileInput.onchange = () => doUpload([...fileInput.files]);
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = (e) => {
    e.preventDefault();
    drop.classList.remove("over");
    doUpload([...e.dataTransfer.files].filter((f) => f.type.startsWith("image/")));
  };

  const filterSel = el("select", {
    onchange: (e) => { statusFilter = e.target.value; reload(); },
  }, [
    el("option", { value: "", text: "Todos os status" }),
    el("option", { value: "unlabeled", text: "⚪ unlabeled" }),
    el("option", { value: "prelabeled", text: "🟡 prelabeled" }),
    el("option", { value: "in_review", text: "🔵 em revisão" }),
    el("option", { value: "done", text: "🟢 done" }),
  ]);

  const preBtn = el("button", {
    class: "btn btn-primary",
    onclick: async () => {
      try {
        await api.preannotate(slug, "all");
        root.prepend(el("div", {
          class: "alert alert-info",
          text: "Job de pré-anotação registrado. Na Fase 1 a submissão ao cluster (Slurm) é manual/aprovada — acompanhe na aba Jobs.",
        }));
      } catch (err) {
        showError(root, err);
      }
    },
  }, ["Pré-anotar"]);

  root.append(
    el("div", { class: "toolbar" }, [filterSel, preBtn]),
    drop, fileInput, progress, grid, moreBtn,
  );

  async function doUpload(files) {
    if (!files.length) return;
    progress.style.display = "";
    const fill = progress.querySelector(".progress-fill");
    const label = progress.querySelector("span");
    label.textContent = `Enviando ${files.length} arquivo(s)…`;
    try {
      await api.uploadImages(slug, files, (p) => {
        fill.style.width = `${Math.round(p * 100)}%`;
        label.textContent = `Enviando… ${Math.round(p * 100)}%`;
      });
      label.textContent = "Upload concluído.";
      reload();
    } catch (err) {
      label.textContent = `Falha no upload: ${err.message}`;
    }
  }

  function thumbCard(img) {
    const name = img.img ?? img.name ?? img.image ?? img;
    const status = img.display_status ?? img.status ?? "unlabeled";
    return el("a", {
      class: "thumb-card",
      href: `#/p/${enc}/anotar?img=${encodeURIComponent(name)}`,
      title: name,
    }, [
      el("img", { src: api.thumbUrl(slug, name), alt: name, loading: "lazy" }),
      el("span", { class: "thumb-status", text: `${statusIcon(status)} ${name}` }),
    ]);
  }

  async function loadMore() {
    try {
      const res = await api.listImages(slug, { status: statusFilter || undefined, cursor: cursor ?? undefined });
      const items = Array.isArray(res) ? res : res.images ?? res.items ?? [];
      cursor = (!Array.isArray(res) && res.next_cursor) || null;
      for (const img of items) grid.append(thumbCard(img));
      moreBtn.style.display = cursor ? "" : "none";
    } catch (err) {
      showError(root, err);
    }
  }

  function reload() {
    clear(grid);
    cursor = null;
    loadMore();
  }

  await loadMore();
}
