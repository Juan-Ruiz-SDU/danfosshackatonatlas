"use strict";
// Overview tab, before/after slider, command palette (Ctrl+K), presentation mode and theme.
// Uses the helpers of app.js ($, $$, esc, pct, api, safe, store, recall, go, showTab) and how.js (svgEl, tipBox, showTip, hideTip).

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");

// --- theme: automatic → light → dark ----------------------------------------------------------
function applyTheme(t) {
  if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
  else delete document.documentElement.dataset.theme;
  const name = { light: "light", dark: "dark" }[t] || "automatic (follows your computer)";
  $("#toggle-theme").title = `Theme: ${name}. Click to change.`;
}
// stored as plain text (not JSON): the inline script in <head> reads it before the page draws
function savedTheme() { try { return localStorage.getItem("atlas.theme") || "auto"; } catch (e) { return "auto"; } }
$("#toggle-theme").onclick = () => {
  const order = ["auto", "light", "dark"];
  const next = order[(order.indexOf(savedTheme()) + 1) % order.length];
  try { localStorage.setItem("atlas.theme", next); } catch (e) {}
  applyTheme(next);
  toast(`Theme: ${next === "auto" ? "automatic" : next}`);
};
applyTheme(savedTheme());

// --- Overview -----------------------------------------------------------------------------------
const RANK_KIND = { passage: "best passage", page: "whole page" };

async function loadOverview() {
  const slug = P.product.slug;
  OV = { slug, kind: recall("ovKind", "passage") };
  const mine = () => OV && OV.slug === slug && P && P.product.slug === slug;
  $$("#ov-rank-kind button").forEach(b => b.classList.toggle("on", b.dataset.kind === OV.kind));
  renderOvStats();
  renderRunsChart();
  $("#ov-title").textContent = "Measuring the page…";
  $("#ov-lede").textContent = "Ranking your copy and Danfoss's page against the competitor pages for every buyer question.";
  $("#ov-dumbbell").innerHTML = `<div class="skeleton" aria-hidden="true"></div>`;
  // Gemini's real citations and the website comparison load side by side
  const cit = api("/api/citations?slug=" + encodeURIComponent(slug)).then(c => {
    if (!mine()) return;
    OV.cit = c; renderOvStats(); renderGeminiChart();
  }).catch(e => { if (mine()) $("#ov-gemini").innerHTML = `<p class="hint">${esc(e.message)}</p>`; });
  const site = (async () => {
    const s = await api("/api/site?slug=" + encodeURIComponent(slug));
    if (!mine()) return;
    if (!s.site || !s.lab_page) { OV.siteMissing = true; return renderHero(); }
    OV.page = s.site.pages.find(x => x.id === s.lab_page);
    const pg = await api(`/api/site/page?slug=${encodeURIComponent(slug)}&id=${encodeURIComponent(s.lab_page)}`);
    if (!mine()) return;
    OV.bm = pg.bm25; OV.pageId = s.lab_page;
    renderHero(true);
  })().catch(e => { if (mine()) { OV.siteError = e.message; renderHero(); } });
  await Promise.all([cit, site]);
}
$$("#ov-rank-kind button").forEach(b => b.onclick = () => {
  if (!OV) return;
  OV.kind = b.dataset.kind; store("ovKind", OV.kind);
  $$("#ov-rank-kind button").forEach(x => x.classList.toggle("on", x === b));
  renderHero(false);
});

function mean(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN; }
function fmt1(x) { return Number.isFinite(x) ? x.toFixed(1) : "–"; }

function renderHero(animate) {
  const host = $("#ov-dumbbell");
  $("#ov-hero-controls").classList.toggle("hidden", !OV.bm);
  if (!OV.bm || !OV.bm.rows.length) {
    $("#ov-title").textContent = OV.siteMissing ? "Load the product pages to measure them" : "The page can't be measured yet";
    $("#ov-lede").innerHTML = OV.siteMissing
      ? `To compare the product page with the competitors, open <a href="#web/site">Web page › Site</a>, then <b>Pages to edit › Load the pages</b>.`
      : esc(OV.siteError || "No buyer questions or competitor pages yet.") + ` Tick questions in <a href="#run/questions">Run › Buyer questions</a> and add competitor pages in <a href="#run/product">Run › Product</a>.`;
    host.innerHTML = "";
    return;
  }
  const k = OV.kind, bm = OV.bm, n = bm.rows.length;
  const before = bm.rows.map(r => r.versions.original[k + "_rank"]);
  const after = bm.rows.map(r => r.versions.rebuilt[k + "_rank"]);
  const mb = mean(before), ma = mean(after);
  const topB = before.filter(r => r <= bm.top_k).length, topA = after.filter(r => r <= bm.top_k).length;
  const verb = ma < mb - 0.05 ? `up from ${fmt1(mb)}` : ma > mb + 0.05 ? `down from ${fmt1(mb)}` : "the same as Danfoss's page";
  $("#ov-title").innerHTML = `The page now ranks <span class="fig">${fmt1(ma)}</span> on average, ${verb.replace(fmt1(mb), `<span class="fig was">${fmt1(mb)}</span>`)}`;
  const forQ = n === 1 ? "for the one buyer question ticked in Run" : `for each of the ${n} buyer questions`;
  const inTop = n === 1
    ? `Your copy is ${topA ? "" : "not "}in the top ${bm.top_k}; Danfoss's page is ${topB ? "" : "not "}in it. Tick more questions in <a href="#run/questions">Run › Buyer questions</a> for a fairer picture.`
    : `Your copy is in the top ${bm.top_k} for <b>${topA} of ${n}</b> questions; Danfoss's page for ${topB}.`;
  $("#ov-lede").innerHTML = `Rank of the page's ${RANK_KIND[k]} among ${bm.pages} pages (the saved competitor pages and this one) ${forQ}. Lower is better: the AI answer box only reads the top ${bm.top_k}. ${inTop}`;
  drawDumbbell(host, bm, k, animate && !REDUCED.matches);
}

function drawDumbbell(host, bm, k, animate) {
  host.innerHTML = `<div class="legend"><span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="pt s2"/></svg>Danfoss's page (as copied)</span>
    <span><svg width="12" height="12" aria-hidden="true"><circle cx="6" cy="6" r="4.5" class="pt s1"/></svg>Your copy</span>
    <span><i class="sw zone"></i>Read by the AI (top ${bm.top_k})</span></div>`;
  tipBox(host);
  const rows = bm.rows, rowH = 34, m = { t: 26, r: 18, b: 10, l: 18 };
  const W = 640, H = m.t + rows.length * rowH + m.b;
  const maxR = Math.max(bm.pages, ...rows.map(r => Math.max(r.versions.original[k + "_rank"], r.versions.rebuilt[k + "_rank"])));
  const x = r => m.l + (r - 1) / Math.max(1, maxR - 1) * (W - m.l - m.r);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "viz dumb", role: "img",
    "aria-label": `Rank per buyer question, Danfoss's page and your copy. Lower is better.` }, host);
  // the zone the answer box reads, then the rank axis
  svgEl("rect", { x: m.l - 8, y: m.t - 18, width: x(bm.top_k + 0.5) - m.l + 8, height: H - m.t - m.b + 18, rx: 6, class: "zone" }, svg);
  const step = maxR > 14 ? 2 : 1;
  for (let r = 1; r <= maxR; r += step)
    svgEl("text", { x: x(r), y: m.t - 8, class: "axis", "text-anchor": "middle" }, svg).textContent = "#" + r;
  rows.forEach((row, i) => {
    const y = m.t + i * rowH + rowH / 2;
    const b = row.versions.original[k + "_rank"], a = row.versions.rebuilt[k + "_rank"];
    svgEl("line", { x1: m.l, x2: W - m.r, y1: y, y2: y, class: "grid" }, svg);
    const g = svgEl("g", { class: "drow" }, svg);
    svgEl("line", { x1: x(b), x2: x(a), y1: y, y2: y, class: "link" + (a < b ? " better" : a > b ? " worse" : "") }, g);
    svgEl("circle", { cx: x(b), cy: y, r: 6, class: "pt s2" }, g);
    const dot = svgEl("circle", { cx: x(a), cy: y, r: 6.5, class: "pt s1" }, g);
    if (animate && a !== b) {
      dot.style.transform = `translateX(${x(b) - x(a)}px)`;
      dot.style.transition = `transform .9s cubic-bezier(.2,.7,.2,1) ${120 + i * 45}ms`;
      requestAnimationFrame(() => requestAnimationFrame(() => { dot.style.transform = "translateX(0)"; }));
    }
    const hit = svgEl("rect", { x: 0, y: y - rowH / 2, width: W, height: rowH, fill: "transparent", tabindex: 0,
      "aria-label": `${row.question}: Danfoss's page #${b}, your copy #${a}` }, g);
    const tip = () => `<b>${esc(row.question)}</b><div>Danfoss's page: <b>#${b}</b> · your copy: <b>#${a}</b>${a < b ? ` <span class="good">▲${b - a}</span>` : a > b ? ` <span class="badtxt">▼${a - b}</span>` : ""}</div>` +
      (row.versions.rebuilt.best_heading ? `<div class="hint">Best passage: ${esc(row.versions.rebuilt.best_heading.split(" > ").slice(-1)[0])}</div>` : "");
    hit.addEventListener("pointermove", ev => { const r = host.getBoundingClientRect(); showTip(host, tip(), ev.clientX - r.left, ev.clientY - r.top); });
    hit.addEventListener("focus", () => { const r = host.getBoundingClientRect(), hb = hit.getBoundingClientRect(); showTip(host, tip(), hb.left - r.left + hb.width / 2, hb.top - r.top); });
    hit.addEventListener("pointerleave", () => hideTip(host));
    hit.addEventListener("blur", () => hideTip(host));
  });
}

function runLabel(run) {  // 2026-11-14_164814 -> 14 Nov 16:48
  const m = /^(\d{4})-(\d{2})-(\d{2})_(\d{2})(\d{2})/.exec(run || "");
  if (!m) return run;
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m[2] - 1];
  return `${+m[3]} ${mon} ${m[4]}:${m[5]}`;
}

function renderOvStats() {
  const runs = (P.runs || []).filter(r => !r.unfinished);
  const r = runs[0], t = r?.targets;
  const nq = P.questions.filter(q => q.enabled).length;
  const latest = OV?.cit?.history?.runs?.[0];
  const cell = (value, label, note = "", cls = "") => `<div class="readout ${cls}"><div class="v">${value}</div><div class="l">${label}</div>${note ? `<div class="note">${note}</div>` : ""}</div>`;
  const delta = r?.baseline ? Math.round(100 * (r.winner.share - r.baseline.share)) : null;
  $("#ov-stats").innerHTML = [
    r ? cell(pct(r.winner.share), "citation share of the best version",
      `${esc(r.winner.name)} · run ${esc(runLabel(r.run))}` + (delta != null ? `<br>${delta >= 0 ? "+" : "−"}${Math.abs(delta)} points vs Danfoss's current page (${pct(r.baseline.share)})` : ""))
      : cell("–", "citation share", `No run yet. <a href="#run/run">Start one</a>.`),
    r ? cell(pct(r.winner.first), "of answers cite it first", `${pct(r.winner.cited)} of answers cite it at all`) : "",
    r?.holdout ? cell(r.holdout.winner_still_first ? "✔ Holds" : "▲ Not first", "on holdout questions",
      `${r.holdout.questions} questions never used for writing · winner ${pct(r.holdout.winner_share)}` +
      (r.holdout.baseline_share != null ? ` vs Danfoss's page ${pct(r.holdout.baseline_share)}` : ""), r.holdout.winner_still_first ? "is-ok" : "is-bad") : "",
    t ? cell(t.met ? "✔ Met" : "✘ Missed", "citation targets",
      `cited in ${t.cited_pct}% (goal ${t.cited_target}%) · first ${t.first_count} times (goal ${t.first_target})`, t.met ? "is-ok" : "is-bad") : "",
    latest ? cell(`${latest.danfoss_answers}<small> of ${latest.prompts}</small>`, "Gemini answers that cite Danfoss",
      `real Google Search, update of ${esc(latest.date)}`) : cell("–", "Gemini answers that cite Danfoss", OV?.cit ? `No update yet. <a href="#citations/ask">Ask Gemini</a>.` : "loading…"),
    cell(`${nq}<small> questions</small>`, "in the test", `against ${P.pages.competitors} competitor pages`),
  ].join("");
}

// One y-axis (0–100%), thin lines, crosshair + tooltip, legend for 2 series, goal line optional.
function lineChart(host, { series, labels, goal, goalLabel, empty }) {
  host.innerHTML = "";
  const n = labels.length;
  if (!n) { host.innerHTML = `<p class="hint">${empty}</p>`; return; }
  if (series.length > 1) host.insertAdjacentHTML("beforeend", `<div class="legend">${series.map(s => `<span><i class="sw ${s.cls}"></i>${esc(s.name)}</span>`).join("")}${goal != null ? `<span><i class="sw goal"></i>${esc(goalLabel)}</span>` : ""}</div>`);
  else if (goal != null) host.insertAdjacentHTML("beforeend", `<div class="legend"><span><i class="sw ${series[0].cls}"></i>${esc(series[0].name)}</span><span><i class="sw goal"></i>${esc(goalLabel)}</span></div>`);
  tipBox(host);
  const W = 560, H = 230, m = { t: 12, r: 16, b: 28, l: 40 };
  const x = i => n === 1 ? (m.l + W - m.r) / 2 : m.l + i / (n - 1) * (W - m.l - m.r);
  const y = v => m.t + (1 - v) * (H - m.t - m.b);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "viz", role: "img", "aria-label": series.map(s => s.name).join(" and ") + " over time" }, host);
  [0, .25, .5, .75, 1].forEach(v => {
    svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "grid" }, svg);
    svgEl("text", { x: m.l - 8, y: y(v) + 4, class: "axis", "text-anchor": "end" }, svg).textContent = Math.round(v * 100) + "%";
  });
  const every = Math.max(1, Math.ceil(n / 6));
  labels.forEach((l, i) => { if (i % every === 0 || i === n - 1) svgEl("text", { x: x(i), y: H - 8, class: "axis", "text-anchor": "middle" }, svg).textContent = l; });
  if (goal != null) svgEl("line", { x1: m.l, x2: W - m.r, y1: y(goal), y2: y(goal), class: "goal" }, svg);
  for (const s of series) {
    const pts = s.values.map((v, i) => v == null ? null : [x(i), y(v)]).filter(Boolean);
    if (pts.length > 1) svgEl("polyline", { points: pts.map(p => p.join(",")).join(" "), class: `line ${s.cls}` }, svg);
    pts.forEach(([px, py]) => svgEl("circle", { cx: px, cy: py, r: 4.5, class: `dot ${s.cls}` }, svg));
  }
  const cross = svgEl("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
  const hit = svgEl("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width;
    const i = n === 1 ? 0 : Math.max(0, Math.min(n - 1, Math.round((px - m.l) / (W - m.l - m.r) * (n - 1))));
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    const hr = host.getBoundingClientRect();
    showTip(host, `<b>${esc(labels[i])}</b>` + series.map(s => `<div><i class="sw ${s.cls}"></i>${esc(s.name)}: <b>${s.values[i] == null ? "–" : pct(s.values[i])}</b></div>`).join("") +
      (goal != null ? `<div class="hint">${esc(goalLabel)}</div>` : ""), ev.clientX - hr.left, ev.clientY - hr.top);
  });
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(host); });
}

function renderRunsChart() {
  const runs = (P.runs || []).filter(r => !r.unfinished).slice().reverse();
  lineChart($("#ov-runs"), {
    labels: runs.map(r => runLabel(r.run)),
    series: [{ name: "Best new version", cls: "s1", values: runs.map(r => r.winner.share) },
             { name: "Danfoss's current page", cls: "s2", values: runs.map(r => r.baseline ? r.baseline.share : null) }],
    empty: `No finished run yet for this product. <a href="#run/run">Start a run</a>: the best version and a report appear in Run › Results.`,
  });
}

function renderGeminiChart() {
  const h = OV.cit.history.runs.slice().reverse();
  const t = OV.cit.targets;
  lineChart($("#ov-gemini"), {
    labels: h.map(r => r.date.slice(5, 10)),
    series: [{ name: "Answers that cite Danfoss", cls: "s1", values: h.map(r => r.prompts ? r.danfoss_answers / r.prompts : null) }],
    goal: t ? t.cited_pct / 100 : null, goalLabel: t ? `Target: ${t.cited_pct}% of answers` : "",
    empty: OV.cit.has_key ? `No update yet. <a href="#citations/ask">Ask Gemini</a> to record what it cites.`
      : `Needs a Gemini key (⚙ Settings). Then <a href="#citations/ask">ask Gemini</a> to record what it cites.`,
  });
}

// --- Web page › Before / after: two pages, one divider ----------------------------------------
let CMP_KEY = null;
function renderCompare() {
  if (!WEB || !PAGESEL) return;
  const key = PAGESEL + "|" + WEB.copy.changed;
  if (key === CMP_KEY) return;
  CMP_KEY = key;
  $("#web-before").src = `/api/site/original?slug=${encodeURIComponent(P.product.slug)}&id=${encodeURIComponent(PAGESEL)}`;
  $("#web-after").src = pageUrl(`site/${PAGESEL}.html`) + "?t=" + Date.now();
}
function setCompare(v) {
  v = Math.max(0, Math.min(100, +v));
  $("#web-compare").style.setProperty("--pos", v + "%");
  $("#web-compare-range").value = v;
}
$("#web-compare-range").addEventListener("input", e => setCompare(e.target.value));
(() => {
  const box = $("#web-compare"), handle = $(".compare-handle", box);
  const move = ev => { const r = box.getBoundingClientRect(); setCompare((ev.clientX - r.left) / r.width * 100); };
  handle.addEventListener("pointerdown", ev => { handle.setPointerCapture(ev.pointerId); box.classList.add("dragging"); move(ev); });
  handle.addEventListener("pointermove", ev => { if (box.classList.contains("dragging")) move(ev); });
  handle.addEventListener("pointerup", () => box.classList.remove("dragging"));
  handle.addEventListener("pointercancel", () => box.classList.remove("dragging"));
  // the two pages scroll together (same position as a share of each page's length)
  let syncing = false;
  const sync = (from, to) => {
    try {
      const a = from.contentWindow, b = to.contentWindow;
      a.addEventListener("scroll", () => {
        if (syncing) return; syncing = true;
        const fa = a.document.documentElement, fb = b.document.documentElement;
        const ratio = fa.scrollTop / Math.max(1, fa.scrollHeight - a.innerHeight);
        b.scrollTo(0, ratio * Math.max(0, fb.scrollHeight - b.innerHeight));
        requestAnimationFrame(() => { syncing = false; });
      });
    } catch (e) { /* not the same origin: no sync */ }
  };
  $("#web-before").addEventListener("load", () => sync($("#web-before"), $("#web-after")));
  $("#web-after").addEventListener("load", () => sync($("#web-after"), $("#web-before")));
  setCompare(50);
})();

// --- command palette ---------------------------------------------------------------------------
let CMDK_ITEMS = [], CMDK_SEL = 0;
function cmdkItems() {
  const items = [];
  for (const b of $$(".tabs [data-tab]")) {
    const tab = b.dataset.tab, name = $(".t", b).textContent;
    items.push({ group: "View", label: name, hint: $(".d", b).textContent, run: () => go(tab) });
    for (const sb of $$(`#tab-${tab} .subtabs [data-sub]`))
      items.push({ group: "View", label: `${name} › ${sb.textContent.replace(/^\d+/, "").trim()}`, hint: "", run: () => go(`${tab}/${sb.dataset.sub}`) });
  }
  for (const p of S?.products || [])
    items.push({ group: "Product", label: p.name, hint: p.slug === P?.product.slug ? "current" : "switch to this product",
      run: () => { const s = $("#product-select"); s.value = p.slug; s.dispatchEvent(new Event("change")); } });
  items.push(
    { group: "Action", label: "Open settings", hint: "keys, AIs, targets", run: () => $("#open-settings").click() },
    { group: "Action", label: "Open the assistant", hint: "chat about the results", run: () => { if ($("#chat").hidden) $("#open-chat").click(); } },
    { group: "Action", label: "Add a product from a brochure", hint: "PDF, Word or text", run: () => $("#open-import").click() },
    { group: "Action", label: "Start the presentation", hint: "a guided tour for the pitch", run: () => present(0) },
    { group: "Action", label: "Switch theme", hint: "automatic, light, dark", run: () => $("#toggle-theme").click() },
  );
  return items;
}
function renderCmdk() {
  const q = $("#cmdk-input").value.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const all = cmdkItems();
  CMDK_ITEMS = all.filter(it => q.every(w => (it.label + " " + it.hint + " " + it.group).toLowerCase().includes(w))).slice(0, 14);
  CMDK_SEL = Math.min(CMDK_SEL, Math.max(0, CMDK_ITEMS.length - 1));
  $("#cmdk-list").innerHTML = CMDK_ITEMS.map((it, i) => `<li role="option" id="cmdk-${i}" aria-selected="${i === CMDK_SEL}" data-i="${i}">
      <span class="g">${esc(it.group)}</span><span class="lb">${esc(it.label)}</span><span class="h">${esc(it.hint)}</span></li>`).join("")
    || `<li class="none">Nothing matches “${esc($("#cmdk-input").value)}”.</li>`;
  $("#cmdk-input").setAttribute("aria-activedescendant", CMDK_ITEMS.length ? "cmdk-" + CMDK_SEL : "");
  $$("#cmdk-list [data-i]").forEach(li => {
    li.onclick = () => runCmdk(+li.dataset.i);
    li.onmousemove = () => { if (CMDK_SEL !== +li.dataset.i) { CMDK_SEL = +li.dataset.i; renderCmdk(); } };
  });
  $(`#cmdk-${CMDK_SEL}`)?.scrollIntoView({ block: "nearest" });
}
function runCmdk(i) { const it = CMDK_ITEMS[i]; if (!it) return; $("#cmdk").close(); it.run(); }
function openCmdk() {
  if ($("#cmdk").open) return;
  $("#cmdk-input").value = ""; CMDK_SEL = 0; renderCmdk();
  $("#cmdk").showModal(); $("#cmdk-input").focus();
}
$("#open-cmdk").onclick = openCmdk;
$("#cmdk-input").addEventListener("input", () => { CMDK_SEL = 0; renderCmdk(); });
$("#cmdk-input").addEventListener("keydown", e => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    const n = CMDK_ITEMS.length; if (!n) return;
    CMDK_SEL = (CMDK_SEL + (e.key === "ArrowDown" ? 1 : -1) + n) % n; renderCmdk();
  } else if (e.key === "Enter") { e.preventDefault(); runCmdk(CMDK_SEL); }
});
$("#cmdk").addEventListener("click", e => { if (e.target === $("#cmdk")) $("#cmdk").close(); });  // click outside

function typing(e) { return e.target.closest("input, textarea, select, [contenteditable]"); }
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openCmdk(); return; }
  if (e.key === "/" && !typing(e) && !document.querySelector("dialog[open]")) { e.preventDefault(); openCmdk(); return; }
  if (PRESENT != null && !typing(e) && !document.querySelector("dialog[open]")) {
    if (["ArrowRight", "PageDown"].includes(e.key) || (e.key === " " && !e.target.closest("button"))) { e.preventDefault(); present(PRESENT + 1); }
    else if (["ArrowLeft", "PageUp"].includes(e.key)) { e.preventDefault(); present(PRESENT - 1); }
    else if (e.key === "Escape") endPresent();
  }
});

// --- presentation mode: a guided tour through the views that tell the story ---------------------
const TOUR = [
  { view: "overview", title: "What changed", text: "Where the product page ranks for each buyer question, before and after the team's edits." },
  { view: "web/compare", title: "Before and after", text: "Danfoss's page and our copy side by side. Drag the handle; both pages scroll together." },
  { view: "web/bm25", title: "Measured per question", text: "BM25 rank against the competitor pages: the whole page and its best passage, like AI search." },
  { view: "run/results", title: "The version AI cites most", text: "Every version is tested in a simulated answer engine. The most cited one wins, with a PDF report." },
  { view: "run/questions-detail", title: "Question by question", text: "Where each version wins or loses, with JEV's real answers one click away." },
  { view: "citations/history", title: "What Gemini really cites", text: "Gemini with Google Search, update by update: the real-world check on the simulation." },
  { view: "how/map", title: "How a page is written", text: "Each section answers one real search, using only evidence it can cite, and every sentence is checked." },
];
let PRESENT = null;
function present(i) {
  if (i < 0) i = 0;
  if (i >= TOUR.length) return endPresent();
  PRESENT = i;
  const s = TOUR[i];
  document.body.classList.add("presenting");
  if (!$("#chat").hidden) $("#chat-close").click();
  $("#present-bar").hidden = false;
  $("#present-count").textContent = `${i + 1} / ${TOUR.length}`;
  $("#present-title").textContent = s.title;
  $("#present-text").textContent = s.text;
  $("#present-prev").disabled = i === 0;
  $("#present-next").textContent = i === TOUR.length - 1 ? "Finish" : "Next";
  go(s.view);
}
function endPresent() {
  PRESENT = null;
  document.body.classList.remove("presenting");
  $("#present-bar").hidden = true;
}
$("#open-present").onclick = () => PRESENT == null ? present(0) : endPresent();
$("#present-next").onclick = () => present(PRESENT + 1);
$("#present-prev").onclick = () => present(PRESENT - 1);
$("#present-exit").onclick = endPresent;
