"use strict";
// Wayfinding: where you are, what to do here, and what comes next.
//  1. "You are here" bar above every view: breadcrumb, one line on what the view is for, and a
//     Next button to the logical next view.
//  2. Setup notices (no key, Ollama unreachable...) fold into one line instead of filling the page.
//  3. The rail is grouped (Results / Work / Evidence / Help).
//  4. "Path to AI citations": a progress ring with the five steps from setup to a cited page, ticked
//     from the app's own state. Each step opens the view where you do it.
//  5. A back-to-top button on long pages.
// Uses app.js globals ($, $$, esc, S, P, go, showTab, showSub, renderBanner, renderQuestions,
// renderResults, loadProduct, recall, store).

const VIEWS = {
  overview: { name: "Overview", what: "The story in numbers: how often AI search cites the new page compared with Danfoss's current one.", next: ["run/results", "See the full results"] },
  "run/product": { name: "Run › Product", what: "Pick the product and give Atlas at least two competitor pages to compete against.", next: ["run/questions", "Pick buyer questions"] },
  "run/questions": { name: "Run › Buyer questions", what: "Tick the questions buyers ask AI search. Every page version is tested on them.", next: ["run/run", "Set up the run"] },
  "run/run": { name: "Run › Run", what: "Choose the AIs and page styles, then press Run. You can keep working while it runs.", next: ["run/results", "Go to the results"] },
  "run/results": { name: "Run › Results", what: "The winning page version, its citation share, and the PDFs to download.", next: ["overview", "Show the overview"] },
  "run/questions-detail": { name: "Run › Per question", what: "Which version won each buyer question, and what the AI answered.", next: ["run/versions", "Compare versions"] },
  "run/versions": { name: "Run › Versions", what: "Every page version side by side, with its scores.", next: ["web/edit", "Improve the web page"] },
  "web/site": { name: "Web page › Site", what: "The live product page and our version of the site. Load the pages here first.", next: ["web/edit", "Edit a page"] },
  "web/edit": { name: "Web page › Edit", what: "Edit our version of a page. Facts must come from the wiki; new numbers are flagged.", next: ["web/compare", "Compare before and after"] },
  "web/compare": { name: "Web page › Before / after", what: "The current page and our version side by side. Drag the handle to compare.", next: ["web/competitors", "Check against competitors"] },
  "web/competitors": { name: "Web page › Competitors", what: "Where the page ranks for each question, which page beats it, and the words it lacks.", next: ["web/factcheck", "Fact-check the page"] },
  "web/factcheck": { name: "Web page › Fact check", what: "Every claim on the page checked against the wiki and its sources.", next: ["web/crawlers", "Crawler checks"] },
  "web/crawlers": { name: "Web page › Crawlers", what: "What Googlebot and AI crawlers can read on the page.", next: ["web/structured", "Structured data"] },
  "web/structured": { name: "Web page › Structured data", what: "The JSON-LD that tells search engines what the page is about.", next: ["web/bm25", "Search ranking per question"] },
  "web/bm25": { name: "Web page › BM25", what: "How the page ranks for each buyer question, as a search engine scores words.", next: ["citations/ask", "Check real Gemini answers"] },
  "catalog/models": { name: "Model by model › Models", what: "One page per product model, built only from the fact sheet. Pick a model.", next: ["catalog/page", "Open the model page"] },
  "catalog/page": { name: "Model by model › Model page", what: "Build the page for the chosen model and check it like the main page.", next: ["web/edit", "Improve the main page"] },
  "citations/ask": { name: "Citations › Ask Gemini", what: "Ask Gemini with Google Search the buyer questions and see who it really cites.", next: ["citations/history", "See the trend"] },
  "citations/history": { name: "Citations › Over time", what: "How often Gemini cites Danfoss, update by update, against the target.", next: ["citations/answers", "Read the answers"] },
  "citations/answers": { name: "Citations › Answers", what: "Gemini's answers and the sources it cited for each question.", next: ["citations/alerts", "Alerts"] },
  "citations/alerts": { name: "Citations › Alerts", what: "New AI models or Google ranking changes that may move the results.", next: ["run/run", "Run the test again"] },
  "wiki/edit": { name: "Wiki › Edit", what: "The facts every page may use. A save checks the wiki and rebuilds the pages.", next: ["wiki/log", "See the change log"] },
  "wiki/log": { name: "Wiki › Change log", what: "Every change to the wiki, with who made it and why.", next: ["wiki/sources", "Original documents"] },
  "wiki/sources": { name: "Wiki › Original documents", what: "The Danfoss documents the wiki cites, saved as text.", next: ["run/run", "Run with the new facts"] },
  "how/process": { name: "How it works › The process", what: "How the section writer builds a page, step by step.", next: ["how/queries", "Sub-queries"] },
  "how/queries": { name: "How it works › Sub-queries", what: "The searches each buyer question is split into.", next: ["how/evidence", "Evidence"] },
  "how/evidence": { name: "How it works › Evidence", what: "The passages each section found, and the sentences checked against them.", next: ["how/map", "Embedding map"] },
  "how/map": { name: "How it works › Embedding map", what: "Questions and passages placed by meaning: close points mean similar text.", next: ["overview", "Back to the overview"] },
};

// --- 1. "You are here" bar -----------------------------------------------------------------------
const where = document.createElement("div");
where.id = "where";
where.innerHTML = `<div class="where-text"><nav class="crumbs" aria-label="You are here"></nav><p class="where-what"></p></div>
  <button type="button" class="ghost where-next"><span></span><svg class="ic" viewBox="0 0 24 24"><path d="M5 12h14M13 6l6 6-6 6"/></svg></button>`;
$("main").prepend(where);

function viewKey() {
  const { tab, sub } = currentView();
  return sub ? `${tab}/${sub}` : tab;
}
function renderWhere() {
  const key = viewKey(), v = VIEWS[key] || VIEWS[key.split("/")[0]];
  if (!v) { where.hidden = true; return; }
  where.hidden = false;
  const parts = v.name.split(" › ");
  $(".crumbs", where).innerHTML = parts.map((p, i) => i < parts.length - 1
    ? `<a href="#${esc(key.split("/")[0])}">${esc(p)}</a><span aria-hidden="true">›</span>` : `<b aria-current="page">${esc(p)}</b>`).join("");
  $(".where-what", where).textContent = v.what;
  const btn = $(".where-next", where);
  btn.hidden = !v.next;
  if (v.next) { $("span", btn).textContent = "Next: " + v.next[1]; btn.onclick = () => go(v.next[0]); }
  if (P) markSeen(key);
}

// --- 2. setup notices fold into one line ----------------------------------------------------------
let setupOpen = false;
function foldBanner() {
  const b = $("#banner");
  const old = $(":scope > details.setup", b);
  const fresh = $$(":scope > section.card:not(.alert-card)", b);
  if (old && !fresh.length) { old.open = setupOpen; return; }  // nothing new: just open or close it
  old?.remove();
  const setup = fresh;
  if (!setup.length) return;
  const d = document.createElement("details");
  d.className = "setup";
  d.open = setupOpen;
  d.innerHTML = `<summary><span class="setup-dot" aria-hidden="true"></span>
    <b>${setup.length} thing${setup.length === 1 ? "" : "s"} to set up before you can run</b>
    <span class="setup-list">${setup.map(s => esc(($("h2", s) || $("b", s))?.textContent || "")).join(" · ")}</span></summary>`;
  setup.forEach(s => d.append(s));
  d.ontoggle = () => { setupOpen = d.open; };
  b.prepend(d);
}
const _renderBanner = renderBanner;
renderBanner = function () { _renderBanner.apply(this, arguments); foldBanner(); renderJourney(); };

// --- 3. rail groups -------------------------------------------------------------------------------
for (const [tab, label] of [["overview", "Results"], ["run", "Work"], ["citations", "Evidence"], ["how", "Help"]]) {
  const btn = $(`.rail [data-tab="${tab}"]`);
  if (!btn) continue;
  const l = document.createElement("span");
  l.className = "rail-label"; l.setAttribute("role", "presentation"); l.textContent = label;
  btn.before(l);
}

// --- 4. path to AI citations -----------------------------------------------------------------------
function seenKey() { return "seen." + (P?.product?.slug || ""); }
function markSeen(key) {
  const run = P?.runs?.find(r => !r.unfinished)?.run;
  if (run && (key === "overview" || key === "run/results")) {
    if (recall(seenKey()) !== run) { store(seenKey(), run); renderJourney(); }
  }
}
function aiReady() {
  if (!S) return false;
  const used = [...new Set([$("#s-writer").value, $("#s-judge").value])].filter(id => S.providers[id]);
  return used.length > 0 && used.every(id => {
    const p = S.providers[id];
    if (p.type === "ollama") return p.reachable && (!p.installed || p.installed.includes($(id === $("#s-writer").value ? "#s-writer-model" : "#s-judge-model").value));
    return !p.key_env || p.has_key;
  });
}
function steps() {
  const runs = (P?.runs || []).filter(r => !r.unfinished);
  const running = S?.job?.status === "running" && S.job.slug === P?.product?.slug;
  return [
    { label: "Connect an AI", hint: "Ollama or a Gemini key", done: aiReady(),
      act: () => {
        if (!$("#banner details.setup")) return $("#open-settings").click();
        setupOpen = true; foldBanner(); go("run/product");
      } },
    { label: "Add competitor pages", hint: `${P?.pages?.competitors || 0} of 2 saved`, done: (P?.pages?.competitors || 0) >= 2,
      act: () => { go("run/product"); const c = $("#cmp"); if (c) { c.open = true; setTimeout(() => c.scrollIntoView({ block: "start", behavior: "smooth" }), 60); } } },
    { label: "Pick buyer questions", hint: `${(P?.questions || []).filter(q => q.enabled).length} ticked`, done: (P?.questions || []).some(q => q.enabled),
      act: () => go("run/questions") },
    { label: "Run the citation test", hint: running ? "running now…" : runs.length ? `${runs.length} run${runs.length === 1 ? "" : "s"} done` : "writes and tests the pages", done: runs.length > 0, busy: running,
      act: () => go("run/run") },
    { label: "Read what wins", hint: "the overview and the report", done: runs.length > 0 && recall(seenKey()) === runs[0].run,
      act: () => go("overview") },
  ];
}
const journey = document.createElement("div");
journey.className = "journey";
journey.innerHTML = `<div class="j-head">
    <svg class="j-ring" viewBox="0 0 44 44" aria-hidden="true"><circle class="j-track" cx="22" cy="22" r="18"/><circle class="j-fill" cx="22" cy="22" r="18" pathLength="100"/></svg>
    <div><b>Path to AI citations</b><span class="j-count"></span></div>
  </div>
  <ol class="j-steps"></ol>
  <button type="button" class="primary j-next"></button>`;
$(".rail").append(journey);

function renderJourney() {
  if (!P) return;
  const st = steps(), done = st.filter(s => s.done).length;
  const now = st.findIndex(s => !s.done);
  journey.classList.toggle("complete", now < 0);
  $(".j-fill", journey).style.strokeDasharray = `${(100 * done) / st.length} 100`;
  $(".j-count", journey).textContent = now < 0 ? "All done: the page is ready to publish" : `${done} of ${st.length} done`;
  $(".j-steps", journey).innerHTML = st.map((s, i) => `<li class="${s.done ? "done" : i === now ? "now" : "todo"}${s.busy ? " busy" : ""}">
      <button type="button" data-step="${i}"><i aria-hidden="true"></i><span><b>${esc(s.label)}</b><small>${esc(s.hint)}</small></span></button></li>`).join("");
  $$(".j-steps [data-step]", journey).forEach(b => b.onclick = () => st[+b.dataset.step].act());
  const next = $(".j-next", journey);
  next.textContent = now < 0 ? "Open the overview" : `Next: ${st[now].label}`;
  next.onclick = () => (now < 0 ? go("overview") : st[now].act());
}

// keep both in step with the app: wrap the functions that change view or state
const _showTab = showTab, _showSub = showSub;
showTab = function () { const r = _showTab.apply(this, arguments); renderWhere(); return r; };
showSub = function () { const r = _showSub.apply(this, arguments); renderWhere(); return r; };
for (const name of ["renderQuestions", "renderResults", "loadProduct", "renderJob"]) {
  const f = window[name];
  if (typeof f !== "function") continue;
  window[name] = function () {
    const r = f.apply(this, arguments);
    if (r && typeof r.then === "function") return r.then(v => { renderJourney(); renderWhere(); return v; });
    renderJourney(); return r;
  };
}

// --- 5. back to top --------------------------------------------------------------------------------
const topBtn = document.createElement("button");
topBtn.type = "button"; topBtn.className = "to-top"; topBtn.setAttribute("aria-label", "Back to the top");
topBtn.innerHTML = `<svg class="ic" viewBox="0 0 24 24"><path d="M12 19V5M6 11l6-6 6 6"/></svg>`;
topBtn.onclick = () => window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
document.body.append(topBtn);
let ticking = false;
addEventListener("scroll", () => {
  if (ticking) return; ticking = true;
  requestAnimationFrame(() => { topBtn.classList.toggle("show", scrollY > 700); ticking = false; });
}, { passive: true });

// first paint: the state may already be loaded
if (S) foldBanner();
renderWhere();
renderJourney();
