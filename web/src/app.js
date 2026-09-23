// Entry do app shell: roteamento por hash e bootstrap.
// Rotas:  #/            dashboard
//         #/new         wizard de criação (3 passos)
//         #/p/:slug     página do projeto (aba padrão: anotar)
//         #/p/:slug/:tab  anotar | imagens | classes | importar | jobs | config
import { el, clear, showError } from "./ui.js";
import { ensureApiKey, clearApiKey } from "./auth.js";
import { renderDashboard } from "./views/dashboard.js";
import { renderWizard } from "./views/wizard.js";
import { renderProject } from "./views/project.js";

if (window.__USE_MOCK__) {
  const m = await import("../mocks/server.js");
  m.installMockServer();
  console.info("[mock] servidor de API simulado ativo");
}

const root = document.getElementById("app");
let cleanupCurrent = null;

function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [pathPart, queryPart] = h.split("?");
  return {
    seg: pathPart.split("/").filter(Boolean).map(decodeURIComponent),
    params: new URLSearchParams(queryPart || ""),
  };
}

function chrome() {
  return el("header", { class: "app-header" }, [
    el("a", { class: "brand", href: "#/" }, ["fly-det · anotação"]),
    el("nav", { class: "app-nav" }, [
      el("a", { href: "#/" }, ["Projetos"]),
      el("a", { href: "#/new" }, ["+ Novo projeto"]),
      el("button", {
        class: "btn btn-link",
        title: "Trocar a chave de API desta sessão",
        onclick: () => { clearApiKey(); ensureApiKey(); },
      }, ["Trocar chave"]),
    ]),
  ]);
}

async function route() {
  if (typeof cleanupCurrent === "function") { cleanupCurrent(); cleanupCurrent = null; }
  const { seg, params } = parseHash();
  clear(root);
  const main = el("main", { class: "app-main" });
  root.append(chrome(), main);
  try {
    if (seg.length === 0) {
      await renderDashboard(main);
    } else if (seg[0] === "new") {
      await renderWizard(main);
    } else if (seg[0] === "p" && seg[1]) {
      cleanupCurrent = await renderProject(main, seg[1], seg[2] || "anotar", params) || null;
    } else {
      main.append(el("p", { text: "Rota desconhecida." }));
    }
  } catch (err) {
    console.error(err);
    showError(main, err);
  }
}

window.addEventListener("hashchange", route);
route();
