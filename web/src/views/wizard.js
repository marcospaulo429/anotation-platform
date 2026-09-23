// Wizard de criação de projeto em 3 passos (seção 8):
//  (1) nome/slug (slug kebab-case auto-gerado, editável)
//  (2) caminho: pré-anotar com modelo | manual do zero | importar anotados
//  (3) configuração do caminho escolhido
import { el, clear, showError, kebab } from "../ui.js";
import * as api from "../api.js";

export async function renderWizard(root) {
  const state = {
    step: 1,
    name: "",
    slug: "",
    slugTouched: false,
    path: "model", // model | manual | import
    checkpoint: "",
    conf: 0.25,
    iou: 0.7,
    sliceSize: 640,
    sliceOverlap: 0.2,
    classesText: "",
  };

  function stepsBar() {
    return el("ol", { class: "wizard-steps" }, [
      el("li", { class: state.step === 1 ? "active" : "", text: "1 · Nome" }),
      el("li", { class: state.step === 2 ? "active" : "", text: "2 · Caminho" }),
      el("li", { class: state.step === 3 ? "active" : "", text: "3 · Configuração" }),
    ]);
  }

  function step1() {
    const nameInput = el("input", {
      type: "text", required: true, placeholder: "Ex.: Placas 2026 Q4",
      value: state.name,
      oninput: (e) => {
        state.name = e.target.value;
        if (!state.slugTouched) slugInput.value = kebab(state.name);
      },
    });
    const slugInput = el("input", {
      type: "text", required: true, pattern: "[a-z0-9\\-]+",
      value: state.slug,
      oninput: (e) => { state.slugTouched = true; state.slug = e.target.value; },
    });
    if (!state.slugTouched) slugInput.value = kebab(state.name);
    return el("form", {
      onsubmit: (e) => {
        e.preventDefault();
        state.slug = slugInput.value.trim();
        if (!state.name.trim() || !state.slug) return;
        state.step = 2; draw();
      },
    }, [
      el("label", {}, ["Nome do projeto", nameInput]),
      el("label", {}, ["Slug (identificador, kebab-case)", slugInput]),
      el("div", { class: "wizard-nav" }, [
        el("button", { class: "btn btn-primary", type: "submit" }, ["Próximo →"]),
      ]),
    ]);
  }

  function step2() {
    const opt = (value, title, desc) =>
      el("label", { class: `path-option ${state.path === value ? "selected" : ""}` }, [
        el("input", {
          type: "radio", name: "path", value,
          checked: state.path === value,
          onchange: () => { state.path = value; draw(); },
        }),
        el("strong", { text: title }),
        el("span", { class: "muted", text: desc }),
      ]);
    return el("div", {}, [
      opt("model", "Pré-anotar com modelo", "Checkpoint YOLO gera rascunhos; humano só revisa."),
      opt("manual", "Manual do zero", "Você define as classes e anota tudo à mão."),
      opt("import", "Importar dados já anotados", "Imagens + labels YOLO existentes viram a fonte da verdade."),
      el("div", { class: "wizard-nav" }, [
        el("button", { class: "btn", onclick: () => { state.step = 1; draw(); } }, ["← Voltar"]),
        el("button", { class: "btn btn-primary", onclick: () => { state.step = 3; draw(); } }, ["Próximo →"]),
      ]),
    ]);
  }

  function step3() {
    let body;
    if (state.path === "model") {
      body = el("div", {}, [
        el("label", {}, ["Caminho do checkpoint (.pt)", el("input", {
          type: "text", required: true, placeholder: "/raid/user_marcospaulo/models/best.pt",
          value: state.checkpoint, oninput: (e) => { state.checkpoint = e.target.value; },
        })]),
        el("div", { class: "field-row" }, [
          el("label", {}, ["conf", num("conf", 0, 1, 0.05)]),
          el("label", {}, ["iou", num("iou", 0, 1, 0.05)]),
          el("label", {}, ["slice", num("sliceSize", 64, 4096, 32)]),
          el("label", {}, ["overlap", num("sliceOverlap", 0, 0.9, 0.05)]),
        ]),
        el("p", { class: "alert alert-info", text: "As classes serão lidas do modelo (model.names) e ficam somente-leitura após a criação." }),
      ]);
    } else if (state.path === "manual") {
      body = el("div", {}, [
        el("label", {}, ["Classes (uma por linha — a ORDEM é o índice YOLO)", el("textarea", {
          rows: 7, required: true, placeholder: "MD\nMV\nMC\nMF",
          oninput: (e) => { state.classesText = e.target.value; },
        }, [state.classesText])]),
        el("p", { class: "alert alert-info", text: "A ordem é imutável: reordenar/renomear/remover depois é bug silencioso. Novas classes só entram no final." }),
      ]);
    } else {
      body = el("div", {}, [
        el("p", { class: "alert alert-info", text: "Após criar o projeto, use a aba Importar/Exportar para apontar os diretórios de imagens e labels (com validação dry-run antes de gravar)." }),
      ]);
    }
    return el("div", {}, [
      body,
      el("div", { class: "wizard-nav" }, [
        el("button", { class: "btn", onclick: () => { state.step = 2; draw(); } }, ["← Voltar"]),
        el("button", { class: "btn btn-primary", onclick: submit }, ["Criar projeto"]),
      ]),
    ]);
  }

  function num(key, min, max, step) {
    return el("input", {
      type: "number", min, max, step, value: state[key],
      oninput: (e) => { state[key] = Number(e.target.value); },
    });
  }

  async function submit() {
    const body = { name: state.name.trim(), slug: state.slug.trim() };
    if (state.path === "model") {
      body.preannotation = {
        enabled: true,
        checkpoint: state.checkpoint.trim(),
        conf_threshold: state.conf,
        iou_threshold: state.iou,
        slice: { size: state.sliceSize, overlap: state.sliceOverlap },
      };
    } else if (state.path === "manual") {
      body.classes = state.classesText.split("\n").map((s) => s.trim()).filter(Boolean);
      body.preannotation = { enabled: false };
    } else {
      body.preannotation = { enabled: false };
    }
    try {
      await api.createProject(body);
      location.hash = state.path === "import"
        ? `#/p/${encodeURIComponent(body.slug)}/importar`
        : `#/p/${encodeURIComponent(body.slug)}`;
    } catch (err) {
      showError(root, err);
    }
  }

  function draw() {
    clear(root);
    root.append(
      el("h1", { text: "Novo projeto" }),
      stepsBar(),
      state.step === 1 ? step1() : state.step === 2 ? step2() : step3(),
    );
  }
  draw();
}
