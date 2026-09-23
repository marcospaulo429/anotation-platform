// Gestão da chave de API (header X-API-Key). Pedida uma vez e guardada
// em sessionStorage (some ao fechar a aba — não persiste em disco).
const KEY = "anno.apiKey";
const USER = "anno.user";

export function getApiKey() {
  return sessionStorage.getItem(KEY);
}

export function ensureApiKey() {
  let k = getApiKey();
  if (!k) {
    k = window.prompt("Informe a chave de API (X-API-Key):");
    if (k) sessionStorage.setItem(KEY, k.trim());
  }
  return k;
}

export function clearApiKey() {
  sessionStorage.removeItem(KEY);
}

export function getUserName() {
  let u = localStorage.getItem(USER);
  if (!u) {
    u = window.prompt("Seu nome/usuário (para auditoria de rascunhos):") || "web";
    localStorage.setItem(USER, u.trim());
  }
  return u;
}
