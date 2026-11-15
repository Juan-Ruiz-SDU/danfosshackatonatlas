"use strict";
// Run results (ranking, holdout, per-question heatmap, JEV's answers, versions), structured data,
// the Wiki tab and the news alerts. Uses the helpers of app.js ($, $$, esc, pct, api, safe, toast,
// fileUrl, renderAudit, showSub, go) and its globals (S, P, RUNDETAIL, WIKI).

// --- Run › Results: ranking, text about the result, holdout check -------------------------------
function renderRunExtras(r) {
  const has = !!r;
  ["#card-heatmap", "#card-versions"].forEach(s => $(s).classList.toggle("hidden", !has));
  ["#explanation", "#ranking", "#holdout-box"].forEach(s => $(s).classList.add("hidden"));
  if (!has) return;
  if (r.explanation) {
    $("#explanation").classList.remove("hidden");
    $("#explanation").innerHTML = `<h3>What this means</h3><p>${esc(r.explanation)}</p>
      <p class="hint tiny">Written from the numbers by ${esc(r.analyst || "the analyst AI")}. JEV, the judge: ${esc(r.judge || "?")}${r.blind ? ", brand names hidden" : ""}${r.repeats ? `, ${r.repeats} repeat(s)` : ""}${r.questions ? `, ${r.questions} questions` : ""}.</p>`;
  }
  const rank = r.ranking || [];
  if (rank.length) {
    const max = Math.max(...rank.map(x => x.share), 0.01);
    $("#ranking").classList.remove("hidden");
    $("#ranking").innerHTML = `<h3>Ranking: best to worst <small>(top ${rank.length})</small></h3>
      <p class="hint">Citation share of each version. <b>Tie</b>: its 95% range overlaps the winner's, so with this much data the gap may be luck.</p>
      <ol class="ranking">${rank.map(x => `<li class="${x.winner ? "win-row" : ""} ${x.publishable ? "" : "test-only"}">
        <span class="pos">${x.rank}</span>
        <span class="nm">${esc(x.name)}${x.winner ? ' <span class="tag on">winner</span>' : x.tie ? ' <span class="tag">tie</span>' : ""}${x.publishable ? "" : ' <span class="tag">not publishable</span>'}</span>
        <span class="barcell"><i style="width:${Math.round(100 * x.share / max)}%"></i></span>
        <span class="val"><b>${pct(x.share)}</b> <span class="hint tiny">cited ${pct(x.cited)} (${pct(x.cited_low)}–${pct(x.cited_high)}) · first ${pct(x.first)}</span></span></li>`).join("")}</ol>`;
  }
  const h = r.holdout;
  if (h) {
    const ok = h.winner_still_first && h.winner_beats_baseline !== false;
    $("#holdout-box").classList.remove("hidden");
    $("#holdout-box").innerHTML = `<h3>Holdout check <small>${h.questions} questions never used to write the pages</small></h3>
      <div class="${ok ? "okbox" : "warnbox"}">${h.winner_still_first ? "✔ The winner is still the most cited version" : "▲ The winner is not the most cited version on these questions: its lead may come from tuning to the usual questions"}${
        h.winner_beats_baseline == null ? "." : h.winner_beats_baseline ? `, and it beats Danfoss's current page (${pct(h.winner_share)} vs ${pct(h.baseline_share)}).`
          : `${h.winner_still_first ? ", but it" : "; it also"} does not beat Danfoss's current page (${pct(h.winner_share)} vs ${pct(h.baseline_share)}).`}</div>
      <div class="tablewrap"><table class="data"><thead><tr><th>Version</th><th>Share</th><th>Cited</th><th>95% range</th></tr></thead><tbody>${
        h.summary.map(x => `<tr><td>${esc(x.name)}</td><td>${pct(x.share)}</td><td>${pct(x.cited)}</td><td>${pct(x.cited_low)}–${pct(x.cited_high)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  loadRunDetail(r.run);
}

// --- Run › Per question / Versions --------------------------------------------------------------
let HEATSET = "main";
async function loadRunDetail(run) {
  const slug = P.product.slug;
  try {
    const d = await api(`/api/run/detail?slug=${encodeURIComponent(slug)}&run=${encodeURIComponent(run)}`);
    if (P.product.slug !== slug) return;
    RUNDETAIL = d;
  } catch (e) { RUNDETAIL = null; $("#heatmap").innerHTML = `<p class="hint">${esc(e.message)}</p>`; return; }
  $("#heat-run").textContent = "run " + run;
  $$("#heat-set button").forEach(b => { b.disabled = b.dataset.set === "holdout" && !RUNDETAIL.holdout; });
  if (HEATSET === "holdout" && !RUNDETAIL.holdout) HEATSET = "main";
  renderHeatmap();
  renderVersions();
}
$$("#heat-set button").forEach(b => b.onclick = () => { HEATSET = b.dataset.set; renderHeatmap(); });

function renderHeatmap() {
  $$("#heat-set button").forEach(b => b.classList.toggle("on", b.dataset.set === HEATSET));
  const g = RUNDETAIL && RUNDETAIL[HEATSET];
  $("#answers").innerHTML = "";
  if (!g) { $("#heatmap").innerHTML = `<p class="hint">No holdout questions in this run.</p>`; return; }
  const cell = (v, i) => {
    const c = g.cells[`${v}|${i}`];
    if (!c) return `<td class="hcell none">–</td>`;
    const rate = c.cited / c.n;
    return `<td class="hcell ${rate >= 0.55 ? "dark" : ""}" style="--h:${Math.round(rate * 100)}%" data-v="${esc(v)}" data-i="${i}" tabindex="0"
      title="${esc(g.questions[i])}: cited ${c.cited} of ${c.n}, first ${c.first}, shown to JEV ${c.shown} of ${c.n}">${c.cited}/${c.n}${c.first ? "<sup>★</sup>" : ""}</td>`;
  };
  $("#heatmap").innerHTML = `<div class="tablewrap"><table class="data heat"><thead><tr><th>Version</th>${g.questions.map((q, i) => `<th title="${esc(q)}">Q${i + 1}</th>`).join("")}</tr></thead><tbody>` +
    g.versions.map(v => `<tr><td class="vname">${esc(v.name)}</td>${g.questions.map((_, i) => cell(v.version, i)).join("")}</tr>`).join("") +
    `</tbody></table></div><p class="hint tiny">★ = cited first at least once. Questions: ${g.questions.map((q, i) => `<b>Q${i + 1}</b> ${esc(q)}`).join(" · ")}</p>`;
  $$("#heatmap .hcell[data-v]").forEach(td => {
    const open = () => safe(() => showAnswers(td.dataset.v, +td.dataset.i));
    td.onclick = open;
    td.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  });
}

async function showAnswers(version, i) {
  $$("#heatmap .hcell").forEach(td => td.classList.toggle("sel", td.dataset.v === version && +td.dataset.i === i));
  const q = new URLSearchParams({ slug: P.product.slug, run: RUNDETAIL.run, version, i, holdout: HEATSET === "holdout" ? "1" : "0" });
  const d = await api("/api/run/answers?" + q);
  const name = RUNDETAIL[HEATSET].versions.find(v => v.version === version)?.name || version;
  $("#answers").innerHTML = `<h3>JEV's answers: ${esc(name)}</h3><p class="hint">${esc(d.question)}</p>` + d.answers.map(a => {
    const lab = a.labels && Object.keys(a.labels).length ? `<div class="hint tiny">JEV saw: ${Object.entries(a.labels).map(([b, l]) => `${esc(l)} = ${esc(b)}`).join(", ")}</div>` : "";
    return `<div class="answer ${a.cited ? "cited" : ""}"><div class="row between"><b>Repeat ${a.repeat + 1}</b>
      <span>${a.cited ? (a.first ? '<span class="good">✔ cited first</span>' : '<span class="good">✔ cited</span>') : a.in_context ? '<span class="badtxt">shown, not cited</span>' : '<span class="hint">not in the top results</span>'}${a.forced ? ' <span class="tag">forced in</span>' : ""} <span class="hint tiny">search rank #${a.bm25_rank}</span></span></div>
      ${lab}<div class="answer-text">${typeof mdLite === "function" ? mdLite(a.answer || "") : esc(a.answer)}</div>
      <div class="hint tiny">Cited: ${a.cited_brands.map(esc).join(", ") || "nothing"}</div></div>`;
  }).join("");
  $("#answers").scrollIntoView({ block: "nearest", behavior: "smooth" });
}

function renderVersions() {
  const vs = RUNDETAIL?.variants || [];
  $("#versions-list").innerHTML = vs.length ? vs.map(v => `<article class="version-card">
      <h3>${esc(v.name)}</h3>
      <div class="hint tiny">${v.words} words${v.unknown_numbers.length ? ` · <span class="warntxt">numbers not in the fact sheet: ${esc(v.unknown_numbers.join(", "))}</span>` : " · every number is in the fact sheet"}</div>
      <iframe class="vframe" sandbox title="${esc(v.name)}" data-src="${fileUrl(RUNDETAIL.run, v.file)}"></iframe>
      <a href="${fileUrl(RUNDETAIL.run, v.file)}" target="_blank" rel="noopener">Open</a> · <a href="${fileUrl(RUNDETAIL.run, v.file, 1)}">Download</a></article>`).join("")
    : `<p class="hint">No page files in this run.</p>`;
  // load the texts only when the Versions sub-tab is shown
  const load = () => $$("#versions-list iframe[data-src]").forEach(f => { f.src = f.dataset.src; f.removeAttribute("data-src"); });
  if (!$('#tab-run .subpanel[data-sub="versions"]').classList.contains("hidden")) load();
  else $('#tab-run .subtabs [data-sub="versions"]').addEventListener("click", load, { once: true });
}

// --- structured data (Web page › Structured data, Model by model) ------------------------------
function renderStructured(el, sd) {
  if (!el) return;
  if (!sd) { el.innerHTML = `<p class="hint">Save the page once to build its structured data.</p>`; return; }
  const icon = { ok: "✔", warn: "▲", bad: "✖" };
  el.innerHTML = `<ul class="checks">${sd.checks.map(c => `<li class="st-${c.status}"><span class="icon">${icon[c.status]}</span> <b>${esc(c.check)}</b> <span class="hint">${esc(c.note)}</span></li>`).join("")}</ul>
    <div class="row"><button type="button" class="sd-copy">Copy the JSON-LD</button>
      <a href="https://search.google.com/test/rich-results" target="_blank" rel="noopener">Test it in Google's Rich Results Test ↗</a>
      <span class="hint tiny">(choose “Code” and paste it)</span></div>
    <pre class="jsonld">${esc(sd.pretty)}</pre>`;
  $(".sd-copy", el).onclick = () => {
    const code = `<script type="application/ld+json">\n${sd.pretty}\n<\/script>`;
    (navigator.clipboard?.writeText(code) || Promise.reject()).then(() => toast("JSON-LD copied")).catch(() => toast("Select the code below and copy it"));
  };
}

// --- Wiki tab ------------------------------------------------------------------------------------
let WIKIFILE = null, rawPoll = null;
async function loadWiki() {
  WIKI = await api("/api/wiki?slug=" + encodeURIComponent(P.product.slug));
  $("#wiki-root").textContent = WIKI.root;
  renderWikiFiles();
  $("#wiki-log").innerHTML = WIKI.log ? logHtml(WIKI.log) : `<p class="hint">No change log yet: the first save here creates <code>log.md</code>.</p>`;
  renderRaw(WIKI.raw, WIKI.raw_job);
  if (WIKIFILE && WIKI.files.some(f => f.path === WIKIFILE)) openWikiFile(WIKIFILE, true);
  else if (!WIKIFILE) setWikiEditor(null);
}
function renderWikiFiles() {
  const f = ($("#wiki-filter").value || "").toLowerCase();
  const files = WIKI.files.filter(x => !f || (x.path + " " + x.title + " " + x.type).toLowerCase().includes(f));
  $("#wiki-files").innerHTML = files.map(x => `<li data-path="${esc(x.path)}" class="${x.path === WIKIFILE ? "sel" : ""} ${x.special ? "special" : ""}">
      ${esc(x.title)} <span class="meta">${esc(x.path)} · ${esc(x.type || "—")}${x.used_by.length ? ` · on ${x.used_by.length} page${x.used_by.length > 1 ? "s" : ""}` : ""}</span></li>`).join("")
    || `<li class="hint">No file matches.</li>`;
  $$("#wiki-files li[data-path]").forEach(li => li.onclick = () => safe(() => openWikiFile(li.dataset.path)));
}
$("#wiki-filter").addEventListener("input", () => WIKI && renderWikiFiles());

function setWikiEditor(file, text) {
  const editable = file && file.path !== "log.md";
  $("#wiki-newpath").classList.add("hidden");
  $("#wiki-path").textContent = file ? file.path : "Pick a file on the left, or make a new concept";
  $("#wiki-used").textContent = file && file.used_by.length ? `Used on: ${file.used_by.join(", ")}` : file ? "Not used by a page of our website version yet" : "";
  $("#wiki-text").value = text || "";
  $("#wiki-text").disabled = !editable;
  $("#wiki-save").disabled = !editable;
  $("#wiki-save").textContent = "Save";
  $("#wiki-text").dataset.orig = text || "";
  if (file && file.path === "log.md") $("#wiki-used").textContent = "The change log is read-only here: see Change log.";
}
async function openWikiFile(path, keepResult) {
  if (!keepResult && WIKIFILE && $("#wiki-text").value !== $("#wiki-text").dataset.orig && !confirm("Discard your unsaved changes?")) return;
  const d = await api(`/api/wiki/file?slug=${encodeURIComponent(P.product.slug)}&path=${encodeURIComponent(path)}`);
  WIKIFILE = path;
  setWikiEditor(WIKI.files.find(x => x.path === path), d.text);
  if (!keepResult) $("#wiki-result").innerHTML = "";
  renderWikiFiles();
}
$("#wiki-new").onclick = () => {
  if (WIKI?.single) return toast("This product's wiki is a single file: edit it directly");
  WIKIFILE = null; renderWikiFiles();
  $("#wiki-path").textContent = "New concept";
  $("#wiki-used").textContent = "";
  $("#wiki-newpath").classList.remove("hidden"); $("#wiki-newpath").value = ""; $("#wiki-newpath").focus();
  $("#wiki-text").disabled = false; $("#wiki-save").disabled = false; $("#wiki-save").textContent = "Create";
  $("#wiki-text").value = "---\ntype: Technology\ntitle: \ndescription: One line about what this concept is.\n---\n# Title\n\nFacts, each with its Danfoss source as a footnote.[^1]\n\n[^1]: Document code or danfoss.com URL, date.\n";
  $("#wiki-text").dataset.orig = $("#wiki-text").value;
  $("#wiki-result").innerHTML = "";
};
$("#wiki-save").onclick = () => {
  const creating = !$("#wiki-newpath").classList.contains("hidden");
  const path = creating ? $("#wiki-newpath").value.trim() : WIKIFILE;
  if (!path) return toast("Give the new file a name, e.g. technologies/new-plate.md");
  const btn = $("#wiki-save"); btn.disabled = true;
  safe(async () => {
    try {
      const r = await api("/api/wiki/save", { slug: P.product.slug, path, text: $("#wiki-text").value, note: $("#wiki-note").value, create: creating });
      WIKI = r; WIKIFILE = path;
      $("#wiki-note").value = "";
      $("#wiki-result").innerHTML = !r.changed ? `<p class="hint">Nothing changed.</p>`
        : `<div class="okbox">✔ ${r.created ? "Created" : "Saved"} and noted in the change log. Our website version was rebuilt from the wiki.</div>`
          + (r.new_numbers.length ? `<div class="warnbox">⚠ New numbers: <b>${esc(r.new_numbers.join(", "))}</b>. Each needs a Danfoss source (document code or danfoss.com URL) in a footnote.</div>` : "")
          + (r.removed_numbers.length ? `<p class="hint">Numbers removed: ${esc(r.removed_numbers.join(", "))}</p>` : "")
          + (r.site_error ? `<p class="hint">Our website version could not be rebuilt: ${esc(r.site_error)}</p>` : "");
      toast(r.changed ? "Wiki saved" : "Nothing changed");
      $("#wiki-log").innerHTML = WIKI.log ? logHtml(WIKI.log) : "";
      await openWikiFile(path, true);
      // the fact sheet changed: pages, checks and the Run tab read it again
      SITE = null; WEB = null; CAT = null; OV = null;
      P.fact_sheet = (await api("/api/product?slug=" + encodeURIComponent(P.product.slug))).fact_sheet;
      $("#fact-sheet").textContent = P.fact_sheet;
    } finally { btn.disabled = false; }
  });
};
function logHtml(md) {
  return md.split("\n").map(l => {
    const t = esc(l).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
    if (/^#\s/.test(l)) return "";
    if (/^##\s/.test(l)) return `<h3>${t.replace(/^##\s*/, "")}</h3>`;
    if (/^\s*\*\s/.test(l)) return `<p class="logitem${/^\s{2,}/.test(l) ? " sub" : ""}">${t.replace(/^\s*\*\s/, "")}</p>`;
    return t.trim() ? `<p>${t}</p>` : "";
  }).join("");
}

function renderRaw(raw, job) {
  $("#raw-folder").textContent = raw.folder + "/";
  const saved = raw.sources.filter(x => x.saved).length;
  $("#raw-state").textContent = `${saved} of ${raw.sources.length} cited documents saved` + (raw.used_by_writer ? "" : " · not used by the writer yet (the first download turns it on)");
  $("#raw-list").innerHTML = raw.sources.length ? `<div class="tablewrap"><table class="data"><thead><tr><th>Document the wiki cites</th><th>Saved as</th><th>Words</th></tr></thead><tbody>` +
    raw.sources.map(x => `<tr><td><a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.url)}</a></td><td>${x.saved ? `<span class="good">✔</span> ${esc(x.file)}` : '<span class="badtxt">missing</span>'}</td><td>${x.words || "–"}</td></tr>`).join("") + "</tbody></table></div>"
    + (raw.other_files.length ? `<p class="hint tiny">Also in the folder (added by hand): ${raw.other_files.map(esc).join(", ")}</p>` : "")
    : `<p class="hint">The wiki cites no document with a web address. Add PDFs by hand to the folder and press Download to convert them.</p>`;
  const log = $("#raw-log");
  log.classList.toggle("hidden", !job);
  if (job) { log.textContent = job.log.join("\n"); log.scrollTop = log.scrollHeight; }
  $("#raw-update").disabled = job?.status === "running";
  clearTimeout(rawPoll);
  if (job?.status === "running") rawPoll = setTimeout(() => safe(async () => {
    const w = await api("/api/wiki?slug=" + encodeURIComponent(P.product.slug));
    WIKI = w; renderRaw(w.raw, w.raw_job);
    if (w.raw_job?.status === "done") toast("Documents downloaded");
  }), 1500);
}
$("#raw-update").onclick = () => safe(async () => {
  await api("/api/raw/update", { slug: P.product.slug });
  renderRaw(WIKI.raw, { status: "running", log: ["Starting…"] });
});

// --- Citations › Alerts: new models and ranking changes ---------------------------------------
let WATCH = null;
async function loadWatch() {
  WATCH = await api("/api/watch");
  renderWatch();
}
function renderWatch() {
  const w = WATCH, c = w.config;
  const badge = $("#alert-count");
  badge.textContent = w.unread; badge.classList.toggle("hidden", !w.unread);
  $("#rail-alert")?.classList.toggle("hidden", !w.unread);
  $("#watch-status").innerHTML = `Last check: <b>${w.last_check ? esc(w.last_check.replace("T", " ")) : "never"}</b>`
    + (w.next_check ? ` · next: ${esc(w.next_check.replace("T", " "))}` : "") + ` · every ${c.hours} h`
    + ` · Gemini versions Atlas knows: ${w.watching.gemini_versions.join(", ") || "–"}`
    + `<br>Emails go to <b>${esc(c.to)}</b>` + (c.invented ? ` <span class="warntxt">(an invented address: emails are saved in app/outbox/ until you set a real one)</span>`
      : !c.smtp_host ? ` <span class="warntxt">(no SMTP server set: emails are saved in app/outbox/)</span>` : "")
    + (w.last_error ? `<br><span class="warntxt">Some feeds could not be read: ${esc(w.last_error)}</span>` : "");
  $("#watch-alerts").innerHTML = w.alerts.length ? w.alerts.map(a => `<article class="alert ${a.read ? "" : "unread"}">
      <div class="row between"><b>${a.kind === "model" ? "New model" : "Ranking and authority"}: ${esc(a.title)}</b><span class="hint tiny">${esc(a.created.replace("T", " "))}</span></div>
      <p class="hint">${a.kind === "model" ? "The results were measured with older models: the pages probably need a new round of tests. Add the model in Settings, pick it for JEV, update Citations and run the test again."
        : "Google changed how it ranks or trusts pages: check whether Danfoss's citations moved and re-test the pages."}</p>
      ${a.items.length ? `<ul class="news">${a.items.map(i => `<li><a href="${esc(i.link)}" target="_blank" rel="noopener">${esc(i.title)}</a> <span class="hint tiny">${esc(i.source)} · ${esc(i.date.slice(0, 16))}</span></li>`).join("")}</ul>` : ""}
      <p class="hint tiny">Email: ${esc(a.email || "")}</p></article>`).join("")
    : `<p class="hint">No alerts yet. ${w.last_check ? "Nothing new since the last check." : "Press <b>Check the news now</b> for a first check."}</p>`;
}
$("#watch-check").onclick = () => {
  const btn = $("#watch-check"); btn.disabled = true; btn.textContent = "Reading the news…";
  safe(async () => {
    try {
      WATCH = await api("/api/watch/check", {});
      renderWatch();
      toast(WATCH.new ? `${WATCH.new} new alert${WATCH.new > 1 ? "s" : ""}` : "Nothing new");
      S.watch = { unread: WATCH.unread, latest: WATCH.alerts.find(a => !a.read)?.title, kind: WATCH.alerts.find(a => !a.read)?.kind };
      renderBanner();
    } finally { btn.disabled = false; btn.textContent = "Check the news now"; }
  });
};
$("#watch-read").onclick = () => safe(async () => {
  await api("/api/watch/read", {});
  S.watch = { unread: 0 }; renderBanner(); await loadWatch();
});
$("#watch-settings").onclick = e => { e.preventDefault(); renderSettings(); $("#settings").showModal(); $("#alerts-settings").scrollIntoView(); };

// --- Settings › Alerts by email ---------------------------------------------------------------
function renderAlertSettings() {
  safe(async () => {
    const w = await api("/api/watch"), c = w.config, f = $("#alert-form");
    f.elements.ALERT_EMAIL.value = c.invented ? "" : c.to;
    f.elements.ALERT_EMAIL.placeholder = "atlas-alerts@example.com (invented: replace it)";
    f.elements.SMTP_HOST.value = c.smtp_host; f.elements.SMTP_PORT.value = c.smtp_port;
    f.elements.SMTP_FROM.value = c.smtp_from; f.elements.SMTP_USER.value = c.smtp_user;
    f.elements.SMTP_PASSWORD.value = ""; f.elements.SMTP_PASSWORD.placeholder = c.has_password ? "•••••••• (unchanged)" : "";
    f.elements.WATCH_HOURS.value = c.hours; f.elements.CITATIONS_EVERY_DAYS.value = c.citations_days;
    $("#alert-hint").innerHTML = `New-model and ranking alerts go to <b>${esc(c.to)}</b>${c.invented ? " (invented for now)" : ""}. Saved in <code>.env</code> on this computer only.`;
  });
}
$("#alert-form").onsubmit = e => {
  e.preventDefault();
  const f = e.target;
  safe(async () => {
    for (const el of f.elements) {
      if (!el.name || (el.name === "SMTP_PASSWORD" && !el.value)) continue;  // empty password = keep the saved one
      await api("/api/key", { env: el.name, value: String(el.value || "").trim() });
    }
    toast("Alert settings saved"); renderAlertSettings();
    if (WATCH) await loadWatch();
  });
};
$("#alert-test").onclick = () => safe(async () => {
  $("#alert-test-result").textContent = "Sending…";
  const r = await api("/api/watch/test", {});
  $("#alert-test-result").textContent = r.result;
});
