// Aba Classes: lista ordenada (índice = índice YOLO, nome, cor, contagem se
// disponível) + botão "adicionar classe" SEMPRE no final, com confirmação de
// irreversibilidade. Não existe UI de reordenar/remover (append-only, §4.1).
import { el, clear, showError, classColor, confirmDialog } from "../ui.js";
import * as api from "../api.js";

export async function renderClasses(root, slug, project) {
  clear(root);
  root.append(el("h2", { text: "Classes" }));

  let classes = [];
  let boxCounts = {};
  try {
    const res = await api.listClasses(slug);
    classes = Array.isArray(res) ? res : res.classes ?? [];
  } catch {
    classes = project?.classes ?? [];
  }
  const stats = await api.getStats(slug).catch(() => null);
  boxCounts = stats?.boxes_per_class ?? {};

  const list = el("table", { class: "table" }, [
    el("thead", {}, [el("tr", {}, [
      el("th", { text: "#" }), el("th", { text: "Cor" }),
      el("th", { text: "Nome" }), el("th", { text: "Caixas" }),
    ])]),
    el("tbody", {}, classes.map((c, i) => {
      const name = typeof c === "string" ? c : c.name;
      return el("tr", {}, [
        el("td", { text: String(i) }),
        el("td", {}, [el("span", { class: "swatch", style: { background: classColor(i) } })]),
        el("td", { text: name }),
        el("td", { text: boxCounts[name] != null ? String(boxCounts[name]) : "—" }),
      ]);
    })),
  ]);

  const nameInput = el("input", { type: "text", placeholder: "Nome da nova classe (entra no final)" });
  const addBtn = el("button", {
    class: "btn btn-primary",
    onclick: async () => {
      const name = nameInput.value.trim();
      if (!name) return;
      const ok = await confirmDialog(
        `Adicionar "${name}" como classe #${classes.length}? Esta ação é IRREVERSÍVEL: classes são append-only e nunca podem ser reordenadas, renomeadas ou removidas.`,
        { danger: true, confirmText: "Adicionar no final" },
      );
      if (!ok) return;
      try {
        await api.addClass(slug, name);
        renderClasses(root, slug, project);
      } catch (err) {
        showError(root, err);
      }
    },
  }, ["Adicionar classe"]);

  root.append(
    el("p", { class: "alert alert-info", text: "A ordem abaixo é o índice YOLO. Reordenar, renomear ou remover não existe nesta UI — novas classes só entram no final." }),
    list,
    el("div", { class: "toolbar" }, [nameInput, addBtn]),
  );
}
