"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
let S = null;          // app state from the server
let P = null;          // current product
let polling = null;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function pct(x) { return Math.round(100 * (x || 0)) + "%"; }
function store(k, v) { try { localStorage.setItem("atlas." + k, JSON.stringify(v)); } catch (e) {} }
function recall(k, d) { try { const v = localStorage.getItem("atlas." + k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
function toast(msg, ms = 2600) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), ms);
}
async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ("Error " + r.status));
  return data;
}
async function safe(fn) { try { return await fn(); } catch (e) { toast(e.message, 6000); } }

// --- start ------------------------------------------------------------------------
async function loadState() {
  S = await api("/api/state");
  renderBanner();
  const sel = $("#product-select");
  const want = recall("product", S.products[0]?.slug);
  sel.innerHTML = S.products.map(p => `<option value="${esc(p.slug)}">${esc(p.name)}</option>`).join("");
  if (S.products.some(p => p.slug === want)) sel.value = want;
  fillProviders();
  renderStyles();
  restoreSettings();
  if (sel.value) await loadProduct(sel.value);
  if (S.job && S.job.status === "running") startPolling();
  else if (S.job && S.job.slug === sel.value && S.job.status !== "done") renderJob(S.job);
}

function renderBanner() {
  const b = $("#banner");
  let html = "";
  if (!S.gemini_key) {
    html += `<section class="card"><h2>👋 First, add your Gemini API key</h2>
      <p class="hint">Atlas uses Google Gemini to write and test the pages. Get a free key at
      <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a>,
      paste it here, and press Save. It stays on this computer.</p>
      <form class="row" id="first-key"><input type="password" id="first-key-val" placeholder="Paste your key" style="flex:1" autocomplete="off">
      <button class="primary">Save</button></form></section>`;
  }
  if (!S.deps.fpdf) {
    html += `<section class="card"><b>PDFs are off.</b> <span class="hint">To get the final page and the report as PDF, close Atlas and run
      <code>pip install -r requirements.txt</code> (or start Atlas with "Start Atlas.bat", which does it for you).</span></section>`;
  }
  b.innerHTML = html;
  const f = $("#first-key");
  if (f) f.onsubmit = e => {
    e.preventDefault();
    safe(async () => { await api("/api/key", { env: "GEMINI_API_KEY", value: $("#first-key-val").value }); toast("Key saved"); await loadState(); });
  };
}

function fillProviders() {
  const opts = Object.entries(S.providers).map(([id, p]) => `<option value="${esc(id)}">${esc(p.label)}${p.has_key ? "" : " (no key yet)"}</option>`).join("");
  for (const [sel, input, list] of [["#s-writer", "#s-writer-model", "#writer-models"], ["#s-judge", "#s-judge-model", "#judge-models"], ["#imp-provider", "#imp-model", "#imp-models"]]) {
    const s = $(sel);
    const prev = s.value;
    s.innerHTML = opts;
    if (prev && S.providers[prev]) s.value = prev;
    const sync = (reset) => {
      const p = S.providers[s.value];
      $(list).innerHTML = (p?.models || []).map(m => `<option value="${esc(m)}">`).join("");
      if (reset || !$(input).value) $(input).value = p?.models?.[0] || "";
    };
    s.onchange = () => { sync(true); saveSettings(); };
    sync(false);
  }
}

function renderStyles() {
  $("#s-styles").innerHTML = S.styles.map(s =>
    `<label title="${s.publishable ? "" : "Lab test only, never published"}"><input type="checkbox" value="${esc(s.id)}"> ${esc(s.name)}</label>`).join("");
  $$("#s-styles input").forEach(i => i.onchange = saveSettings);
}

// --- settings of a run -------------------------------------------------------------
function gather() {
  return {
    discovery: $("#s-discovery").checked,
    writer: $("#s-writer").value, writer_model: $("#s-writer-model").value.trim(),
    judge: $("#s-judge").value, judge_model: $("#s-judge-model").value.trim(),
    styles: $$("#s-styles input:checked").map(i => i.value),
    words: +$("#s-words").value || 400, repeats: +$("#s-repeats").value || 1,
    top_k: +$("#s-topk").value || 5, fresh_pages: $("#s-fresh").checked,
    retries: $("#s-retries").value === "" ? 3 : +$("#s-retries").value,
    retrieval: $("#s-retrieval").value || "page",
  };
}
let restoring = false;
function restoreSettings() {
  restoring = true;
  try { applySettings({ ...S.defaults, ...recall("settings", {}) }); } finally { restoring = false; }
}
function applySettings(s) {
  $("#s-discovery").checked = !!s.discovery;
  for (const [sel, input, pk, mk] of [["#s-writer", "#s-writer-model", "writer", "writer_model"], ["#s-judge", "#s-judge-model", "judge", "judge_model"]]) {
    if (S.providers[s[pk]]) { $(sel).value = s[pk]; $(sel).onchange(); }
    if (s[mk]) $(input).value = s[mk];
  }
  $$("#s-styles input").forEach(i => i.checked = s.styles.includes(i.value));
  $("#s-words").value = s.words; $("#s-repeats").value = s.repeats; $("#s-topk").value = s.top_k;
  $("#s-fresh").checked = !!s.fresh_pages;
  $("#s-retries").value = s.retries ?? 3;
  $("#s-retrieval").value = s.retrieval === "passage" ? "passage" : "page";
}
function saveSettings() { if (restoring) return; store("settings", gather()); estimate(); }
["#s-discovery", "#s-writer-model", "#s-judge-model", "#s-words", "#s-repeats", "#s-topk", "#s-fresh", "#s-retries", "#s-retrieval"]
  .forEach(s => $(s).addEventListener("change", saveSettings));

function estimate() {
  if (!P || !S) return;
  const s = gather();
  const nq = P.questions.filter(q => q.enabled).length;
  const ns = s.styles.length;
  const targets = ns + P.pages.danfoss;
  const search = s.discovery ? nq : 0;
  const judge = targets * nq * s.repeats;
  const calls = search + ns + judge;
  const wait = q => (S.providers[q]?.sleep || 0) + 3;
  const secs = search * 9 + ns * wait(s.writer) * 2 + judge * wait(s.judge);
  const mins = Math.max(1, Math.round(secs / 60));
  let txt = `${nq} questions × ${targets} page versions → about <b>${calls} AI calls</b>, roughly ${mins} min. Answers already saved are free.`;
  if (calls > 200 && (s.judge === "gemini" || s.writer === "gemini")) txt += `<br><span style="color:var(--warn)">This may hit Gemini's free daily limit. If it does, press Run again tomorrow: it continues where it stopped.</span>`;
  $("#estimate").innerHTML = txt;
  $("#discovery-hint").textContent = s.discovery
    ? `On: asks Google's AI all ${nq} questions and imports the pages it cites as the competition (+${nq} searches).`
    : `Off: faster, uses the ${P.pages.competitors} competitor pages saved earlier.`;
}

// --- product ----------------------------------------------------------------------
async function loadProduct(slug) {
  P = await api("/api/product?slug=" + encodeURIComponent(slug));
  store("product", slug);
  $("#f-type").value = P.product.product_type || "";
  $("#f-app").value = P.product.application || "";
  $("#fact-sheet").textContent = P.fact_sheet_error ? "Problem with the fact sheet:\n" + P.fact_sheet_error : P.fact_sheet;
  const pg = P.pages;
  $("#pages-hint").innerHTML = `Comparison pages saved: <b>${pg.competitors}</b> competitor, <b>${pg.danfoss}</b> current Danfoss` +
    (pg.competitors < 2 ? ` · <span style="color:var(--warn)">too few: switch on “Find fresh sources” for the first run</span>` : "");
  renderQuestions();
  renderResults();
  estimate();
  resetPageTabs();
}
$("#product-select").onchange = e => safe(() => loadProduct(e.target.value));
for (const [id, key] of [["#f-type", "product_type"], ["#f-app", "application"]]) {
  $(id).addEventListener("change", e => safe(async () => {
    await api("/api/product/update", { slug: P.product.slug, [key]: e.target.value });
    await loadProduct(P.product.slug); toast("Saved: the standard questions now use this");
  }));
}

// --- questions --------------------------------------------------------------------
function renderQuestions() {
  const std = P.questions.filter(q => q.kind === "standard");
  const own = P.questions.filter(q => q.kind === "custom");
  const item = q => `<li class="${q.enabled ? "" : "off"}"><input type="checkbox" data-id="${esc(q.id)}" ${q.enabled ? "checked" : ""} aria-label="Use this question">
    <span>${esc(q.text)}</span>${q.kind === "custom" ? `<button class="x" title="Delete" data-del="${esc(q.id)}">✕</button>` : ""}</li>`;
  $("#q-standard").innerHTML = std.map(item).join("") || `<li class="empty">No standard questions. Add one below.</li>`;
  $("#q-custom").innerHTML = own.map(item).join("") || `<li class="empty">None yet. Add one below.</li>`;
  const n = P.questions.filter(q => q.enabled).length;
  $("#q-count").textContent = `${n} of ${P.questions.length} selected`;
  $$(".qlist input[type=checkbox]").forEach(c => c.onchange = () => {
    P.questions.find(q => q.id === c.dataset.id).enabled = c.checked;
    renderQuestions(); saveSelection();
  });
  $$(".qlist [data-del]").forEach(b => b.onclick = () => safe(async () => {
    await api("/api/questions/delete", { slug: P.product.slug, id: b.dataset.del, kind: "custom" });
    await loadProduct(P.product.slug);
  }));
  estimate();
}
let selTimer = null;
function saveSelection() {
  clearTimeout(selTimer);
  selTimer = setTimeout(() => safe(() => api("/api/questions/select",
    { slug: P.product.slug, enabled: P.questions.filter(q => q.enabled).map(q => q.id) })), 300);
}
$$("[data-all],[data-none]").forEach(a => a.onclick = e => {
  e.preventDefault();
  const kind = a.dataset.all || a.dataset.none;
  P.questions.filter(q => q.kind === kind).forEach(q => q.enabled = !!a.dataset.all);
  renderQuestions(); saveSelection();
});
$("#q-add").onsubmit = e => {
  e.preventDefault();
  const text = $("#q-text").value.trim();
  if (!text) return toast("Type a question first");
  const scope = $("input[name=scope]:checked").value;
  safe(async () => {
    await api("/api/questions/add", { slug: P.product.slug, text, scope });
    $("#q-text").value = "";
    toast(scope === "standard" ? "Added for all products" : "Added for this product");
    S = await api("/api/state");
    await loadProduct(P.product.slug);
  });
};

// --- run & progress ---------------------------------------------------------------
$("#run").onclick = () => safe(async () => {
  const s = gather();
  if (!P.questions.some(q => q.enabled)) return toast("Tick at least one question");
  if (!s.styles.length) return toast("Tick at least one page version");
  saveSettings();
  await api("/api/run", { slug: P.product.slug, settings: s });
  startPolling();
});
$("#stop").onclick = () => safe(async () => { await api("/api/stop", {}); toast("Stopping after the current step…"); });

function startPolling() {
  $("#card-progress").classList.remove("hidden");
  $("#run").disabled = true;
  clearInterval(polling);
  const tick = async () => {
    const job = await api("/api/job").catch(() => null);
    if (!job) return;
    renderJob(job);
    if (job.status !== "running") {
      clearInterval(polling); polling = null;
      $("#run").disabled = false;
      if (job.status === "done") {
        toast("Done! Your files are ready.");
        await loadProduct(job.slug);
        $("#card-results").scrollIntoView({ behavior: "smooth" });
      }
    }
  };
  tick();
  polling = setInterval(tick, 1500);
}
function renderJob(job) {
  $("#card-progress").classList.remove("hidden");
  const label = { running: "", done: "✔ ", error: "⚠ ", cancelled: "■ " }[job.status] || "";
  $("#p-step").textContent = label + (job.status === "error" ? "Stopped with a problem" : job.status === "cancelled" ? "Stopped" : job.step);
  const frac = job.status === "done" ? 1 : job.total ? job.done / job.total : 0;
  $("#p-bar").style.width = Math.round(100 * frac) + "%";
  const m = Math.floor(job.elapsed / 60), sec = job.elapsed % 60;
  $("#p-detail").textContent = (job.total ? `${job.done} of ${job.total} · ` : "") + `${m}:${String(sec).padStart(2, "0")} elapsed`;
  $("#stop").classList.toggle("hidden", job.status !== "running");
  $("#p-error").classList.toggle("hidden", !job.error);
  $("#p-error").textContent = job.error || "";
  const log = $("#p-log"); const atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
  log.textContent = job.log.join("\n");
  if (atEnd) log.scrollTop = log.scrollHeight;
}

// --- results ----------------------------------------------------------------------
function fileUrl(run, name, dl) { return `/files/${encodeURIComponent(P.product.slug)}/runs/${encodeURIComponent(run)}/${encodeURIComponent(name)}${dl ? "?download=1" : ""}`; }
function renderResults() {
  const done = P.runs.filter(r => !r.unfinished);
  const r = done[0];
  if (!r) {
    $("#latest").innerHTML = `<p class="hint">No results yet. Pick the questions and press <b>Run</b>: the best version of the page and a report will appear here.</p>`;
  } else {
    const f = r.files || {};
    const b = r.baseline;
    $("#latest").innerHTML = `<div class="win">
      <div class="label">Best version to publish · run ${esc(r.run)}</div>
      <div class="title">${esc(r.winner.name)}</div>
      <div class="stats">
        <div><b>${pct(r.winner.share)}</b><span>citation share</span></div>
        <div><b>${pct(r.winner.cited)}</b><span>answers citing it</span></div>
        <div><b>${pct(r.winner.first)}</b><span>cited first</span></div>
        ${b ? `<div><b>${pct(b.share)}</b><span>current Danfoss page</span></div>` : ""}
      </div>
      ${r.check_numbers?.length ? `<div class="warnbox">⚠ Check these numbers before publishing: ${esc(r.check_numbers.join(", "))}. They are not in the fact sheet.</div>` : ""}
      <div class="downloads">
        ${f.final_pdf ? `<a class="dl main" href="${fileUrl(r.run, f.final_pdf, 1)}">⬇ Final page (PDF)</a>` : ""}
        ${f.report_pdf ? `<a class="dl" href="${fileUrl(r.run, f.report_pdf, 1)}">⬇ Report (PDF)</a>` : ""}
        <a class="dl" href="${fileUrl(r.run, f.final_md || "final_page.md", 1)}">⬇ Page as text (Markdown)</a>
        <a class="dl" href="${fileUrl(r.run, f.zip || "all_results.zip", 1)}">⬇ Everything (ZIP)</a>
      </div>
      <p class="hint tiny">${f.final_pdf ? `<a href="${fileUrl(r.run, f.final_pdf)}" target="_blank">Open the page</a> · <a href="${fileUrl(r.run, f.report_pdf)}" target="_blank">open the report</a> in a new tab` : `<a href="${fileUrl(r.run, f.report_md || "report.md")}" target="_blank">Open the report</a>`}</p>
    </div>`;
  }
  const older = P.runs.slice(r ? P.runs.indexOf(r) + 1 : 0);
  $("#older").classList.toggle("hidden", !older.length);
  $("#runs").innerHTML = older.map(o => o.unfinished
    ? `<li><span>${esc(o.run)}</span><span class="hint">unfinished</span></li>`
    : `<li><span>${esc(o.run)} · ${esc(o.winner.name)} · ${pct(o.winner.share)}</span>
       <span>${o.files.final_pdf ? `<a href="${fileUrl(o.run, o.files.final_pdf, 1)}">page</a> · <a href="${fileUrl(o.run, o.files.report_pdf, 1)}">report</a> · ` : ""}<a href="${fileUrl(o.run, o.files.zip, 1)}">zip</a></span></li>`).join("");
}

// --- settings dialog ----------------------------------------------------------------
$("#open-settings").onclick = () => { renderSettings(); $("#settings").showModal(); };
function renderSettings() {
  const envs = {};
  for (const [id, p] of Object.entries(S.providers)) if (p.key_env) (envs[p.key_env] ||= []).push(p.label);
  $("#keys").innerHTML = Object.entries(envs).map(([env, labels]) => {
    const has = Object.values(S.providers).some(p => p.key_env === env && p.has_key);
    return `<form class="keyrow" data-env="${esc(env)}"><span>${esc(labels.join(", "))}<br><small class="${has ? "ok" : "hint"}">${has ? "✔ key saved" : "no key"}</small></span>
      <input type="password" placeholder="${has ? "•••••••• (paste to replace)" : "paste key"}" autocomplete="off"><button>Save</button></form>`;
  }).join("");
  $$("#keys form").forEach(f => f.onsubmit = e => {
    e.preventDefault();
    safe(async () => { await api("/api/key", { env: f.dataset.env, value: $("input", f).value }); toast("Key saved"); await loadState(); renderSettings(); });
  });
  $("#prov-list").innerHTML = Object.entries(S.providers).map(([id, p]) =>
    `<li><span><b>${esc(p.label)}</b> <small class="hint">${esc(p.base_url)} · ${esc(p.models.join(", "))}</small></span>
     ${id === "gemini" ? `<small class="hint">needed for search</small>` : `<button class="x" data-rm="${esc(id)}" title="Remove">✕</button>`}</li>`).join("");
  $$("#prov-list [data-rm]").forEach(b => b.onclick = () => {
    if (!confirm("Remove this AI from the app?")) return;
    safe(async () => { await api("/api/provider/remove", { id: b.dataset.rm }); await loadState(); renderSettings(); });
  });
  $("#std-manage").innerHTML = S.standard.map(q => `<li><span>${esc(q.text)}</span><button class="x" data-std="${esc(q.id)}" title="Delete for all products">✕</button></li>`).join("");
  $$("#std-manage [data-std]").forEach(b => b.onclick = () => {
    if (!confirm("Delete this standard question for ALL products?")) return;
    safe(async () => { await api("/api/questions/delete", { id: b.dataset.std, kind: "standard" }); await loadState(); renderSettings(); });
  });
}
$("#prov-add").onsubmit = e => {
  e.preventDefault();
  const f = Object.fromEntries(new FormData(e.target));
  safe(async () => { await api("/api/provider/add", f); e.target.reset(); toast("AI added"); await loadState(); renderSettings(); });
};

// --- add product dialog -------------------------------------------------------------
let upload = null;
$("#open-import").onclick = () => {
  upload = null; $("#imp-file").value = ""; $("#drop-text").textContent = "Choose a PDF, Word or text file, or drop it here";
  $("#imp-read").disabled = true; $("#imp-status").textContent = "";
  $("#imp-step1").classList.remove("hidden"); $("#imp-step2").classList.add("hidden");
  $("#import").showModal();
};
function takeFile(file) {
  if (!file) return;
  const r = new FileReader();
  r.onload = () => { upload = { filename: file.name, data: String(r.result).split(",")[1] }; $("#drop-text").textContent = "📄 " + file.name; $("#imp-read").disabled = false; };
  r.readAsDataURL(file);
}
$("#imp-file").onchange = e => takeFile(e.target.files[0]);
const drop = $("#drop");
drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
drop.ondragleave = () => drop.classList.remove("over");
drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); takeFile(e.dataTransfer.files[0]); };
$("#imp-read").onclick = () => safe(async () => {
  $("#imp-read").disabled = true; $("#imp-status").textContent = "Reading the brochure and pulling out the facts… this can take a minute.";
  try {
    const r = await api("/api/import/extract", { ...upload, provider: $("#imp-provider").value, model: $("#imp-model").value });
    const f = $("#imp-step2");
    for (const [k, v] of Object.entries(r.draft)) if (f.elements[k]) f.elements[k].value = v;
    $("#imp-step1").classList.add("hidden"); f.classList.remove("hidden");
  } finally { $("#imp-read").disabled = false; $("#imp-status").textContent = ""; }
});
$("#imp-back").onclick = () => { $("#imp-step2").classList.add("hidden"); $("#imp-step1").classList.remove("hidden"); };
$("#imp-step2").onsubmit = e => {
  e.preventDefault();
  const draft = Object.fromEntries(new FormData(e.target));
  safe(async () => {
    const r = await api("/api/import/save", { draft });
    $("#import").close(); toast("Product created");
    store("product", r.slug);
    await loadState();
  });
};

// --- tabs -----------------------------------------------------------------------------
function showTab(name) {
  $$(".tabs [role=tab]").forEach(b => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  $$(".tab").forEach(t => t.classList.toggle("hidden", t.id !== "tab-" + name));
  store("tab", name);
  if (name === "catalog" && P && !CAT) safe(loadCatalog);
  if (name === "web" && P && !SITE) safe(loadWeb);
  if (name === "citations" && P && !CIT) safe(loadCitations);
}
$$(".tabs [role=tab]").forEach(b => b.onclick = () => showTab(b.dataset.tab));

let WEB = null, CAT = null, CATSEL = null, CATFILE = null;
function resetPageTabs() {
  WEB = null; SITE = null; PAGESEL = null; CAT = null; CATSEL = null; WIKIBLOCKS = null; CIT = null; CITROW = null;
  $$(".product-name").forEach(e => e.textContent = P.product.name);
  if (!$("#web-url").value || $("#web-url").dataset.auto === "1") {
    $("#web-url").value = P.danfoss_url || ""; $("#web-url").dataset.auto = "1";
  }
  ["#web-out", "#web-edit", "#web-site", "#web-job", "#web-gaps-card"].forEach(s => $(s).classList.add("hidden"));
  $("#web-status").textContent = ""; $("#web-md").value = ""; $("#web-verify-out").innerHTML = "";
  $("#cat-page").classList.add("hidden"); $("#cat-list").innerHTML = "";
  if (!$("#tab-catalog").classList.contains("hidden")) safe(loadCatalog);
  if (!$("#tab-web").classList.contains("hidden")) safe(loadWeb);
  if (!$("#tab-citations").classList.contains("hidden")) safe(loadCitations);
}
$("#web-url").addEventListener("input", e => e.target.dataset.auto = "0");

const STATUS_ICON = { ok: "✔", warn: "▲", bad: "✖" };
const VERSION_NAME = { original: "Danfoss's page", rebuilt: "Your copy", template: "From the fact sheet", ai: "AI rewrite" };

// Crawler checks: one row per check, one column per version
function renderAudit(el, audits) {
  const names = Object.keys(audits);
  const checks = [];
  for (const n of names) for (const a of audits[n]) if (!checks.includes(a.check)) checks.push(a.check);
  el.innerHTML = `<div class="tablewrap"><table class="data"><thead><tr><th>Check</th>${names.map(n => `<th>${esc(VERSION_NAME[n] || n)}</th>`).join("")}</tr></thead><tbody>` +
    checks.map(c => `<tr><td>${esc(c)}</td>${names.map(n => {
      const a = audits[n].find(x => x.check === c);
      return a ? `<td class="st-${a.status}" title="${esc(a.note)}"><span class="icon">${STATUS_ICON[a.status]}</span> ${esc(a.value)}${a.note && a.status !== "ok" ? `<div class="tiny hint">${esc(a.note.slice(0, 160))}</div>` : ""}</td>` : "<td class='hint'>–</td>";
    }).join("")}</tr>`).join("") + "</tbody></table></div>";
}

// What Googlebot sees: the passages, and which one answers each question
function renderGooglebot(el, views) {
  const names = Object.keys(views);
  const qs = [...new Set(names.flatMap(n => Object.keys(views[n].best)))];
  const state = { side: names[names.length - 1], q: qs[0] || "" };
  const draw = () => {
    const v = views[state.side];
    const best = v.best[state.q];
    el.innerHTML = `<div class="row">
        <div class="seg">${names.map(n => `<button type="button" data-side="${esc(n)}" class="${n === state.side ? "on" : ""}">${esc(VERSION_NAME[n] || n)}</button>`).join("")}</div>
        <select class="qsel" aria-label="Question">${qs.map(q => `<option ${q === state.q ? "selected" : ""}>${esc(q)}</option>`).join("")}</select></div>
      <p class="hint">${v.words} words a crawler can read, cut into <b>${v.passages.length} passages</b> at the headings (about 200 words each, like AI search).
        ${best ? `The question matches passage <b>#${best.index + 1}</b> best (BM25 ${best.score}).` : "No passage matches this question."}</p>
      <ol class="passages">${v.passages.map(p => `<li class="${best && best.index === p.index ? "best" : ""}">
        <div class="crumb">${esc(p.heading || "(no heading)")} <span class="hint">· ${p.words} words</span></div>
        <div class="ptext">${esc(p.text.length > 600 ? p.text.slice(0, 600) + " …" : p.text)}</div></li>`).join("")}</ol>`;
    $$("[data-side]", el).forEach(b => b.onclick = () => { state.side = b.dataset.side; draw(); });
    $(".qsel", el).onchange = e => { state.q = e.target.value; draw(); };
    const b = $(".passages .best", el); if (b) b.scrollIntoView({ block: "nearest" });
  };
  draw();
}

// BM25 per question: rank among the competitor pages, whole page and best passage
function renderBm25(el, bm) {
  const names = Object.keys(bm.rows[0]?.versions || {});
  const two = names.length === 2;
  const cell = (v, kind) => {
    const r = v[kind + "_rank"], top = v[kind + "_top"];
    return `<span class="${top ? "good" : "badtxt"}">#${r}</span> <span class="hint">(${v[kind + "_score"]})</span>`;
  };
  const delta = (a, b, kind) => {
    const d = a[kind + "_rank"] - b[kind + "_rank"];
    return d > 0 ? `<span class="good">▲${d}</span>` : d < 0 ? `<span class="badtxt">▼${-d}</span>` : `<span class="hint">=</span>`;
  };
  el.innerHTML = `<p class="hint">Rank of the Danfoss page among ${bm.pages} pages (the saved competitor pages + this one). Green = in the top ${bm.top_k}, so the AI would see it.
      <b>Whole page</b> is the lab's default ranking; <b>best passage</b> ranks each page by its best passage, like AI search.</p>
    <div class="tablewrap"><table class="data"><thead><tr><th>Question</th>${names.map(n => `<th>${esc(VERSION_NAME[n] || n)}<br><small>whole page · best passage</small></th>`).join("")}${two ? "<th>Change<br><small>page · passage</small></th>" : ""}</tr></thead><tbody>` +
    bm.rows.map(r => `<tr><td>${esc(r.question)}</td>${names.map(n => `<td>${cell(r.versions[n], "page")} · ${cell(r.versions[n], "passage")}<div class="tiny hint">${esc((r.versions[n].best_heading || "").split(" > ").slice(-1)[0])}</div></td>`).join("")}
      ${two ? `<td>${delta(r.versions[names[0]], r.versions[names[1]], "page")} · ${delta(r.versions[names[0]], r.versions[names[1]], "passage")}</td>` : ""}</tr>`).join("") +
    "</tbody></table></div>";
}

function pageUrl(file, dl) { return `/pages/${encodeURIComponent(P.product.slug)}/${file.split("/").map(encodeURIComponent).join("/")}${dl ? "?download=1" : ""}`; }

// --- Web page tab: the mini website ------------------------------------------------------
let SITE = null, PAGESEL = null, sitePoll = null;

async function loadWeb() {
  SITE = await api("/api/site?slug=" + encodeURIComponent(P.product.slug));
  if (!$("#web-url").value || $("#web-url").dataset.auto === "1") {
    $("#web-url").value = SITE.start || P.danfoss_url || ""; $("#web-url").dataset.auto = "1";
  }
  renderJobBox(SITE.job);
  if (SITE.job && SITE.job.status === "running") pollSite();
  if (!SITE.site) {
    $("#web-copyinfo").innerHTML = "No copy yet. Check the first page of the section (for example the catalog) and press <b>Copy the website</b>. It takes a minute or two.";
    ["#web-site", "#web-edit", "#web-out"].forEach(s => $(s).classList.add("hidden"));
    return;
  }
  renderSite();
  const ids = SITE.site.pages.map(x => x.id);
  await selectPage(ids.includes(PAGESEL) ? PAGESEL : (SITE.lab_page || ids[0]), true);
}

function renderJobBox(job) {
  const box = $("#web-job");
  box.classList.toggle("hidden", !job);
  if (!job) return;
  const label = { running: "Copying the website…", done: "✔ Copy finished", error: "⚠ Stopped with a problem" }[job.status] || job.status;
  $("#web-job-step").textContent = `${label} (${Math.floor(job.elapsed / 60)}:${String(job.elapsed % 60).padStart(2, "0")})`;
  $("#web-stop").classList.toggle("hidden", job.status !== "running");
  const log = $("#web-log"); log.textContent = job.log.join("\n"); log.scrollTop = log.scrollHeight;
  $("#web-copy-btn").disabled = job.status === "running";
}

function pollSite() {
  clearInterval(sitePoll);
  sitePoll = setInterval(async () => {
    const s = await api("/api/site?slug=" + encodeURIComponent(P.product.slug)).catch(() => null);
    if (!s) return;
    renderJobBox(s.job);
    if (!s.job || s.job.status !== "running") {
      clearInterval(sitePoll); sitePoll = null;
      if (s.job?.status === "done") { toast("Website copied"); await safe(loadWeb); }
      else if (s.job?.status === "error") toast(s.job.error, 8000);
    }
  }, 1500);
}

$("#web-form").onsubmit = e => {
  e.preventDefault();
  if (!P) return;
  if (SITE?.site && $("#web-replace").checked && !confirm("Replace ALL your edited page copies with fresh copies of Danfoss's pages?")) return;
  safe(async () => {
    await api("/api/site/copy", { slug: P.product.slug, url: $("#web-url").value.trim(),
      max_pages: +$("#web-max").value || 15, replace: $("#web-replace").checked });
    $("#web-copy-btn").disabled = true;
    renderJobBox({ status: "running", log: ["Starting…"], elapsed: 0 });
    pollSite();
  });
};
$("#web-stop").onclick = () => safe(async () => { await api("/api/site/stop", {}); toast("Stopping after the current page…"); });
$("#web-import").onchange = e => {
  const file = e.target.files[0];
  if (!file || !P) return;
  const r = new FileReader();
  r.onload = () => safe(async () => {
    const res = await api("/api/site/import", { slug: P.product.slug, url: $("#web-url").value.trim(),
      filename: file.name, data: String(r.result).split(",")[1] });
    toast("Page imported"); PAGESEL = res.id; await loadWeb();
  }).finally(() => { e.target.value = ""; });
  r.readAsDataURL(file);
};

function renderSite() {
  const s = SITE.site, rows = Object.fromEntries((SITE.checks?.pages || []).map(r => [r.id, r]));
  $("#web-copy-btn").textContent = "Copy the website again";
  $("#web-copyinfo").innerHTML = `${s.pages.length} pages copied ${esc(s.copied.replace("T", " "))} from <a href="${esc(s.start)}" target="_blank" rel="noopener">${esc(s.start)}</a>${s.browser ? "" : " (without a browser: pages that need JavaScript may be incomplete)"}.`;
  $("#web-site").classList.remove("hidden");
  $("#web-pages").innerHTML = s.pages.map(pg => {
    const r = rows[pg.id] || {};
    const d = r.depth == null ? 3 : Math.min(r.depth, 3);
    return `<li data-id="${esc(pg.id)}" class="d${d} ${pg.id === PAGESEL ? "sel" : ""}">${esc(r.h1 || pg.h1)}
      ${pg.id === SITE.lab_page ? '<span class="labtag">· in the citation test</span>' : ""}
      <span class="meta">${r.depth == null ? "not linked from the first page" : r.depth === 0 ? "first page" : r.depth + " click" + (r.depth > 1 ? "s" : "") + " deep"} · ${r.links_in ?? 0} links in · ${r.links_out ?? 0} out</span></li>`;
  }).join("");
  $$("#web-pages li").forEach(li => li.onclick = () => safe(() => selectPage(li.dataset.id, true)));
  if (SITE.checks) renderAudit($("#web-sitechecks"), { "Your website": SITE.checks.summary });
}

async function selectPage(id, setFrame) {
  if (PAGESEL !== id) $("#web-verify-out").innerHTML = "";
  PAGESEL = id;
  $$("#web-pages li").forEach(li => li.classList.toggle("sel", li.dataset.id === id));
  if (setFrame) $("#web-frame").src = pageUrl(`site/${id}.html`) + "?t=" + Date.now();
  WEB = await api(`/api/site/page?slug=${encodeURIComponent(P.product.slug)}&id=${encodeURIComponent(id)}`);
  renderPage();
}

// follow clicks inside the little website: select the page it shows
$("#web-frame").addEventListener("load", () => {
  try {
    const m = /\/site\/([^/?#]+)\.html$/.exec($("#web-frame").contentWindow.location.pathname);
    if (m && decodeURIComponent(m[1]) !== PAGESEL) safe(() => selectPage(decodeURIComponent(m[1]), false));
  } catch (e) { /* a page outside the website */ }
});

$("#web-save").onclick = () => {
  if (!P || !PAGESEL) return;
  const btn = $("#web-save"); btn.disabled = true;
  $("#web-status").textContent = "";
  safe(async () => {
    try {
      const r = await api("/api/site/save", { slug: P.product.slug, id: PAGESEL, text: $("#web-md").value });
      SITE.checks = r.checks; WEB = r;
      renderSite(); renderPage();
      $("#web-frame").src = pageUrl(`site/${PAGESEL}.html`) + "?t=" + Date.now();
      toast("Page saved");
    } finally { btn.disabled = false; }
  });
};

let WIKIBLOCKS = null;
async function loadWikiBlocks() {
  WIKIBLOCKS = await api("/api/site/wiki?slug=" + encodeURIComponent(P.product.slug));
  $("#web-wiki-pick").innerHTML = WIKIBLOCKS.flatMap(b => [
    `<option value="${esc(b.ref)}">${esc(b.title)} — whole</option>`,
    ...b.sections.filter(s => !["facts", "summary"].includes(s.toLowerCase()))
      .map(s => `<option value="${esc(b.ref + "#" + s)}">${esc(b.title)} — ${esc(s)}</option>`),
  ]).join("");
}
function insertWiki(ref) {
  const t = $("#web-md"), line = `\n{{wiki: ${ref}}}\n`;
  const at = t.selectionStart ?? t.value.length;
  t.value = t.value.slice(0, at) + line + t.value.slice(at);
  t.focus(); t.selectionStart = t.selectionEnd = at + line.length;
  toast("Wiki block inserted: press Save and check");
}
$("#web-wiki-insert").onclick = () => $("#web-wiki-pick").value && insertWiki($("#web-wiki-pick").value);

function renderGaps(rows) {
  $("#web-gaps-card").classList.remove("hidden");
  $("#web-gaps").innerHTML = `<div class="tablewrap"><table class="data"><thead><tr><th>Question</th><th>Rank<br><small>passage · page</small></th><th>Beaten by</th><th>Words the winner has, this page lacks</th><th>Wiki blocks with them</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.question)}</td>
      <td><span class="${r.passage_rank === 1 ? "good" : r.passage_rank > 5 ? "badtxt" : ""}">#${r.passage_rank}</span> · #${r.page_rank}</td>
      <td>${esc(r.winner || "—")}</td>
      <td>${r.missing.map(esc).join(", ") || (r.absent_everywhere.length ? `<span class="hint">none (${r.absent_everywhere.map(esc).join(", ")}: on no page)</span>` : "—")}</td>
      <td>${r.wiki.map(s => `<button type="button" class="chipbtn" data-ref="${esc(s.ref)}" title="has “${esc(s.term)}”">+ ${esc(s.title)}</button>`).join(" ") || "—"}</td></tr>`).join("") +
    "</tbody></table></div>";
  $$("#web-gaps [data-ref]").forEach(b => b.onclick = () => { insertWiki(b.dataset.ref); $("#web-md").scrollIntoView({ block: "center" }); });
}

function renderPage() {
  const w = WEB, c = w.changes, cp = w.copy;
  if (!WIKIBLOCKS) safe(loadWikiBlocks);
  $("#web-wiki-used").innerHTML = w.wiki.used.length
    ? `Wiki blocks on this page (they follow the wiki): ${w.wiki.used.map(u => `<code>${esc(u)}</code>`).join(" ")}` : "No wiki blocks on this page yet.";
  if (w.gaps) renderGaps(w.gaps);
  const meta = (/^---[\s\S]*?\nurl:\s*"?([^"\n]*)"?/m.exec(cp.text) || [])[1] || cp.final_url;
  $("#web-addr").textContent = meta;
  $("#web-open").href = pageUrl(w.file);
  $("#web-edit").classList.remove("hidden");
  $("#web-edit-title").textContent = (SITE.checks?.pages || []).find(r => r.id === w.id)?.h1 || w.id;
  if ($("#web-md").dataset.page !== w.id || $("#web-md").value !== cp.text) { $("#web-md").value = cp.text; $("#web-md").dataset.page = w.id; }
  $("#web-saved").textContent = `Copied ${cp.copied.slice(0, 10)} (${cp.rendered_with}) · last saved ${cp.changed.replace("T", " ")}`;
  $("#web-out").classList.remove("hidden");
  const list = (a) => a.map(esc).join(" ");
  $("#web-check").innerHTML = (c.same
      ? `<div class="okbox">✔ Same content as Danfoss's page: only the format changed (${c.words_after} words, numbers identical).</div>`
      : `<div class="warnbox">✎ Your copy changes the content: ${c.words_before} words in Danfoss's page, ${c.words_after} in your copy.</div>
         ${c.added.length ? `<p class="hint"><b>Added words:</b> ${list(c.added)}</p>` : ""}
         ${c.removed.length ? `<p class="hint"><b>Removed words:</b> ${list(c.removed)}</p>` : ""}
         ${c.numbers_added.length ? `<p class="hint"><b>New numbers:</b> ${list(c.numbers_added)}</p>` : ""}
         ${c.numbers_removed.length ? `<p class="hint"><b>Numbers removed:</b> ${list(c.numbers_removed)}</p>` : ""}`)
    + (c.numbers_not_in_wiki.length ? `<div class="warnbox">⚠ New numbers that are not in the wiki: <b>${list(c.numbers_not_in_wiki)}</b>. Every fact must come from the wiki: add it there with its Danfoss source, or remove it.</div>` : "")
    + (c.removed_empty_sections.length ? `<p class="hint">Left out when copying: headings with nothing under them (a script fills them on the live page, so a crawler sees them empty): <b>${esc(c.removed_empty_sections.join(", "))}</b>.</p>` : "")
    + (w.is_lab_page ? `<p class="hint">This page is the product's page in the citation test: <code>${esc(w.lab_file || "")}</code> (style “restructured”), extracted the same way as Danfoss's page.</p>` : "");
  $("#web-files").innerHTML = `<a class="dl main" href="${pageUrl(w.file, 1)}">⬇ This page (HTML)</a>
    <a class="dl" href="${pageUrl("sitemap.xml")}" target="_blank" rel="noopener">sitemap.xml</a>
    <a class="dl" href="${esc(cp.final_url)}" target="_blank" rel="noopener">Danfoss's page</a>`;
  const outline = (lst, title) => `<div><h3>${title}</h3><ul class="outline">${lst.map(h => h.pseudo && !h.level ? `<li class="pseudo">bold text: ${esc(h.text)}</li>`
      : `<li class="lv${h.level}"><b>H${h.level}</b> ${esc(h.text)}</li>`).join("")}</ul></div>`;
  $("#web-outline").innerHTML = outline(w.outline.original, "Danfoss's page") + outline(w.outline.rebuilt, "Your copy");
  renderAudit($("#web-audit"), w.audit);
  renderGooglebot($("#web-gbot"), w.googlebot);
  renderBm25($("#web-bm25"), w.bm25);
  const claims = (fs) => fs.length ? `<ul class="claims">${fs.map(f => `<li><span class="tag">${esc(f.type)}</span> “${esc(f.match)}” — <span class="hint">${esc(f.sentence)}</span></li>`).join("")}</ul>` : `<p class="okbox">✔ None found.</p>`;
  $("#web-claims").innerHTML = `<div class="grid2"><div><h3>Danfoss's page</h3>${claims(w.claims.original)}</div><div><h3>Your copy</h3>${claims(w.claims.copy)}</div></div>`;
}

// --- Citations tab: what Gemini with Google Search cites ------------------------------------
let CIT = null, CITROW = null, citPoll = null;

async function loadCitations() {
  CIT = await api("/api/citations?slug=" + encodeURIComponent(P.product.slug));
  $("#cit-key").innerHTML = CIT.has_key ? "✔ Gemini key saved."
    : `<span style="color:var(--warn)">No Gemini API key yet: add it in ⚙ Settings to run updates.</span>`;
  const sec = $("#cit-section"), prev = sec.value;
  sec.innerHTML = `<option value="all">All (${Object.values(CIT.sections).reduce((a, b) => a + b, 0)})</option>` +
    Object.entries(CIT.sections).map(([k, n]) => `<option value="${esc(k)}">${esc(k)} (${n})</option>`).join("");
  sec.value = prev && [...sec.options].some(o => o.value === prev) ? prev : (Object.keys(CIT.sections)[0] || "all");
  const ours = $("#cit-ours"), prevO = ours.value;
  ours.innerHTML = CIT.ours.map(o => `<option value="${esc(o.id)}">${esc(o.label)}</option>`).join("") || `<option value="">No page of ours yet</option>`;
  if (prevO && CIT.ours.some(o => o.id === prevO)) ours.value = prevO;
  renderCitJob(CIT.job);
  if (CIT.job && CIT.job.status === "running") pollCitations();
  renderCitHistory();
  const runs = CIT.history.runs;
  $("#cit-run").innerHTML = runs.map(r => `<option value="${esc(r.run)}">${esc(r.date)} · ${r.prompts} prompts</option>`).join("") || `<option value="">No update yet</option>`;
  if (CIT.latest) $("#cit-run").value = CIT.latest;
  renderCitPrompts(CIT.summary);
}

function renderCitJob(job) {
  $("#cit-job").classList.toggle("hidden", !job);
  if (!job) return;
  const label = { running: "Asking Gemini…", done: "✔ Update finished", error: "⚠ Stopped" }[job.status] || job.status;
  $("#cit-job-step").textContent = `${label} (${Math.floor(job.elapsed / 60)}:${String(job.elapsed % 60).padStart(2, "0")})`;
  const log = $("#cit-log"); log.textContent = job.log.join("\n"); log.scrollTop = log.scrollHeight;
  $("#cit-update").disabled = job.status === "running";
}

function pollCitations() {
  clearInterval(citPoll);
  citPoll = setInterval(async () => {
    const s = await api("/api/citations?slug=" + encodeURIComponent(P.product.slug)).catch(() => null);
    if (!s) return;
    renderCitJob(s.job);
    if (!s.job || s.job.status !== "running") {
      clearInterval(citPoll); citPoll = null;
      if (s.job?.status === "done") toast("Citations updated");
      else if (s.job?.status === "error") toast(s.job.error, 8000);
      await safe(loadCitations);
    }
  }, 2000);
}

$("#cit-update").onclick = () => safe(async () => {
  await api("/api/citations/update", { slug: P.product.slug, section: $("#cit-section").value,
    limit: +$("#cit-limit").value || 0, model: $("#cit-model").value.trim() });
  renderCitJob({ status: "running", log: ["Starting…"], elapsed: 0 });
  pollCitations();
});

function shareBar(x, danfoss) {
  const w = Math.round(100 * (x || 0));
  return `<span class="sharebar"><i style="width:${w}%" class="${danfoss ? "us" : ""}"></i></span> ${w}%`;
}

function renderCitHistory() {
  const h = CIT.history;
  if (!h.runs.length) {
    $("#cit-history").innerHTML = `<p class="hint">No update yet. Press <b>Update citations</b> (needs a Gemini key). A first test with “At most 3” takes about a minute.</p>`;
    $("#cit-sites").innerHTML = ""; return;
  }
  $("#cit-history").innerHTML = `<div class="tablewrap"><table class="data"><thead><tr><th>Update</th><th>Prompts</th><th>Pages cited</th><th>Answers citing Danfoss</th><th>Danfoss share</th><th>Most cited sites (share)</th></tr></thead><tbody>` +
    h.runs.map(r => `<tr><td>${esc(r.date)}<div class="tiny hint">${esc(r.model)}${r.has_shares ? "" : " · counts only"}</div></td><td>${r.prompts}</td><td>${r.sources}</td>
      <td>${r.danfoss_answers} of ${r.prompts}</td><td>${shareBar(r.danfoss_share, true)}</td>
      <td class="tiny">${r.top_sites.map(([d, v]) => `${esc(d)} ${pct(v)}`).join(" · ")}</td></tr>`).join("") + "</tbody></table></div>";
  const runs = h.runs.slice().reverse();
  $("#cit-sites").innerHTML = runs.length < 2 ? "" : `<h3>Share per site, update by update</h3><div class="tablewrap"><table class="data"><thead><tr><th>Site</th>${runs.map(r => `<th>${esc(r.date.slice(5))}</th>`).join("")}</tr></thead><tbody>` +
    h.sites.map(s => `<tr><td>${esc(s.site)}</td>${runs.map(r => `<td>${s.by_run[r.run] != null ? pct(s.by_run[r.run]) : "–"}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>";
}

function renderCitPrompts(rows) {
  $("#cit-prompts").innerHTML = !rows.length ? "" : `<div class="tablewrap"><table class="data pick"><thead><tr><th>Prompt</th><th>Pages</th><th>Searches</th><th>Top page (share)</th><th>Danfoss share</th></tr></thead><tbody>` +
    rows.map(r => `<tr data-i="${r.i}"><td>${esc(r.prompt)}</td><td>${r.sources}</td><td>${r.queries}</td><td>${esc(r.top || "—")} ${r.top ? pct(r.top_share) : ""}</td><td>${shareBar(r.danfoss_share, true)}</td></tr>`).join("") + "</tbody></table></div>";
  $$("#cit-prompts tr[data-i]").forEach(tr => tr.onclick = () => safe(() => openCitPrompt(+tr.dataset.i)));
}

$("#cit-run").onchange = () => safe(async () => {
  renderCitPrompts(await api("/api/citations/run?run=" + encodeURIComponent($("#cit-run").value)));
  $("#cit-detail").classList.add("hidden");
});
$("#cit-ours").onchange = () => CITROW != null && safe(() => openCitPrompt(CITROW));

async function openCitPrompt(i) {
  CITROW = i;
  $$("#cit-prompts tr[data-i]").forEach(tr => tr.classList.toggle("sel", +tr.dataset.i === i));
  const q = new URLSearchParams({ slug: P.product.slug, run: $("#cit-run").value, i, ours: $("#cit-ours").value });
  const d = await api("/api/citations/prompt?" + q);
  $("#cit-detail").classList.remove("hidden");
  $("#cit-q").textContent = d.prompt;
  $("#cit-meta").textContent = `Asked ${d.asked_at.replace("T", " ")} · ${d.model}` + (d.coverage != null ? ` · ${pct(d.coverage)} of the answer is backed by a source` : "");
  $("#cit-answer").textContent = d.answer;
  $("#cit-sources").innerHTML = d.sources.length ? `<div class="tablewrap"><table class="data"><thead><tr><th>#</th><th>Page</th><th>Share of the answer</th><th>Pieces supported</th><th>Confidence</th></tr></thead><tbody>` +
    d.sources.map(s => `<tr><td>${s.rank ?? ""}</td><td>${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.site)}</a>` : esc(s.site)}${s.danfoss ? ' <span class="tag">Danfoss</span>' : ""}</td>
      <td>${shareBar(s.share, s.danfoss)}</td><td>${s.supports}</td><td>${s.confidence != null ? s.confidence : "—"}</td></tr>`).join("") + "</tbody></table></div>"
    : `<p class="hint">Gemini answered without searching.</p>`;
  const c = d.compare;
  if (!c) { $("#cit-queries").innerHTML = `<p class="hint">No page of ours to compare yet.</p>`; return; }
  $("#cit-queries").innerHTML = (c.queries.length ? `<p class="hint">Our page answers <b>${c.answered} of ${c.n_queries}</b> searches best (${esc(d.ours.label)}).</p>
    <div class="tablewrap"><table class="data"><thead><tr><th>Search</th><th>Our rank</th><th>Leads</th><th>Our best passage</th></tr></thead><tbody>` +
    c.queries.map(x => `<tr><td>${esc(x.query)}</td><td><span class="${x.answered ? "good" : "badtxt"}">#${x.our_rank}</span> of ${x.of}</td><td>${esc(x.leader)}</td><td class="tiny">${esc(x.our_passage)}</td></tr>`).join("") + "</tbody></table></div>"
    : `<p class="hint">None of the cited pages could be imported, so there is nothing to compare.</p>`)
    + (c.docs.length ? `<details><summary>The passage of each cited page that best matches what Gemini took from it</summary>${c.docs.map(x => `<p><b>${esc(x.site)}</b> (${pct(x.share)}): <span class="hint">${esc(x.likely_passage || "—")}</span></p>`).join("")}</details>` : "")
    + (c.not_imported.length ? `<p class="hint tiny">Not imported (blocked or no text): ${c.not_imported.map(x => esc(x.site)).join(", ")}</p>` : "");
  $("#cit-why").innerHTML = ""; $("#cit-explain-status").textContent = "";
}

$("#cit-explain").onclick = () => {
  if (CITROW == null) return;
  const s = gather(), btn = $("#cit-explain"); btn.disabled = true;
  $("#cit-explain-status").textContent = `Asking ${S.providers[s.judge]?.label || s.judge} (${s.judge_model})… a local model can take a minute or two.`;
  safe(async () => {
    try {
      const r = await api("/api/citations/explain", { slug: P.product.slug, run: $("#cit-run").value, i: CITROW,
        ours: $("#cit-ours").value, provider: s.judge, model: s.judge_model, fresh: $("#cit-fresh").checked });
      const keys = r.rubric.map(k => k.key);
      $("#cit-why").innerHTML = `<p>${esc(r.why)}</p>
        ${r.missing.length ? `<p class="hint"><b>What the weakest passages lack:</b> ${r.missing.map(esc).join("; ")}</p>` : ""}
        <div class="tablewrap"><table class="data"><thead><tr><th>Passage</th><th>Gemini share</th>${r.rubric.map(k => `<th title="${esc(k.text)}">${esc(k.key.replace(/_/g, " "))}</th>`).join("")}<th>Total</th></tr></thead><tbody>` +
        r.rows.sort((a, b) => b.total - a.total).map(x => `<tr><td>${esc(x.label)} · ${esc(x.name)}</td><td>${pct(x.gemini_share)}</td>${keys.map(k => `<td>${x.scores[k]}</td>`).join("")}<td><b>${x.total}</b></td></tr>`).join("") + "</tbody></table></div>" +
        `<p class="hint">Agreement with Gemini's shares (rank correlation, −1 to 1): <b>${r.agreement ?? "not enough pages"}</b>. Each passage was ${r.words_per_passage} words. Reviewer: ${esc(r.model)}.</p>` +
        `<details><summary>The passages the reviewer saw</summary>${r.rows.map(x => `<p><b>${esc(x.label)} · ${esc(x.name)}</b>: <span class="hint">${esc(x.excerpt)}</span></p>`).join("")}</details>`;
      $("#cit-explain-status").textContent = "";
    } catch (e) { $("#cit-explain-status").textContent = ""; throw e; } finally { btn.disabled = false; }
  });
};

// --- fact check (both web tabs) ---------------------------------------------------------
let verifyPoll = null;
function factCheck(kind, ref, out, status, btn) {
  const s = gather();
  btn.disabled = true; out.innerHTML = "";
  status.textContent = "Starting…";
  safe(async () => {
    try {
      await api("/api/verify", { slug: P.product.slug, kind, ref, provider: s.judge, model: s.judge_model });
    } catch (e) { btn.disabled = false; status.textContent = ""; throw e; }
    clearInterval(verifyPoll);
    verifyPoll = setInterval(async () => {
      const j = await api("/api/verify/job").catch(() => null);
      if (!j) return;
      status.textContent = j.status === "running" ? (j.log.slice(-1)[0] || "Checking…") : "";
      if (j.status === "running") return;
      clearInterval(verifyPoll); btn.disabled = false;
      if (j.status === "error") { toast(j.error, 8000); return; }
      const r = j.result, m = r.summary;
      const icon = { supported: "✔", partly: "▲", unsupported: "✖", "not checked": "…" };
      const cls = { supported: "st-ok", partly: "st-warn", unsupported: "st-bad", "not checked": "" };
      out.innerHTML = `<div class="${m.unsupported ? "warnbox" : "okbox"}">${m.supported} of ${m.claims} claims supported` +
        (m.partly ? `, ${m.partly} partly` : "") + (m.unsupported ? `, <b>${m.unsupported} not supported</b>` : "") +
        (m["not checked"] ? `, ${m["not checked"]} not checked (limit)` : "") + ` · model calls: ${m.model_calls} (${esc(r.backend)})</div>` +
        `<div class="tablewrap"><table class="data"><thead><tr><th>Verdict</th><th>Claim</th><th>How</th><th>Best source</th></tr></thead><tbody>` +
        r.claims.filter(c => c.verdict !== "supported").concat(r.claims.filter(c => c.verdict === "supported").slice(0, 15)).map(c =>
          `<tr><td class="${cls[c.verdict] || ""}"><span class="icon">${icon[c.verdict] || ""}</span> ${esc(c.verdict)}</td><td>${esc(c.claim)}</td>
           <td class="tiny">${esc(c.method)}${c.note ? `<div class="hint">${esc(c.note)}</div>` : ""}${c.quote ? `<div class="hint">“${esc(c.quote)}”</div>` : ""}</td>
           <td class="tiny">${c.evidence[0] ? `<b>${esc(c.evidence[0].source)}</b>: ${esc(c.evidence[0].text.slice(0, 160))}` : "—"}</td></tr>`).join("") +
        `</tbody></table></div>` + (m.supported > 15 ? `<p class="hint tiny">Showing the first 15 supported claims.</p>` : "");
    }, 1500);
  });
}
$("#web-verify").onclick = () => PAGESEL && factCheck("site", PAGESEL, $("#web-verify-out"), $("#web-verify-status"), $("#web-verify"));
$("#cat-verify").onclick = () => CATFILE && factCheck("product", CATFILE, $("#cat-verify-out"), $("#cat-verify-status"), $("#cat-verify"));

// --- Product by product tab ---------------------------------------------------------------
async function loadCatalog() {
  CAT = await api("/api/catalog?slug=" + encodeURIComponent(P.product.slug));
  if (!CAT.items.length) {
    $("#cat-hint").textContent = CAT.note || "No product list in this fact sheet.";
    $("#cat-list").innerHTML = ""; return;
  }
  $("#cat-hint").innerHTML = `${CAT.items.length} products, from the fact sheet table “${esc(CAT.source)}”. Pick one to build its page.`;
  $("#cat-list").innerHTML = `<div class="tablewrap"><table class="data pick"><thead><tr>${CAT.columns.map(c => `<th>${esc(c)}</th>`).join("")}<th></th></tr></thead><tbody>` +
    CAT.items.map(it => `<tr data-id="${esc(it.id)}" class="${it.id === CATSEL ? "sel" : ""}">${it.cells.map(c => `<td>${esc(c)}</td>`).join("")}<td>${it.extra.length ? `<span class="tag">+ ${it.extra.map(x => esc(x.title || "data")).join(", ")}</span>` : ""}</td></tr>`).join("") + "</tbody></table></div>";
  $$("#cat-list tr[data-id]").forEach(tr => tr.onclick = () => pickProduct(tr.dataset.id));
}

function pickProduct(id) {
  CATSEL = id;
  $$("#cat-list tr[data-id]").forEach(tr => tr.classList.toggle("sel", tr.dataset.id === id));
  $("#cat-page").classList.remove("hidden");
  $("#cat-title").textContent = `${CAT.key} ${id}`;
  $("#cat-out").classList.add("hidden");
  buildProduct("template");
  $("#cat-page").scrollIntoView({ behavior: "smooth", block: "start" });
}

function buildProduct(version) {
  const s = gather();
  const btns = [$("#cat-template"), $("#cat-ai")]; btns.forEach(b => b.disabled = true);
  $("#cat-status").textContent = version === "ai" ? `Rewriting with ${S.providers[s.writer]?.label || s.writer} (${s.writer_model})… this can take a minute.` : "Building the page from the fact sheet…";
  safe(async () => {
    try {
      const r = await api("/api/catalog/build", { slug: P.product.slug, id: CATSEL, version, provider: s.writer, model: s.writer_model, fresh: $("#cat-fresh").checked });
      $("#cat-out").classList.remove("hidden");
      const f = r.flags;
      $("#cat-flags").innerHTML = version === "ai"
        ? (f.numbers_not_in_facts.length || f.claims.length
          ? `<div class="warnbox">⚠ Check before use:${f.numbers_not_in_facts.length ? ` numbers not in this product's facts: <b>${esc(f.numbers_not_in_facts.join(", "))}</b>.` : ""}${f.claims.length ? ` Never-claim words: ${f.claims.map(c => `“${esc(c.match)}”`).join(", ")}.` : ""}</div>`
          : `<div class="okbox">✔ No numbers outside this product's facts and no never-claim words found. Still read it before use.</div>`)
        : `<div class="okbox">✔ Every sentence comes from the fact sheet (${r.words} words).</div>`;
      CATFILE = r.file; $("#cat-verify-out").innerHTML = "";
      $("#cat-files").innerHTML = `<a class="dl main" href="${pageUrl(r.file, 1)}">⬇ Page (HTML)</a><a class="dl" href="${pageUrl(r.file)}" target="_blank" rel="noopener">Open in a new tab</a>`;
      $("#cat-frame").src = pageUrl(r.file) + "?t=" + Date.now();
      renderAudit($("#cat-audit"), { [version]: r.audit });
      renderGooglebot($("#cat-gbot"), { [version]: r.googlebot });
      renderBm25($("#cat-bm25"), r.bm25);
      $("#cat-status").textContent = version === "ai" ? "AI rewrite ready." : "Page from the fact sheet ready.";
    } catch (err) { $("#cat-status").textContent = ""; throw err; } finally { btns.forEach(b => b.disabled = false); }
  });
}
$("#cat-template").onclick = () => CATSEL && buildProduct("template");
$("#cat-ai").onclick = () => CATSEL && buildProduct("ai");

safe(async () => { await loadState(); showTab(recall("tab", "run")); });
