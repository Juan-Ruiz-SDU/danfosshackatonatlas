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
  const sel = $("#product-select");
  const want = recall("product", S.products[0]?.slug);
  sel.innerHTML = S.products.map(p => `<option value="${esc(p.slug)}">${esc(p.name)}</option>`).join("");
  if (S.products.some(p => p.slug === want)) sel.value = want;
  fillProviders();
  renderStyles();
  restoreSettings();
  renderBanner();
  if (sel.value) await loadProduct(sel.value);
  if (S.job && S.job.status === "running") startPolling();
  else if (S.job && S.job.slug === sel.value && S.job.status !== "done") renderJob(S.job);
}

function renderBanner() {
  const b = $("#banner");
  let html = "";
  const used = [...new Set([$("#s-writer").value, $("#s-judge").value])].filter(id => S.providers[id]);
  for (const id of used) {
    const p = S.providers[id];
    if (p.type === "ollama" && !p.reachable) {
      html += `<section class="card"><h2>Ollama can't be reached</h2>
        <p class="hint">Atlas is set to use Ollama at <code>${esc(p.base_url)}</code>, but nothing answers there.
        If Ollama runs on <b>your</b> computer, open the Ollama app. If you use the <b>team server</b>, type its address
        (ask its owner to run <code>ipconfig</code>; you must be on the same Wi-Fi) and press Save.</p>
        <form class="row" data-addr="${esc(id)}"><input value="${esc(p.base_url)}" style="flex:1" placeholder="http://10.126.128.116:11434/">
        <button class="primary">Save</button><button type="button" class="ghost" data-recheck>Check again</button></form></section>`;
    } else if (p.type === "ollama" && p.installed && !p.installed.includes($(id === $("#s-writer").value ? "#s-writer-model" : "#s-judge-model").value)) {
      html += `<section class="card"><b>Model not installed.</b> <span class="hint">The Ollama server at <code>${esc(p.base_url)}</code> has
        ${p.installed.length ? esc(p.installed.join(", ")) : "no models"}. Pick one of those, or run <code>ollama pull qwen3:8b</code> on that computer.</span></section>`;
    } else if (p.key_env && !p.has_key) {
      html += `<section class="card"><h2>Add your ${esc(p.label)} key</h2>
        <p class="hint">${id === "gemini" ? `Get a free key at <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">aistudio.google.com/apikey</a>. ` : ""}It stays on this computer.
        Or pick Ollama above to run everything on your own server, with no key and no quota.</p>
        <form class="row" data-key="${esc(p.key_env)}"><input type="password" placeholder="Paste your key" style="flex:1" autocomplete="off">
        <button class="primary">Save</button></form></section>`;
    }
  }
  if (!S.deps.fpdf) {
    html += `<section class="card"><b>PDFs are off.</b> <span class="hint">To get the final page and the report as PDF, close Atlas and run
      <code>pip install -r requirements.txt</code> (or start Atlas with "Start Atlas.bat", which does it for you).</span></section>`;
  }
  b.innerHTML = html;
  $$("#banner [data-key]").forEach(f => f.onsubmit = e => {
    e.preventDefault();
    safe(async () => { await api("/api/key", { env: f.dataset.key, value: $("input", f).value }); toast("Key saved"); await loadState(); });
  });
  $$("#banner [data-addr]").forEach(f => f.onsubmit = e => {
    e.preventDefault();
    safe(async () => { await api("/api/provider/update", { id: f.dataset.addr, base_url: $("input", f).value }); await loadState(); toast(S.providers[f.dataset.addr].reachable ? "Connected" : "Still no answer at that address"); });
  });
  $$("#banner [data-recheck]").forEach(btn => btn.onclick = () => safe(loadState));

  // source discovery searches Google, which only Gemini can do
  const disc = $("#s-discovery");
  disc.disabled = !S.gemini_key;
  if (!S.gemini_key) disc.checked = false;
  disc.closest(".switch").title = S.gemini_key ? "" : "Needs a Gemini key (Settings): Ollama can't search the web";
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
  $("#s-retrieval").value = ["passage", "hybrid"].includes(s.retrieval) ? s.retrieval : "page";
}
function saveSettings() { if (restoring) return; store("settings", gather()); renderBanner(); estimate(); }
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
  const pw = S.providers[s.writer] || {}, pj = S.providers[s.judge] || {};
  // writing: 1.5 attempts per page on average (length retries)
  const secs = search * 9 + ns * 1.5 * ((pw.est_write || 30) + (pw.sleep || 0)) + judge * ((pj.est_answer || 10) + (pj.sleep || 0));
  const mins = Math.max(1, Math.round(secs / 60));
  const time = mins >= 90 ? `${(mins / 60).toFixed(1)} hours` : `${mins} min`;
  let txt = `${nq} questions × ${targets} page versions → about <b>${calls} AI calls</b>, roughly ${time}. Answers already saved are free.`;
  if (pw.type === "ollama" || pj.type === "ollama") txt += ` Runs on Ollama: no tokens or quota used.`;
  if (mins >= 90 && pj.type === "ollama") txt += `<br><span style="color:var(--warn)">That's long on a CPU. To speed it up, tick fewer questions or page versions, or keep the computer from sleeping and let it run.</span>`;
  if (calls > 200 && (s.judge === "gemini" || s.writer === "gemini")) txt += `<br><span style="color:var(--warn)">This may hit Gemini's free daily limit. If it does, press Run again tomorrow: it continues where it stopped.</span>`;
  $("#estimate").innerHTML = txt;
  $("#discovery-hint").textContent = !S.gemini_key
    ? `Needs a Gemini key (Settings), because Ollama can't search the web. Off: uses the ${P.pages.competitors} competitor pages saved earlier.`
    : s.discovery
      ? `On: asks Google's AI (Gemini, uses quota) all ${nq} questions and imports the pages it cites as the competition (+${nq} searches).`
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
    `<li style="flex-wrap:wrap"><span><b>${esc(p.label)}</b>
       ${p.type === "ollama" ? `<small class="${p.reachable ? "ok" : "hint"}">${p.reachable ? "✔ connected · " + esc((p.installed || []).join(", ") || "no models") : "not reachable"}</small>` : ""}
       <br><small class="hint">${esc(p.models.join(", "))}</small></span>
     <form class="row" data-addr="${esc(id)}" style="flex:1 1 300px"><input value="${esc(p.base_url)}" style="flex:1" aria-label="Address">
       <button>Save address</button>
       ${["gemini", "ollama"].includes(id) ? "" : `<button type="button" class="x" data-rm="${esc(id)}" title="Remove">✕</button>`}</form></li>`).join("");
  $$("#prov-list [data-addr]").forEach(f => f.onsubmit = e => {
    e.preventDefault();
    safe(async () => { await api("/api/provider/update", { id: f.dataset.addr, base_url: $("input", f).value }); await loadState(); renderSettings(); toast("Address saved"); });
  });
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
  if (name === "web" && P && !WEB) safe(loadWeb);
}
$$(".tabs [role=tab]").forEach(b => b.onclick = () => showTab(b.dataset.tab));

let WEB = null, CAT = null, CATSEL = null;
function resetPageTabs() {
  WEB = null; CAT = null; CATSEL = null;
  $$(".product-name").forEach(e => e.textContent = P.product.name);
  if (!$("#web-url").value || $("#web-url").dataset.auto === "1") {
    $("#web-url").value = P.danfoss_url || ""; $("#web-url").dataset.auto = "1";
  }
  $("#web-out").classList.add("hidden"); $("#web-edit").classList.add("hidden");
  $("#web-status").textContent = ""; $("#web-md").value = "";
  $("#cat-page").classList.add("hidden"); $("#cat-list").innerHTML = "";
  if (!$("#tab-catalog").classList.contains("hidden")) safe(loadCatalog);
  if (!$("#tab-web").classList.contains("hidden")) safe(loadWeb);
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

// --- Web page tab ---------------------------------------------------------------------------
async function loadWeb() {
  $("#web-status").textContent = "";
  WEB = await api("/api/webpage?slug=" + encodeURIComponent(P.product.slug));
  if (!WEB.copy) {
    $("#web-copyinfo").innerHTML = "No copy yet. Check the address and press <b>Make the copy</b>.";
    $("#web-copy-btn").textContent = "Make the copy";
    $("#web-edit").classList.add("hidden"); $("#web-out").classList.add("hidden");
    return;
  }
  renderWeb();
}

function webCall(path, body, msg) {
  const btns = [$("#web-copy-btn"), $("#web-save")]; btns.forEach(b => b.disabled = true);
  $("#web-status").textContent = msg;
  return safe(async () => {
    try {
      WEB = await api(path, { slug: P.product.slug, ...body });
      renderWeb();
      $("#web-status").textContent = WEB.copy_written === false
        ? "Reference snapshot renewed. Your edited copy was kept (tick “Also replace” to start over)." : "";
      return true;
    } catch (err) { $("#web-status").textContent = ""; throw err; } finally { btns.forEach(b => b.disabled = false); }
  });
}

$("#web-form").onsubmit = e => {
  e.preventDefault();
  if (!P) return;
  if (WEB?.copy && $("#web-replace").checked && !confirm("Replace your edited copy with a fresh copy of Danfoss's page?")) return;
  webCall("/api/webpage/copy", { url: $("#web-url").value.trim(), replace: $("#web-replace").checked },
    "Reading Danfoss's page and making the copy… (a few seconds)");
};
$("#web-import").onchange = e => {
  const file = e.target.files[0];
  if (!file || !P) return;
  if (WEB?.copy && $("#web-replace").checked && !confirm("Replace your edited copy with this file?")) return;
  const r = new FileReader();
  r.onload = () => webCall("/api/webpage/copy", {
    url: $("#web-url").value.trim(), replace: $("#web-replace").checked,
    filename: file.name, data: String(r.result).split(",")[1],
  }, "Reading the saved page…").finally(() => { e.target.value = ""; });
  r.readAsDataURL(file);
};
$("#web-save").onclick = () => {
  if (!P) return;
  webCall("/api/webpage/save", { text: $("#web-md").value }, "Saving your copy and checking it…")
    .then(ok => ok && toast("Copy saved"));
};

function renderWeb() {
  const w = WEB, c = w.changes, cp = w.copy;
  $("#web-copy-btn").textContent = "Copy the page again";
  $("#web-copyinfo").innerHTML = `Copy made ${esc(cp.copied.replace("T", " "))} from ${cp.imported ? `the saved file <b>${esc(cp.imported)}</b>` : `<a href="${esc(cp.final_url)}" target="_blank" rel="noopener">${esc(cp.final_url)}</a>`}.`;
  $("#web-edit").classList.remove("hidden");
  if ($("#web-md").value !== cp.text) $("#web-md").value = cp.text;
  $("#web-saved").textContent = `Last saved ${cp.changed.replace("T", " ")}`;
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
    + (c.removed_empty_sections.length ? `<p class="hint">Left out when copying: headings with nothing under them in the HTML (a script fills them on the live page, so a crawler sees them empty): <b>${esc(c.removed_empty_sections.join(", "))}</b>.</p>` : "")
    + `<p class="hint">Your copy is in the citation test as <code>${esc(w.files.lab)}</code> (style “restructured”), extracted the same way as Danfoss's page.</p>`;
  $("#web-files").innerHTML = `<a class="dl main" href="${pageUrl(w.files.rebuilt, 1)}">⬇ Your page (HTML)</a>
    <a class="dl" href="${pageUrl(w.files.rebuilt)}" target="_blank" rel="noopener">Open it in a new tab</a>
    <a class="dl" href="${pageUrl(w.files.sitemap)}" target="_blank" rel="noopener">sitemap.xml</a>
    <a class="dl" href="${esc(cp.final_url)}" target="_blank" rel="noopener">Danfoss's page</a>`;
  const outline = (list, title) => `<div><h3>${title}</h3><ul class="outline">${list.map(h => h.pseudo && !h.level ? `<li class="pseudo">bold text: ${esc(h.text)}</li>`
      : `<li class="lv${h.level}${h.pseudo ? " fixed" : ""}"><b>H${h.level}</b> ${esc(h.text)}${h.pseudo ? " <small>(was bold text)</small>" : ""}</li>`).join("")}</ul></div>`;
  $("#web-outline").innerHTML = outline(w.outline.original, "Danfoss's page") + outline(w.outline.rebuilt, "Your copy");
  $("#web-frame").src = pageUrl(w.files.rebuilt) + "?t=" + Date.now();
  renderAudit($("#web-audit"), w.audit);
  renderGooglebot($("#web-gbot"), w.googlebot);
  renderBm25($("#web-bm25"), w.bm25);
  const claims = (fs) => fs.length ? `<ul class="claims">${fs.map(f => `<li><span class="tag">${esc(f.type)}</span> “${esc(f.match)}” — <span class="hint">${esc(f.sentence)}</span></li>`).join("")}</ul>` : `<p class="okbox">✔ None found.</p>`;
  $("#web-claims").innerHTML = `<div class="grid2"><div><h3>Danfoss's page</h3>${claims(w.claims.original)}</div><div><h3>Your copy</h3>${claims(w.claims.copy)}</div></div>`;
}

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
