// Single-page front end. Routes: #/  #/kuesioner  #/hasil  #/pekerjaan/<kode>
"use strict";

const view = document.getElementById("view");
const SESSION_KEY = "crs_session";
// A typical session is 20 questions plus 8 repeated ones; the bar fills against that and then stays full.
const TYPICAL_LENGTH = 28;

function savedSession() {
  try { return localStorage.getItem(SESSION_KEY); } catch (e) { return null; }
}
function saveSession(id) {
  try { id ? localStorage.setItem(SESSION_KEY, id) : localStorage.removeItem(SESSION_KEY); } catch (e) { /* private mode */ }
}

async function api(path, options) {
  const res = await fetch("/api" + path, options && {
    method: options.method || "POST",
    headers: { "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error(typeof data.detail === "string" ? data.detail : "Terjadi kesalahan");
    err.status = res.status;
    throw err;
  }
  return data;
}

// el("p", {class: "muted"}, "text", childNode, ...) - all text goes through textContent.
function el(tag, attrs, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const child of children.flat()) {
    if (child != null && child !== false) node.append(child);
  }
  return node;
}

function show(...nodes) {
  view.replaceChildren(...nodes.flat().filter(Boolean));
  window.scrollTo(0, 0);
}

function showError(err) {
  show(el("h1", null, "Ada masalah"),
       el("p", { class: "error" }, err.message),
       el("a", { class: "btn", href: "#/" }, "Kembali ke awal"));
}

// ---------------------------------------------------------------- home
async function home() {
  let resumable = false;
  const id = savedSession();
  if (id) {
    try { resumable = !(await api("/sessions/" + id)).done; } catch (e) { saveSession(null); }
  }

  const zone = el("select", { id: "zone" },
    el("option", { value: "" }, "Belum tahu / tampilkan semua"),
    el("option", { value: "2" }, "Lulus SMA/SMK lalu bekerja atau pelatihan singkat"),
    el("option", { value: "3" }, "Sampai D3 atau pelatihan vokasi"),
    el("option", { value: "4" }, "Sampai S1"),
    el("option", { value: "5" }, "Sampai S2/S3"));

  const start = el("button", { class: "btn", onclick: async () => {
    start.disabled = true;
    try {
      const state = await api("/sessions", { body: { max_job_zone: zone.value ? Number(zone.value) : null } });
      saveSession(state.session_id);
      location.hash = "#/kuesioner";
    } catch (err) { showError(err); }
  } }, "Mulai");

  show(
    el("h1", null, "Temukan karier yang sesuai dengan minatmu"),
    el("p", { class: "muted" }, "Jawab beberapa pertanyaan tentang kegiatan yang kamu sukai. Setiap jawabanmu menentukan pertanyaan berikutnya."),
    el("div", { class: "card" },
      el("ol", { class: "steps" },
        el("li", null, "Sekitar 30 pertanyaan, 5 sampai 10 menit."),
        el("li", null, "Tidak ada jawaban benar atau salah. Jawab sesuai yang kamu rasakan."),
        el("li", null, "Jangan pikirkan gaji atau pendidikan yang dibutuhkan."),
        el("li", null, "Kami tidak meminta nama. Jawabanmu disimpan tanpa identitas.")),
      el("label", { for: "zone" }, "Rencana pendidikanmu"),
      zone,
      el("p", { class: "muted", style: "margin-top:8px;font-size:0.9rem" },
        "Dipakai untuk menyaring pekerjaan yang butuh pendidikan lebih tinggi dari rencanamu."),
      el("div", { class: "below" }, start,
        resumable && el("a", { class: "btn ghost", href: "#/kuesioner" }, "Lanjutkan yang tadi"))));
}

// ---------------------------------------------------------------- questionnaire
async function questionnaire() {
  const id = savedSession();
  if (!id) { location.hash = "#/"; return; }
  let state;
  try { state = await api("/sessions/" + id); } catch (err) { saveSession(null); showError(err); return; }
  renderQuestion(state);
}

function renderQuestion(state) {
  if (state.done) { location.hash = "#/hasil"; return; }
  const q = state.question;
  let busy = false;

  async function choose(value) {
    if (busy) return;
    busy = true;
    buttons.forEach((b) => { b.disabled = true; });
    try {
      renderQuestion(await api(`/sessions/${state.session_id}/answers`,
        { body: { kind: q.kind, index: q.index, repeat: q.repeat, value } }));
    } catch (err) {
      // 409 = this page was stale (double click, second tab): reload the real current question.
      if (err.status === 409) questionnaire(); else showError(err);
    }
  }

  const buttons = state.responses.map((label, value) =>
    el("button", { class: "choice", onclick: () => choose(value) },
      el("span", { class: "key" }, String(value + 1)), label));

  const finish = state.can_finish && el("button", { class: "btn ghost", onclick: async () => {
    try { await api(`/sessions/${state.session_id}/finish`, {}); location.hash = "#/hasil"; }
    catch (err) { showError(err); }
  } }, "Selesai sekarang dan lihat hasil");

  show(
    el("div", { class: "progress", role: "progressbar", "aria-label": "Kemajuan" },
      el("div", { style: `width:${Math.min(100, (state.answered / TYPICAL_LENGTH) * 100)}%` })),
    el("p", { class: "muted", style: "font-size:0.9rem" }, `Pertanyaan ${q.number}`),
    el("span", { class: "chip" }, q.label),
    el("p", { class: "prompt" }, q.prompt),
    el("p", { class: "qtext" }, q.text),
    el("div", { class: "choices" }, buttons),
    el("div", { class: "below" }, el("span", { class: "muted", style: "font-size:0.85rem" }, "Bisa juga tekan angka 1 sampai 5"), finish));

  keyHandler = (e) => {
    const n = Number(e.key);
    if (n >= 1 && n <= state.responses.length) choose(n - 1);
  };
}

let keyHandler = null;
document.addEventListener("keydown", (e) => {
  if (keyHandler && location.hash === "#/kuesioner" && !e.ctrlKey && !e.metaKey && !e.altKey) keyHandler(e);
});

// ---------------------------------------------------------------- result
function occupationCard(r, rank) {
  return el("div", { class: "card" },
    el("h3", null, rank && el("span", { class: "rank" }, rank + "."),
      el("a", { href: "#/pekerjaan/" + r.code }, r.title)),
    el("p", null, r.description),
    el("p", { class: "meta" }, el("b", null, "Persiapan: "), r.job_zone_name),
    el("p", { class: "meta" }, el("b", null, "Perlu dikembangkan: "), r.skills.join(", ")),
    el("p", { class: "meta" }, el("b", null, "Karier serupa: "),
      r.related.flatMap((o, i) => [i ? ", " : "", el("a", { href: "#/pekerjaan/" + o.code }, o.title)])),
    el("p", { style: "margin:12px 0 0" }, el("a", { href: "#/pekerjaan/" + r.code }, "Lihat detail")));
}

async function result() {
  const id = savedSession();
  if (!id) { location.hash = "#/"; return; }
  let res;
  try { res = await api(`/sessions/${id}/result`); }
  catch (err) {
    if (err.status === 409) { location.hash = "#/kuesioner"; return; }
    showError(err); return;
  }
  const notes = res.notes.map((t) => el("p", null, t));
  const special = res.outcome !== "jelas";
  show(
    el("h1", null, res.headline),
    special
      ? el("div", { class: "notice" }, notes,
          res.liked_areas.length > 0 && el("div", null, el("p", { style: "margin:10px 0 0" }, "Bidang yang kamu sukai:"),
            el("ul", { class: "tags" }, res.liked_areas.map((a) => el("li", null, a)))))
      : notes.map((n) => { n.className = "muted"; return n; }),
    el("p", { class: "muted", style: "font-size:0.9rem;margin-top:12px" },
      `Dihitung dari ${res.answered} jawaban` + (res.repeated ? ` dan ${res.repeated} pertanyaan ulang.` : ".")),
    res.recommendations.map((r, i) => occupationCard(r, i + 1)),
    el("div", { class: "below" },
      el("button", { class: "btn ghost", onclick: () => { saveSession(null); location.hash = "#/"; } }, "Ulangi dari awal")));
}

// ---------------------------------------------------------------- occupation detail
async function occupation(code) {
  let o;
  try { o = await api("/occupations/" + encodeURIComponent(code)); } catch (err) { showError(err); return; }
  show(
    el("p", null, el("a", { href: savedSession() ? "#/hasil" : "#/" }, "← Kembali")),
    el("h1", null, o.title),
    el("p", { class: "muted", style: "font-size:0.9rem;margin-top:-6px" }, `Nama di O*NET: ${o.title_en} (${o.code})`),
    el("p", null, o.description),
    el("div", { class: "card" },
      el("p", { class: "meta", style: "margin-top:0" }, el("b", null, "Persiapan: "), o.job_zone_name),
      el("p", { class: "meta" }, el("b", null, "Tipe minat utama: "), o.interests.join(", ")),
      el("p", { class: "meta" }, el("b", null, "Bidang minat terkuat: "), o.areas.join(", "))),
    el("h2", null, "Kompetensi yang penting"),
    el("p", { class: "muted", style: "font-size:0.9rem" },
      "Tingkat menunjukkan seberapa tinggi penguasaan yang dituntut pekerjaan ini, pada skala 0 sampai 7."),
    el("table", null,
      el("thead", null, el("tr", null, el("th", null, "Kompetensi"), el("th", { class: "num" }, "Tingkat"))),
      el("tbody", null, o.skills.map((s) =>
        el("tr", null, el("td", null, s.name), el("td", { class: "num" }, s.level.toFixed(1) + " / 7"))))),
    el("h2", null, "Karier serupa"),
    el("ul", { class: "tags" }, o.related.map((r) =>
      el("li", null, el("a", { href: "#/pekerjaan/" + r.code }, r.title)))));
}

// ---------------------------------------------------------------- router
function route() {
  keyHandler = null;
  const hash = location.hash || "#/";
  if (hash === "#/kuesioner") questionnaire();
  else if (hash === "#/hasil") result();
  else if (hash.startsWith("#/pekerjaan/")) occupation(decodeURIComponent(hash.slice("#/pekerjaan/".length)));
  else home();
}
window.addEventListener("hashchange", route);
route();
