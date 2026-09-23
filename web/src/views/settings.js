// Aba Config: lê/atualiza project.yaml (PATCH /projects/{slug}). Classes são
// somente-leitura aqui (gerenciadas na aba Classes, append-only).
import { el, clear, showError } from "../ui.js";
import * as api from "../api.js";

export async function renderSettings(root, slug, project) {
  clear(root);
  root.append(el("h2", { text: "Configurações do projeto" }));

  const proj = project ?? (await api.getProject(slug).catch((err) => { showError(root, err); return null; }));
  if (!proj) return;
  const pre = proj.preannotation ?? {};
  const slice = pre.slice ?? {};

  const nameIn = el("input", { type: "text", value: proj.name ?? "" });
  const ckptIn = el("input", { type: "text", value: pre.checkpoint ?? "", placeholder: "(vazio = sem pré-anotação)" });
  const confIn = el("input", { type: "number", min: 0, max: 1, step: 0.05, value: pre.conf_threshold ?? 0.25 });
  const iouIn = el("input", { type: "number", min: 0, max: 1, step: 0.05, value: pre.iou_threshold ?? 0.7 });
  const sliceIn = el("input", { type: "number", min: 64, max: 4096, step: 32, value: slice.size ?? 640 });
  const overlapIn = el("input", { type: "number", min: 0, max: 0.9, step: 0.05, value: slice.overlap ?? 0.2 });

  const saveBtn = el("button", {
    class: "btn btn-primary",
    onclick: async () => {
      const body = {
        name: nameIn.value.trim(),
        preannotation: {
          enabled: Boolean(ckptIn.value.trim()),
          checkpoint: ckptIn.value.trim() || null,
          conf_threshold: Number(confIn.value),
          iou_threshold: Number(iouIn.value),
          slice: { size: Number(sliceIn.value), overlap: Number(overlapIn.value) },
        },
      };
      try {
        await api.patchProject(slug, body);
        root.prepend(el("div", { class: "alert alert-info", text: "Configurações salvas." }));
      } catch (err) {
        // 409 aqui normalmente é checkpoint com model.names incompatível.
        showError(root, err);
      }
    },
  }, ["Salvar"]);

  root.append(el("section", { class: "card settings-form" }, [
    el("label", {}, ["Nome", nameIn]),
    el("label", {}, ["Slug (imutável)", el("input", { type: "text", value: proj.slug ?? slug, disabled: true })]),
    el("h3", { text: "Pré-anotação" }),
    el("label", {}, ["Checkpoint (.pt)", ckptIn]),
    el("div", { class: "field-row" }, [
      el("label", {}, ["conf", confIn]),
      el("label", {}, ["iou", iouIn]),
      el("label", {}, ["slice", sliceIn]),
      el("label", {}, ["overlap", overlapIn]),
    ]),
    el("p", { class: "muted", text: "Trocar o checkpoint exige model.names prefixo-compatível com as classes atuais (o backend devolve 409 em divergência)." }),
    el("h3", { text: "Classes (somente-leitura)" }),
    el("p", { class: "muted", text: (proj.classes ?? []).map((c, i) => `${i}:${typeof c === "string" ? c : c.name}`).join("  ") || "—" }),
    el("p", { class: "muted", text: "Gerencie classes na aba Classes (append-only)." }),
    el("div", { class: "toolbar" }, [saveBtn]),
  ]));
}
