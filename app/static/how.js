"use strict";
// Loaded after app.js (shares its globals: $, $$, esc, api, safe, toast, S, P, CIT, HOW, gather).

const SVGNS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs = {}, parent) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
}
function tipBox(host) {
  let t = $(".viz-tip", host);
  if (!t) { t = document.createElement("div"); t.className = "viz-tip"; t.hidden = true; host.appendChild(t); }
  return t;
}
function showTip(host, html, x, y) {
  const t = tipBox(host); t.innerHTML = html; t.hidden = false;
  const w = host.clientWidth, tw = t.offsetWidth;
  t.style.left = Math.max(4, Math.min(w - tw - 4, x + 12)) + "px";
  t.style.top = Math.max(4, y - t.offsetHeight - 10) + "px";
}
function hideTip(host) { const t = $(".viz-tip", host); if (t) t.hidden = true; }

// --- Citations: how the citation rate changes over time ----------------------------------------
function renderCitChart() {
  const host = $("#cit-chart");
  const tg = CIT.targets || {};
  const gem = (CIT.history.runs || []).slice().reverse().map(r => ({ date: r.date, v: 100 * r.danfoss_answers / Math.max(1, r.prompts),
    tip: `${r.danfoss_answers} of ${r.prompts} answers cite Danfoss · cited first ${r.danfoss_first ?? 0}× · share ${pct(r.danfoss_share)}` }));
  const lab = (CIT.lab || []).map(r => ({ date: r.date, v: r.cited_pct,
    tip: `best version “${r.style}”: cited in ${r.cited_pct}% · share ${r.share_pct}%${r.first_count != null ? ` · first ${r.first_count}×` : ""}` }));
  const last = CIT.history.runs?.[0]?.targets;
  $("#cit-targets").innerHTML = tg.cited_pct == null ? "" : `<div class="target-line">Targets (same as the Run tab): Danfoss cited in at least <b>${tg.cited_pct}%</b> of the answers and cited first in at least <b>${tg.first_count}</b>.
    ${last ? `Last update with Gemini: ${last.cited_pct}% ${last.cited_ok ? '<span class="ok">✔ met</span>' : '<span class="miss">✘ missed</span>'} · first ${last.first_count}× ${last.first_ok ? '<span class="ok">✔ met</span>' : '<span class="miss">✘ missed</span>'}` : ""}</div>`;
  host.innerHTML = "";
  if (!gem.length && !lab.length) {
    host.innerHTML = `<p class="hint">The chart appears after the first update or the first run of the Run tab.</p>`; return;
  }
  const series = [
    { key: "gem", name: "Gemini with Google Search (real answers)", cls: "s1", pts: gem },
    { key: "lab", name: "Lab test, best version (Run tab)", cls: "s2", pts: lab },
  ].filter(s => s.pts.length);
  const W = 680, H = 240, m = { l: 44, r: 150, t: 14, b: 30 };
  const time = d => Date.parse(d.replace(" ", "T")) || 0;
  const all = series.flatMap(s => s.pts);
  let t0 = Math.min(...all.map(p => time(p.date))), t1 = Math.max(...all.map(p => time(p.date)));
  if (t0 === t1) { t0 -= 864e5; t1 += 864e5; }
  const x = d => m.l + (time(d) - t0) / (t1 - t0) * (W - m.l - m.r);
  const y = v => m.t + (1 - v / 100) * (H - m.t - m.b);
  host.insertAdjacentHTML("beforeend", `<div class="legend">${series.map(s => `<span><i class="sw ${s.cls}"></i>${esc(s.name)}</span>`).join("")}
    ${tg.cited_pct != null ? `<span><i class="sw goal"></i>Goal</span>` : ""}</div>`);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "viz", role: "img",
    "aria-label": "Share of answers that cite Danfoss over time" }, host);
  for (const v of [0, 25, 50, 75, 100]) {
    svgEl("line", { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), class: "grid" }, svg);
    svgEl("text", { x: m.l - 8, y: y(v) + 4, class: "axis", "text-anchor": "end" }, svg).textContent = v + "%";
  }
  // one date label per day, under that day's first point (never outside the plot)
  const firstOfDay = {};
  all.slice().sort((a, b) => time(a.date) - time(b.date)).forEach(p => { firstOfDay[p.date.slice(0, 10)] ??= p.date; });
  const days = Object.keys(firstOfDay), step = Math.ceil(days.length / 5);
  days.forEach((d, i) => { if (i % step === 0) svgEl("text", { x: x(firstOfDay[d]), y: H - 8, class: "axis", "text-anchor": "middle" }, svg).textContent = d.slice(5); });
  // labels on the right edge: series values and the goal, pushed apart so they never overlap
  const labels = [];
  for (const s of series) {
    const pts = s.pts.slice().sort((a, b) => time(a.date) - time(b.date));
    if (pts.length > 1) svgEl("polyline", { points: pts.map(p => `${x(p.date)},${y(p.v)}`).join(" "), class: `line ${s.cls}` }, svg);
    pts.forEach(p => svgEl("circle", { cx: x(p.date), cy: y(p.v), r: 4.5, class: `dot ${s.cls}` }, svg));
    const lp = pts[pts.length - 1];
    labels.push({ y: y(lp.v), text: `${s.key === "gem" ? "Gemini" : "Lab"} ${Math.round(lp.v)}%`, cls: "lbl" });
  }
  if (tg.cited_pct != null) {
    svgEl("line", { x1: m.l, x2: W - m.r, y1: y(tg.cited_pct), y2: y(tg.cited_pct), class: "goal" }, svg);
    labels.push({ y: y(tg.cited_pct), text: `goal ${tg.cited_pct}%`, cls: "axis" });
  }
  labels.sort((a, b) => a.y - b.y);
  labels.forEach((l, i) => { if (i && l.y - labels[i - 1].y < 14) l.y = labels[i - 1].y + 14; });
  labels.forEach(l => { svgEl("text", { x: W - m.r + 8, y: l.y + 4, class: l.cls }, svg).textContent = l.text; });
  // hover: crosshair on the nearest update, a tooltip with every series at that moment
  const cross = svgEl("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
  const hit = svgEl("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", ev => {
    const r = svg.getBoundingClientRect(), px = (ev.clientX - r.left) * W / r.width;
    let best = null;
    for (const s of series) for (const p of s.pts) {
      const d = Math.abs(x(p.date) - px);
      if (!best || d < best.d) best = { d, p };
    }
    if (!best) return;
    const at = best.p.date;
    cross.setAttribute("x1", x(at)); cross.setAttribute("x2", x(at)); cross.setAttribute("visibility", "visible");
    const rows = series.map(s => [s, s.pts.find(p => p.date === at)]).filter(([, p]) => p);
    showTip(host, `<b>${esc(at)}</b>` + rows.map(([s, p]) => `<div><i class="sw ${s.cls}"></i>${esc(p.tip)}</div>`).join(""),
      x(at) * r.width / W, ev.clientY - host.getBoundingClientRect().top);
  });
  hit.addEventListener("pointerleave", () => { cross.setAttribute("visibility", "hidden"); hideTip(host); });
  if (lab.length) host.insertAdjacentHTML("beforeend", `<details><summary class="hint">Lab test runs as a table</summary><div class="tablewrap"><table class="data"><thead><tr><th>Run</th><th>Best version</th><th>Cited</th><th>Share</th><th>Cited first</th><th>Targets</th></tr></thead><tbody>${
    CIT.lab.slice().reverse().map(r => `<tr><td>${esc(r.date)}</td><td>${esc(r.style)}</td><td>${r.cited_pct}%</td><td>${r.share_pct}%</td><td>${r.first_count ?? "–"}</td><td>${r.met == null ? "–" : r.met ? "✔ met" : "✘ missed"}</td></tr>`).join("")}</tbody></table></div></details>`);
}

// --- Citations: wiki suggestions from the explanation ------------------------------------------
function citSuggKey() {
  return { slug: P.product.slug, run: $("#cit-run").value, i: CITROW, ours: $("#cit-ours").value };
}
function renderCitSugg(d) {
  const box = $("#cit-sugg");
  if (!d) { box.innerHTML = ""; return; }
  const list = items => items.length ? `<ul>${items.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "";
  const open = d.suggestions.filter(x => !x.decision).length;
  box.innerHTML = `<div class="sugg-box"><h3>Wiki suggestions from this answer</h3>
    <p>${esc(d.diagnosis)}</p><p class="hint">By ${esc(d.analyst)}. Nothing changes in the wiki until you accept; you can edit the text first. Accepted changes are noted in wiki/log.md.</p>
    ${d.suggestions.map(suggCard).join("")}
    ${d.missing_facts.length ? `<div class="sugg"><b>Missing facts</b> <span class="hint">(a person must find a Danfoss source)</span>${list(d.missing_facts)}</div>` : ""}
    <p class="hint">${open ? `${open} of ${d.suggestions.length} still to decide.` : "All decided. The next run writes from the updated wiki."}</p></div>`;
  bindSuggCards(box, (id, decision, text) => api("/api/citations/suggestion", { ...citSuggKey(), id, decision, text }),
    nd => renderCitSugg(nd));
}
function loadCitSugg() {
  if (CITROW == null) return;
  safe(async () => {
    const d = await api("/api/citations/suggestions?" + new URLSearchParams(citSuggKey()));
    renderCitSugg(d);
    if (d) $("#cit-sugg-row").classList.remove("hidden");
  });
}
$("#cit-suggest").onclick = () => {
  if (CITROW == null) return;
  const s = gather(), btn = $("#cit-suggest"); btn.disabled = true;
  const st = $("#cit-suggest-status"), old = st.textContent;
  st.textContent = `Asking ${S.providers[s.judge]?.label || s.judge} (${s.judge_model}) for wiki changes… a local model can take a few minutes.`;
  safe(async () => {
    try { renderCitSugg(await api("/api/citations/suggest", { ...citSuggKey(), provider: s.judge, model: s.judge_model })); }
    finally { btn.disabled = false; st.textContent = old; }
  });
};

// --- How it works ---------------------------------------------------------------------------------
let HOWSEC = 0;
async function loadHow(run = "") {
  HOW = await api("/api/process?" + new URLSearchParams({ slug: P.product.slug, run }));
  $("#how-run").innerHTML = HOW.runs.map(r => `<option ${r === HOW.run ? "selected" : ""}>${esc(r)}</option>`).join("");
  const has = !!HOW.process;
  $("#how-run").closest("label").classList.toggle("hidden", !HOW.runs.length);
  $("#how-body").classList.toggle("hidden", !has);
  $("#how-empty").innerHTML = has ? "" : `No run with the section writer yet for this product. In the Run tab, tick <b>“Section by section, verified citations”</b> and start a run.`;
  if (!has) return;
  HOWSEC = 0;
  renderHow();
  $("#how-map").innerHTML = ""; $("#how-map-status").textContent = HOW.has_map ? "" : "Needs the embedding model on the Ollama server; the first time takes about a minute.";
  if (HOW.has_map) drawMap();
}
$("#how-run").onchange = () => safe(() => loadHow($("#how-run").value));

function badge(v) {
  return { supported: `<span class="good">✔ supported</span>`, partly: `<span class="warntxt">~ partly</span>`,
    unsupported: `<span class="badtxt">✘ unsupported</span>`, "not checked": `<span class="hint">not checked</span>` }[v] || esc(v);
}
function renderHow() {
  const pr = HOW.process, m = pr.metrics;
  const kept = pr.subqueries.filter(q => q.kept).length, nosrc = pr.missing.length;
  const sents = pr.sections.reduce((a, s) => a + s.checks.length, 0) + pr.intro.checks.length;
  const steps = [
    ["Sub-queries", `${pr.subqueries.length}`, `${pr.subqueries.filter(q => q.origin === "Gemini search").length} from Gemini, ${pr.subqueries.filter(q => q.origin === "buyer question").length} buyer questions, ${pr.subqueries.filter(q => q.origin === "AI fan-out").length} fan-out`],
    ["Evidence units", `${pr.units}`, "wiki facts [w] and original passages [r]"],
    ["Search", "BM25 + embeddings", esc(pr.embeddings)],
    ["Rerank", "top 5", esc(pr.reranker)],
    ["Sections written", `${kept}`, `${nosrc} skipped: no evidence (missing facts)`],
    ["Sentences checked", `${sents}`, `${m.rewritten_sections} section(s) rewritten, ${m.removed} sentence(s) removed`],
    ["Page", `${m.sections} sections`, `citation precision ${m.citation_precision == null ? "–" : pct(m.citation_precision)}`],
  ];
  $("#how-flow").innerHTML = steps.map(([t, v, d], i) => `${i ? '<span class="arrow" aria-hidden="true">→</span>' : ""}<div class="step-box"><div class="hint tiny">${esc(t)}</div><b>${v}</b><div class="tiny">${d}</div></div>`).join("");
  const tile = (label, v, note) => `<div class="tile"><div class="hint tiny">${label}</div><div class="big">${v}</div><div class="tiny hint">${note}</div></div>`;
  $("#how-metrics").innerHTML = `<div class="tiles">
    ${tile("Citation precision", m.citation_precision == null ? "–" : pct(m.citation_precision), "cited sentences their evidence supports")}
    ${tile("Citation coverage", m.citation_coverage == null ? "–" : pct(m.citation_coverage), "sentences with an [id]")}
    ${tile("Removed", m.removed, "unsupported after one rewrite")}</div>`;
  $("#how-queries").innerHTML = `<div class="tablewrap"><table class="data"><thead><tr><th>Search</th><th>From</th><th>Section?</th></tr></thead><tbody>` +
    pr.subqueries.map(q => `<tr><td>${esc(q.query)}</td><td>${esc(q.origin)}</td><td>${q.kept ? `<span class="good">✔ written</span>` : `<span class="hint">${esc(q.why || "not used")}</span>`}</td></tr>`).join("") + "</tbody></table></div>";
  const secs = [...pr.sections.map((s, i) => ({ label: `S${i + 1}. ${s.query}${s.empty ? " (left out: nothing supported)" : ""}`, s })), { label: "Intro (title and summary)", s: { ...pr.intro, candidates: [], evidence: [] } }];
  $("#how-sec").innerHTML = secs.map((x, i) => `<option value="${i}" ${i === HOWSEC ? "selected" : ""}>${esc(x.label)}</option>`).join("");
  $("#how-sec").onchange = () => { HOWSEC = +$("#how-sec").value; renderHow(); };
  const s = secs[HOWSEC].s;
  $("#how-cands").innerHTML = s.candidates.length ? `<div class="tablewrap"><table class="data"><thead><tr><th></th><th>Passage</th><th title="exact words">BM25</th><th title="meaning">Embeddings</th><th title="fused rank">RRF</th><th title="0-3, how well it answers">Reranker</th></tr></thead><tbody>` +
    s.candidates.map(c => `<tr class="${c.chosen ? "chosen" : ""}"><td>${c.chosen ? "✔" : ""}</td><td><b>[${esc(c.id)}]</b> <span class="tiny hint">${esc(c.source)}</span><div class="tiny">${esc(c.text)}</div></td>
      <td>#${c.bm25_rank}</td><td>${c.dense_rank ? "#" + c.dense_rank : "–"}</td><td>#${c.rrf_rank}</td><td>${c.grade ?? "–"}</td></tr>`).join("") + "</tbody></table></div>"
    : `<p class="hint">The intro uses the passages that best match the product name.</p>`;
  const dropped = new Set(s.dropped || []);
  $("#how-checks").innerHTML = (s.rewritten ? `<p class="hint">Some sentences failed the check, so the section was rewritten once with that feedback.</p>` : "") +
    `<ul class="claims">${s.checks.map(c => `<li>${dropped.has(c.sentence) ? `<s>${esc(c.claim)}</s> <span class="badtxt">removed</span>` : esc(c.claim)}
      <div class="tiny">${badge(c.verdict)} · cites ${c.cites.length ? c.cites.map(i => `<abbr title="${esc(pr.unit_text[i]?.text || "")}">[${esc(i)}]</abbr>`).join(" ") : "nothing"} · ${esc(c.method)}${c.note ? " · " + esc(c.note) : ""}</div></li>`).join("")}</ul>
    <details><summary>Final text of this section</summary><pre class="md">${esc(s.final)}</pre></details>`;
}

$("#how-map-btn").onclick = () => {
  const btn = $("#how-map-btn"); btn.disabled = true;
  $("#how-map-status").textContent = "Embedding the passages and projecting them… (cached afterwards)";
  safe(async () => {
    try { HOW.map = await api("/api/process/map", { slug: P.product.slug, run: HOW.run }); drawMap(); $("#how-map-status").textContent = ""; }
    catch (e) { $("#how-map-status").textContent = ""; throw e; }
    finally { btn.disabled = false; }
  });
};
async function drawMap() {
  if (!HOW.map) HOW.map = await api("/api/process/map", { slug: P.product.slug, run: HOW.run });
  const host = $("#how-map"), pts = HOW.map.points;
  host.innerHTML = "";
  const kinds = [
    { k: "wiki", name: "Wiki facts", cls: "s1", shape: "circle" },
    { k: "raw", name: "Original documents (raw/)", cls: "s1 hollow", shape: "circle" },
    { k: "competitor", name: "Competitor passages", cls: "s2", shape: "square" },
    { k: "ours", name: "Our sections", cls: "s3", shape: "diamond" },
    { k: "query", name: "Sub-queries", cls: "q", shape: "star" },
  ].filter(k => pts.some(p => p.kind === k.k));
  host.insertAdjacentHTML("beforeend", `<div class="legend">${kinds.map(k => `<span><svg width="14" height="14" aria-hidden="true">${shapePath(k.shape, 7, 7, 5, k.cls)}</svg>${esc(k.name)}</span>`).join("")}</div>`);
  const W = 680, H = 440, pad = 24;
  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const X = v => pad + (v - x0) / ((x1 - x0) || 1) * (W - 2 * pad), Y = v => pad + (v - y0) / ((y1 - y0) || 1) * (H - 2 * pad);
  const svg = svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "viz map", role: "img", "aria-label": "Embedding map of evidence, competitor passages, our sections and sub-queries" }, host);
  const byId = Object.fromEntries(pts.map(p => [p.id, p]));
  for (const [q, ids] of Object.entries(HOW.map.chosen || {})) {
    const qp = byId[q];
    if (qp) ids.forEach(id => byId[id] && svgEl("line", { x1: X(qp.x), y1: Y(qp.y), x2: X(byId[id].x), y2: Y(byId[id].y), class: "link" }, svg));
  }
  const order = ["raw", "wiki", "competitor", "ours", "query"];
  const g = svgEl("g", {}, svg);
  pts.slice().sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind)).forEach(p => {
    const k = kinds.find(k => k.k === p.kind);
    g.insertAdjacentHTML("beforeend", shapePath(k.shape, X(p.x), Y(p.y), p.kind === "query" ? 9 : 5, k.cls, p.id));
    if (p.kind === "query") svgEl("text", { x: X(p.x) + 11, y: Y(p.y) + 4, class: "lbl" }, svg).textContent = p.id.toUpperCase();
  });
  svg.addEventListener("pointermove", ev => {
    const id = ev.target.dataset?.id; if (!id) return hideTip(host);
    const p = byId[id], k = kinds.find(k => k.k === p.kind), r = host.getBoundingClientRect();
    showTip(host, `<b>${esc(k.name)} · ${esc(p.id)}</b><div>${esc(p.text)}</div>`, ev.clientX - r.left, ev.clientY - r.top);
  });
  svg.addEventListener("pointerleave", () => hideTip(host));
  host.insertAdjacentHTML("beforeend", `<ol class="tiny hint qlist">${HOW.map.queries.map(q => `<li>${esc(q)}</li>`).join("")}</ol>`);
}
function shapePath(shape, x, y, r, cls, id = "") {
  const a = `class="pt ${cls}" ${id ? `data-id="${esc(id)}"` : ""}`;
  if (shape === "square") return `<rect x="${x - r * .85}" y="${y - r * .85}" width="${r * 1.7}" height="${r * 1.7}" rx="1" ${a}/>`;
  if (shape === "diamond") return `<path d="M${x} ${y - r * 1.2}L${x + r * 1.2} ${y}L${x} ${y + r * 1.2}L${x - r * 1.2} ${y}Z" ${a}/>`;
  if (shape === "star") {
    const p = [];
    for (let i = 0; i < 10; i++) { const rr = i % 2 ? r * .45 : r, t = Math.PI / 5 * i - Math.PI / 2; p.push(`${(x + rr * Math.cos(t)).toFixed(1)},${(y + rr * Math.sin(t)).toFixed(1)}`); }
    return `<polygon points="${p.join(" ")}" ${a}/>`;
  }
  return `<circle cx="${x}" cy="${y}" r="${r}" ${a}/>`;
}

// --- the assistant panel (Ollama on the team server) ------------------------------------------------
let CHAT = { msgs: [], id: null, timer: null, ready: false };
try { CHAT.msgs = JSON.parse(localStorage.getItem("atlas.chat") || "[]"); } catch (e) { CHAT.msgs = []; }
function chatSave() { try { localStorage.setItem("atlas.chat", JSON.stringify(CHAT.msgs.slice(-30))); } catch (e) {} }
function currentTab() { return $(".tabs [aria-selected=true]")?.textContent.trim() || "Run"; }
function chatContext() {
  $("#chat-where").textContent = `Knows the app, the “${currentTab()}” tab` + (P ? ` and the facts of ${P.product.name}.` : ".");
}
function mdLite(s) {
  let h = esc(s);
  h = h.replace(/```([\s\S]*?)```/g, (_, c) => `<pre>${c.trim()}</pre>`);
  h = h.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  h = h.replace(/^\s*[-*] (.+)$/gm, "<li>$1</li>").replace(/(<li>.*<\/li>\n?)+/g, m => `<ul>${m}</ul>`);
  return h.replace(/\n/g, "<br>").replace(/<\/li><br>/g, "</li>").replace(/<ul><br>/g, "<ul>");
}
function renderChat() {
  const log = $("#chat-log");
  log.innerHTML = CHAT.msgs.length ? CHAT.msgs.map(m => `<div class="msg ${m.role}">${m.role === "assistant" ? mdLite(m.content || "…") : esc(m.content)}${m.error ? `<div class="error">${esc(m.error)}</div>` : ""}</div>`).join("")
    : `<p class="hint">Ask in any language, for example: “Why did the fact-dense version win?”, “What pressure does Micro Plate handle?”, “What does RRF mean?”</p>`;
  log.scrollTop = log.scrollHeight;
  $("#chat-send").textContent = CHAT.id ? "Stop" : "Send";
}
async function chatOpen(open) {
  const panel = $("#chat");
  panel.hidden = !open; document.body.classList.toggle("chat-open", open);
  $("#open-chat").setAttribute("aria-expanded", String(open));
  try { localStorage.setItem("atlas.chatOpen", open ? "1" : "0"); } catch (e) {}
  if (!open) return;
  chatContext(); renderChat(); $("#chat-input").focus();
  try {
    const st = await api("/api/chat/status");
    const sel = $("#chat-model"), keep = sel.value || (() => { try { return localStorage.getItem("atlas.chatModel"); } catch (e) { return null; } })();
    sel.innerHTML = st.models.map(m => `<option ${m === (keep && st.models.includes(keep) ? keep : st.default) ? "selected" : ""}>${esc(m)}</option>`).join("");
    CHAT.ready = st.reachable && st.models.length > 0;
    if (!st.reachable) $("#chat-where").textContent = `Cannot reach Ollama at ${st.base_url}. Set its address in Settings (the team server's IP) and check you are on the same network.`;
    else if (!st.models.length) $("#chat-where").textContent = `No chat model on ${st.base_url}. On that computer run: ollama pull qwen3:8b`;
  } catch (e) { $("#chat-where").textContent = e.message; }
}
$("#open-chat").onclick = () => chatOpen($("#chat").hidden);
$("#chat-close").onclick = () => chatOpen(false);
$("#chat-clear").onclick = () => { if (CHAT.id) return; CHAT.msgs = []; chatSave(); renderChat(); };
$("#chat-model").onchange = () => { try { localStorage.setItem("atlas.chatModel", $("#chat-model").value); } catch (e) {} };
$("#chat-input").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chat-form").requestSubmit(); } });
$("#chat-form").onsubmit = e => {
  e.preventDefault();
  if (CHAT.id) { api("/api/chat/stop", { id: CHAT.id }).catch(() => {}); return; }
  const text = $("#chat-input").value.trim();
  if (!text) return;
  $("#chat-input").value = "";
  CHAT.msgs.push({ role: "user", content: text });
  const reply = { role: "assistant", content: "" };
  CHAT.msgs.push(reply); renderChat();
  safe(async () => {
    try {
      const r = await api("/api/chat", { messages: CHAT.msgs.slice(0, -1).map(m => ({ role: m.role, content: m.content })),
        slug: P?.product.slug || "", tab: currentTab(), model: $("#chat-model").value });
      CHAT.id = r.id; renderChat();
      await new Promise(done => {
        CHAT.timer = setInterval(async () => {
          try {
            const p = await api("/api/chat/poll?id=" + CHAT.id);
            reply.content = p.text; if (p.error) reply.error = p.error;
            renderChat();
            if (p.done) { clearInterval(CHAT.timer); done(); }
          } catch (err) { reply.error = err.message; clearInterval(CHAT.timer); done(); }
        }, 400);
      });
    } catch (err) { reply.error = err.message; }
    finally { CHAT.id = null; if (!reply.content && !reply.error) reply.content = "(stopped)"; chatSave(); renderChat(); }
  });
};
try { if (localStorage.getItem("atlas.chatOpen") === "1") chatOpen(true); } catch (e) {}
