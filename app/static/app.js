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
}
function saveSettings() { if (restoring) return; store("settings", gather()); estimate(); }
["#s-discovery", "#s-writer-model", "#s-judge-model", "#s-words", "#s-repeats", "#s-topk", "#s-fresh", "#s-retries"]
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

safe(loadState);
