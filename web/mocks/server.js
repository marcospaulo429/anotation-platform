// Servidor de API simulado para desenvolvimento do app shell SEM backend.
// Ative abrindo web/index.html?mock — faz monkeypatch de window.fetch e
// implementa um subconjunto dos contratos da seção 7 em memória.
// Não é usado em produção.

const state = {
  projects: new Map(), // slug -> {project, classes[], images[], drafts{}, jobs[], exports[]}
};

function seed(slug = "demo-placas") {
  const images = [];
  for (let i = 1; i <= 12; i++) {
    images.push({
      name: `IMG_${String(i).padStart(4, "0")}.jpg`,
      status: i <= 4 ? "prelabeled" : i <= 9 ? "unlabeled" : "done",
    });
  }
  state.projects.set(slug, {
    project: {
      name: "Placas Demo", slug, image_width: 1920, image_height: 1080,
      classes: ["MD", "MV", "MC", "MF"],
      preannotation: { enabled: true, checkpoint: "/raid/demo/best.pt", conf_threshold: 0.25, iou_threshold: 0.7, slice: { size: 640, overlap: 0.2 } },
    },
    classes: ["MD", "MV", "MC", "MF"],
    images,
    drafts: new Map(),
    jobs: [],
    exports: [],
  });
}

function svgMarkup(text, w = 320, h = 180) {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">` +
    `<rect width="100%" height="100%" fill="#3a3f4a"/>` +
    `<text x="50%" y="50%" fill="#cfd6e4" font-family="monospace" font-size="${Math.max(12, w / 20)}" text-anchor="middle" dominant-baseline="middle">${text}</text>` +
    `</svg>`
  );
}
const svgResponse = (text, w, h) =>
  Promise.resolve(new Response(svgMarkup(text, w, h), {
    status: 200, headers: { "Content-Type": "image/svg+xml" },
  }));

function fakeBoxes(seedStr) {
  // Caixas determinísticas derivadas do nome, origem "model".
  let h = 0;
  for (const c of seedStr) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  const n = 3 + (h % 4);
  const boxes = [];
  for (let i = 0; i < n; i++) {
    const r = (k) => ((h >> (k * 3)) % 1000) / 1000;
    boxes.push({
      id: `mock-${seedStr}-${i}`,
      cls: (h + i) % 4,
      cx: 0.1 + 0.8 * r(i), cy: 0.1 + 0.8 * r(i + 5),
      w: 0.02 + 0.03 * r(i + 9), h: 0.03 + 0.04 * r(i + 13),
      origin: "model", model_conf: 0.5 + 0.49 * r(i + 17), edited: false, edit_ops: [],
    });
  }
  return boxes;
}

const json = (data, status = 200) =>
  Promise.resolve(new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json" },
  }));
const notFound = () => json({ detail: "mock: não encontrado" }, 404);

function route(method, path, url, body) {
  const parts = path.split("/").filter(Boolean); // ["projects", slug, ...]
  if (parts[0] !== "projects") return notFound();

  // /projects
  if (parts.length === 1) {
    if (method === "GET") {
      return json([...state.projects.values()].map((p) => {
        const done = p.images.filter((i) => i.status === "done").length;
        return { slug: p.project.slug, name: p.project.name, total_images: p.images.length, done, last_export: p.exports.at(-1)?.version ?? null };
      }));
    }
    if (method === "POST") {
      const slug = body.slug;
      if (state.projects.has(slug)) return json({ detail: "slug já existe" }, 409);
      state.projects.set(slug, {
        project: {
          name: body.name, slug, image_width: 1920, image_height: 1080,
          classes: body.classes ?? ["MD", "MV", "MC", "MF"],
          preannotation: body.preannotation ?? { enabled: false },
        },
        classes: body.classes?.length ? [...body.classes] : ["MD", "MV", "MC", "MF"],
        images: [], drafts: new Map(), jobs: [], exports: [],
      });
      return json({ slug }, 201);
    }
    return notFound();
  }

  const p = state.projects.get(parts[1]);
  if (!p) return notFound();
  const rest = parts.slice(2);

  // /projects/{slug}
  if (rest.length === 0) {
    if (method === "GET") return json({ ...p.project, classes: [...p.classes] });
    if (method === "PATCH") {
      Object.assign(p.project, body ?? {});
      return json(p.project);
    }
  }
  // /classes
  if (rest[0] === "classes") {
    if (method === "GET") return json({ classes: [...p.classes] });
    if (method === "POST") {
      p.classes.push(body.name);
      p.project.classes = [...p.classes];
      return json({ classes: [...p.classes] }, 201);
    }
  }
  // /images
  if (rest[0] === "images" && rest.length === 1) {
    if (method === "GET") {
      const status = url.searchParams.get("status");
      const items = p.images.filter((i) => !status || i.status === status);
      return json({ images: items, next_cursor: null });
    }
    if (method === "POST") return json({ uploaded: 0 }); // multipart real não simulado
  }
  if (rest[0] === "images" && rest.length >= 3) {
    const img = rest[1];
    if (rest[2] === "thumb") return svgResponse(img);
    if (rest[2] === "full") return svgResponse(img, 1920, 1080);
    if (rest[2] === "tiles") return svgResponse(`tile ${rest[3]},${rest[4]}`, 640, 640);
  }
  // /labels/{img}
  if (rest[0] === "labels" && rest.length >= 2) {
    const img = rest[1];
    if (rest.length === 2 && method === "GET") {
      const source = url.searchParams.get("source") ?? "merged";
      const draft = p.drafts.get(img);
      if (source === "draft" && draft) return json(draft);
      return json({ image: img, base_version: `mock-${img}-v1`, boxes: fakeBoxes(img) });
    }
    if (rest[2] === "draft" && method === "PUT") {
      p.drafts.set(img, body);
      const it = p.images.find((i) => i.name === img);
      if (it && it.status !== "done") it.status = "in_review";
      return json({ ok: true });
    }
    if (rest[2] === "commit" && method === "POST") {
      p.drafts.delete(img);
      const it = p.images.find((i) => i.name === img);
      if (it) it.status = "done";
      return json({ ok: true });
    }
    if (rest[2] === "revert" && method === "POST") {
      return json({ image: img, base_version: `mock-${img}-v1`, boxes: fakeBoxes(img) });
    }
  }
  // /preannotate, /jobs, /export, /exports, /stats, /import
  if (rest[0] === "preannotate" && method === "POST") {
    const job = { id: `job-${p.jobs.length + 1}`, type: "preannotate", status: "pending", created_at: new Date().toISOString() };
    p.jobs.push(job);
    return json(job, 202);
  }
  if (rest[0] === "jobs") return json({ jobs: p.jobs });
  if (rest[0] === "export" && method === "POST") {
    const v = `v${p.exports.length + 1}`;
    p.exports.push({ version: v, created_at: new Date().toISOString() });
    return json({ version: v, manifest: { split_strategy: "by_plate", train: 6, val: 2, test: 1 } });
  }
  if (rest[0] === "exports") return json({ exports: p.exports });
  if (rest[0] === "import" && method === "POST") {
    if (body.dry_run) return json({ valid: 10, invalid: 1, errors: [{ file: "IMG_0007.txt", error: "classe 9 fora de faixa" }] });
    return json({ imported: 10 });
  }
  if (rest[0] === "stats") {
    const done = p.images.filter((i) => i.status === "done").length;
    return json({ total: p.images.length, done, correction_rate: 0.31 });
  }
  return notFound();
}

export function installMockServer() {
  seed();
  const realFetch = window.fetch?.bind(window);
  window.fetch = async (input, init = {}) => {
    const u = new URL(typeof input === "string" ? input : input.url, location.origin);
    if (!u.pathname.startsWith("/annotate")) {
      return realFetch ? realFetch(input, init) : Promise.reject(new Error("sem fetch"));
    }
    let body = init.body;
    if (typeof body === "string") { try { body = JSON.parse(body); } catch { /* form-data */ } }
    const res = route(init.method ?? "GET", u.pathname.replace(/^\/annotate/, ""), u, body);
    console.info("[mock-api]", init.method ?? "GET", u.pathname + u.search);
    return res;
  };
}
