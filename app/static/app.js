const $ = (id) => document.getElementById(id);
const state = {view: "paper", mode: "live", q: "", page: 1, total: 0, busy: false, request: 0, modeRequest: 0, records: []};
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const url = (value) => {try {const u = new URL(value); return ["http:", "https:"].includes(u.protocol) ? u.href : "";} catch {return "";}};
const names = {crossref: "CROSSREF", arxiv: "ARXIV", mldeadlines: "ML DEADLINES", demo: "SYNTHETIC DEMO"};
const labels = {paper: "Discover papers", conference: "Conferences", saved: "Saved collection", dashboard: "Overview"};
const dateText = (v) => v ? new Date(v).toLocaleString(undefined, {dateStyle:"medium", timeStyle:"short"}) : "Not fetched yet";

async function api(path, options = {}) {
  const response = await fetch("/api/v1" + path, {...options, headers: {"Content-Type":"application/json", ...options.headers}});
  if (!response.ok) {
    let error; try {error = await response.json();} catch {error = {};}
    const detail = error.detail;
    throw new Error(typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(x => x.msg).join("; ") : "Request failed. Please try again.");
  }
  return response.status === 204 ? null : response.json();
}

function feedback(message, type = "") {
  $("feedback").textContent = message;
  $("feedback").className = type;
  $("feedback").hidden = !message;
}
let toastTimer;
function toast(message) {$("toast").textContent = message; $("toast").hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $("toast").hidden = true, 3200);}

function params() {
  const result = new URLSearchParams({kind: state.view === "saved" ? "all" : state.view === "conference" ? "conference" : "paper", mode:state.mode, q:state.q, page:state.page, page_size:12, sort:$("sort").value});
  if (state.view === "saved") result.set("saved", "true");
  if (state.mode === "live" && state.view === "paper" && $("source").value) result.set("source", $("source").value);
  if (state.view === "paper" && $("year").value) result.set("year_from", $("year").value);
  if (state.view === "conference") {result.set("location", $("location").value); result.set("deadline", $("deadline").value);}
  return result;
}

function deadlineLabel(r) {
  if (r.status === "unknown") return "Deadline to be announced · verify with source";
  if (r.status === "expired") return "Submission deadline passed";
  if (r.status === "due_today") return "Due today · time / timezone unspecified";
  if (r.status === "date_only") return `${r.days_left} calendar days · time / timezone unverified`;
  return r.days_left === 0 ? "Due in less than 24 hours · check prerequisites" : `${r.days_left} days until submission deadline`;
}

function card(r) {
  const sources = [...new Set(r.sources.map(s => s.source))];
  const stale = !r.demo && Date.now() - new Date(r.retrieved_at).getTime() > 86400000;
  const description = r.kind === "paper" ? r.abstract || "No abstract supplied by this source. Open the original record for more information." : r.note || "See the official conference site for tracks, eligibility, and submission instructions.";
  return `<article class="card"><div class="card-head">${sources.map(s => `<span class="badge ${esc(s)}">${esc(names[s] || s)}</span>`).join("")}${stale ? '<span class="badge demo" title="Retrieved more than 24 hours ago">STALE</span>' : ""}<span class="card-year">${esc(r.year || "Year unknown")}</span><button class="save-btn ${r.saved ? "saved" : ""}" data-save="${esc(r.id)}" aria-label="${r.saved ? "Remove bookmark" : "Save record"}" aria-pressed="${r.saved}">${r.saved ? "▣" : "▢"}</button></div>
    <h3 class="card-title"><button data-detail="${esc(r.id)}">${esc(r.title)}</button></h3>
    <p class="authors">${esc(r.kind === "paper" ? (r.authors.slice(0,3).join(" · ") || "Authors not supplied") + (r.authors.length > 3 ? " et al." : "") : r.location || "Location to be announced")}</p>
    ${r.kind === "conference" ? `<p class="deadline ${esc(r.status)}">◷ &nbsp;${esc(deadlineLabel(r))}</p>` : ""}
    <p class="abstract">${esc(description)}</p><div class="tags">${r.topics.slice(0,3).map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
    <div class="card-bottom"><span title="${esc(r.matched_terms.join(", "))}" class="match">${r.score > 0 ? Math.round(r.score*100) + "% text match" : r.kind === "conference" ? "Check official CFP" : esc(r.venue || "Research metadata")}</span><button data-detail="${esc(r.id)}">View details ↗</button></div></article>`;
}

function emptyState() {
  const saved = state.view === "saved";
  const title = saved ? "A place for your next big idea." : state.q ? "No matching records yet." : "Follow your curiosity.";
  const message = saved ? "Save a paper or conference using the square bookmark button. Your collection is kept across restarts." : state.q ? "Try a broader topic, reset your filters, or check source status. Conference coverage is limited to the collected index." : "Search a topic to collect live research, or explore a small set of clearly labeled examples.";
  return `<div class="empty"><div class="empty-icon">✳</div><h3>${title}</h3><p>${message}</p>${saved ? '<button class="primary" data-go="paper">Discover papers ↗</button>' : '<button class="secondary" id="try-demo">Explore demo examples</button>'}</div>`;
}

async function loadResults() {
  const current = ++state.request;
  const data = await api("/items?" + params());
  if (current !== state.request) return;
  const lastPage = Math.max(1, Math.ceil(data.total / 12));
  if (state.page > lastPage) {state.page = lastPage; return loadResults();}
  state.records = data.items; state.total = data.total;
  $("result-count").textContent = data.total;
  $("results").innerHTML = data.items.map(card).join("") || emptyState();
  $("result-note").textContent = `${data.total} ${state.mode === "demo" ? "synthetic" : "collected"} results${state.q ? ` matching “${state.q}”` : ""}. ${state.view === "conference" ? "Deadlines are aggregator-reported; check earlier abstract registration and official requirements." : "Text match measures relevance, not research quality."}`;
  $("pagination").hidden = data.total <= 12;
  $("page-label").textContent = `Page ${state.page} of ${Math.max(1,Math.ceil(data.total/12))}`;
  $("previous").disabled = state.page === 1;
  $("next").disabled = state.page * 12 >= data.total;
  $("export").disabled = data.total === 0;
  await updateCounts();
}

function healthRows(sources) {
  return sources.map(s => `<div class="health-row"><strong>${esc(s.name)}</strong><span>${esc(s.status.replaceAll("_"," "))}</span><p>${esc(s.method)} · ${s.count || 0} records in last run</p><p>Last success: ${esc(dateText(s.last_success_at))}</p>${s.error ? `<p>${esc(s.error)}</p>` : ""}</div>`).join("");
}
function deadlineRows(records) {
  return records.map(r => `<div class="deadline-row"><button data-detail="${esc(r.id)}">${esc(r.title)}</button><small>${esc(deadlineLabel(r))} · ${esc(r.location)}</small></div>`).join("") || '<p class="muted">No upcoming deadlines in this collection. Refresh conference data or broaden your search.</p>';
}
async function updateCounts() {
  const mode = state.mode;
  const data = await api("/dashboard?mode=" + mode);
  if (mode !== state.mode) return;
  $("saved-count").textContent = data.saved;
  if (state.view === "dashboard") {
    $("stats").innerHTML = [[data.papers,"Collected papers"],[data.conferences,"Conference listings"],[data.saved,"Saved items"],[data.open_deadlines,"Future / due today"]].map(([n,t]) => `<div class="stat"><strong>${n}</strong><span>${t}</span></div>`).join("");
    $("upcoming").innerHTML = deadlineRows(data.upcoming) + '<h3>From your saved collection</h3>' + deadlineRows(data.saved_upcoming);
    $("source-health").innerHTML = healthRows(data.sources);
  }
}

function updateSearchButton() {
  const local = state.mode === "demo" || state.view === "saved";
  const waiting = state.busy && !local;
  $("search-button").disabled = waiting;
  $("search-button").textContent = waiting ? "Collecting…" : local ? "Search collection ↗" : "Search sources ↗";
  document.querySelectorAll("[data-query]").forEach(button => button.disabled = waiting);
}

async function setView(view) {
  ++state.request;
  state.view = view; state.page = 1;
  document.querySelectorAll(".nav").forEach(n => {n.classList.toggle("active", n.dataset.view === view); if(n.dataset.view === view) n.setAttribute("aria-current", "page"); else n.removeAttribute("aria-current");});
  $("crumb").textContent = labels[view];
  $("section-title").replaceChildren(document.createTextNode(labels[view] + " "), $("result-count"));
  $("section-label").textContent = view === "conference" ? "YOUR NEXT OPPORTUNITY" : view === "saved" ? "KEEP THE GOOD IDEAS" : "THE LITERATURE";
  const titles = {paper:"Your next idea<br>starts here<span>.</span>",conference:"Find your next<br>opportunity<span>.</span>",saved:"Good ideas,<br>kept close<span>.</span>",dashboard:"See the bigger<br>picture<span>.</span>"};
  $("hero-title").innerHTML = titles[view];
  $("hero-description").textContent = view === "conference" ? "Discover calls for papers, explore research communities, and keep submission dates in sight." : view === "saved" ? "The papers and possibilities you want to come back to." : view === "dashboard" ? "A snapshot of your collected research, saved ideas, and upcoming deadlines." : "Explore the literature. Find your community. Bring papers and possibilities into one place.";
  $("results-section").hidden = view === "dashboard";
  $("dashboard-section").hidden = view !== "dashboard";
  $("search-panel").hidden = view === "dashboard";
  $("source-filter").hidden = view !== "paper" || state.mode === "demo";
  $("year-filter").hidden = view !== "paper";
  $("location-filter").hidden = view !== "conference";
  $("deadline-filter").hidden = view !== "conference";
  updateSearchButton();
  if (view === "dashboard") await updateCounts(); else await loadResults();
}

async function setMode(mode) {
  const current = ++state.modeRequest;
  ++state.request;
  if (mode === "demo") await api("/demo", {method:"POST"});
  if (current !== state.modeRequest) return;
  state.mode = mode; state.page = 1; $("mode").value = mode; $("demo-banner").hidden = mode !== "demo";
  try {localStorage.setItem("eureka-mode", mode);} catch {}
  feedback("");
  await setView(state.view);
}

async function search() {
  if (state.busy && state.mode === "live" && state.view !== "saved") return;
  state.q = $("query").value.trim(); state.page = 1;
  if (state.mode === "demo" || state.view === "saved") {await loadResults(); return;}
  if (state.q.length < 2) {feedback("Enter a topic with at least two characters, or choose Browse collected.", "error"); return;}
  state.busy = true; updateSearchButton();
  const modeRequest = state.modeRequest;
  feedback("Collecting metadata from sources. Existing records remain available while this runs.", "busy");
  try {
    const sources = state.view === "conference" ? ["mldeadlines"] : $("source").value ? [$("source").value] : ["crossref", "arxiv", "mldeadlines"];
    const job = await api("/refresh", {method:"POST", body:JSON.stringify({query:state.q, sources})});
    let result, checked = -1;
    do {
      await new Promise(resolve => setTimeout(resolve, 1000));
      result = await api("/jobs/" + job.id);
      const complete = result.results?.length || 0;
      if (modeRequest === state.modeRequest) feedback(`Collecting metadata… ${complete} of ${sources.length} sources checked.`, "busy");
      if (complete !== checked && modeRequest === state.modeRequest) {
        checked = complete;
        if (state.view !== "dashboard") await loadResults(); else await updateCounts();
      }
    } while (["queued", "running"].includes(result.status));
    const message = result.results.map(r => `${names[r.source]}: ${r.status === "error" ? r.error : `${r.count} records (${r.status})`}`).join(" · ");
    if (modeRequest === state.modeRequest) feedback(result.error || message || "Refresh finished.", result.status === "failed" ? "error" : result.status === "partial" ? "warning" : "");
    if (state.view !== "dashboard") await loadResults(); else await updateCounts();
  } finally {
    state.busy = false; updateSearchButton();
  }
}

async function toggleSave(id, button) {
  const saved = button.getAttribute("aria-pressed") === "true";
  button.disabled = true;
  try {
    await api("/bookmarks" + (saved ? "/" + id : ""), {method:saved ? "DELETE" : "POST", ...(!saved ? {body:JSON.stringify({item_id:id})} : {})});
    toast(saved ? "Removed from your collection" : "Saved to your collection");
    await loadResults();
  } finally {button.disabled = false;}
}

async function showDetail(id) {
  const r = await api("/items/" + id);
  const link = url(r.url);
  $("detail-content").innerHTML = `<span class="badge ${r.demo ? "demo" : ""}">${r.demo ? "SYNTHETIC EXAMPLE" : r.kind.toUpperCase()}</span><h2 class="detail-title">${esc(r.title)}</h2>
    <div class="detail-meta">${esc(r.authors?.join(" · ") || r.location || "")} · ${esc(r.year || "Year unknown")}</div>
    ${r.kind === "conference" ? `<p class="deadline ${esc(r.status)}">${esc(deadlineLabel(r))}</p><p class="detail-text">Event: ${esc(r.event_dates || "Not announced")}<br>Source deadline: ${esc(r.deadline_raw || "Not announced")}<br>Timezone: ${esc(r.deadline_timezone || "Unspecified")}<br>${r.deadline_utc ? "Your local time: " + esc(dateText(r.deadline_utc)) : "No exact countdown available."}</p>` : ""}
    <p class="detail-text">${esc(r.abstract || r.note || "No abstract provided. Refer to the source record.")}</p>
    ${r.kind === "conference" ? '<p class="muted">Aggregator-reported, not independently verified. An open paper deadline does not mean abstract registration is still open. Check the original call for papers.</p>' : ""}
    <div class="tags">${r.topics.map(t => `<span class="tag">${esc(t)}</span>`).join("")}</div>
    <div class="detail-links">${link ? `<a class="primary" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Open original website ↗</a>` : ""}${r.sources.map(s => url(s.url) ? `<a class="secondary" href="${esc(url(s.url))}" target="_blank" rel="noopener noreferrer">${esc(names[s.source] || s.source)} ↗</a>` : "").join("")}</div>
    <p class="detail-meta">Retrieved ${esc(dateText(r.retrieved_at))}${r.doi ? " · DOI: " + esc(r.doi) : ""}</p>
    <label for="bookmark-note">Collection note</label><textarea id="bookmark-note" class="bookmark-note" maxlength="1000" placeholder="Why is this useful for your research?">${esc(r.bookmark_note || "")}</textarea><button class="secondary" id="save-note" data-id="${esc(id)}">Save record and note</button>
    <h3>Source observations</h3>${r.history.map(h => `<div class="history-row">${esc(names[h.source] || h.source)} · ${esc(dateText(h.observed_at))}${h.deadline_raw ? " · Deadline: " + esc(h.deadline_raw) : ""}</div>`).join("")}`;
  $("details").showModal();
}

function handleError(error) {feedback(error.message || "Something went wrong. Please try again.", "error");}
function act(fn) {return (...args) => Promise.resolve().then(() => fn(...args)).catch(handleError);}
$("search-form").addEventListener("submit", e => {e.preventDefault(); search().catch(handleError);});
document.addEventListener("click", act(async e => {
  const target = e.target.closest("button"); if (!target) return;
  if (target.dataset.view) await setView(target.dataset.view);
  else if (target.dataset.go) await setView(target.dataset.go);
  else if (target.dataset.query) {$("query").value = target.dataset.query; await search();}
  else if (target.dataset.save) await toggleSave(target.dataset.save, target);
  else if (target.dataset.detail) await showDetail(target.dataset.detail);
  else if (target.id === "try-demo") {state.q = ""; $("query").value = ""; await setMode("demo");}
  else if (target.id === "save-note") {await api("/bookmarks", {method:"POST",body:JSON.stringify({item_id:target.dataset.id,note:$("bookmark-note").value})}); toast("Record and note saved"); if(state.view !== "dashboard") await loadResults(); else await updateCounts();}
}));
$("mode").addEventListener("change", act(() => setMode($("mode").value)));
for (const id of ["sort", "source", "year", "location", "deadline"]) $(id).addEventListener("change", act(() => {state.page = 1; return loadResults();}));
$("reset-filters").addEventListener("click", act(() => {for(const id of ["source","year","location"]) $(id).value=""; $("deadline").value="all"; $("sort").value="relevance"; state.page=1; return loadResults();}));
$("clear-search").addEventListener("click", act(() => {state.q=""; $("query").value=""; state.page=1; return loadResults();}));
$("previous").addEventListener("click", act(() => {state.page=Math.max(1,state.page-1); return loadResults();}));
$("next").addEventListener("click", act(() => {state.page=Math.min(Math.max(1,Math.ceil(state.total/12)),state.page+1); return loadResults();}));
$("export").addEventListener("click", () => {const p=params(); p.delete("page"); p.delete("page_size"); window.location.href="/api/v1/export?"+p;});
$("source-details").addEventListener("click", act(() => setView("dashboard")));
$("close-details").addEventListener("click", () => $("details").close());
$("details").addEventListener("click", e => {if(e.target===$("details")) {const r=e.target.getBoundingClientRect(); if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom) e.target.close();}});
act(async () => {let mode="live"; try {mode=localStorage.getItem("eureka-mode");} catch {} await setMode(mode === "demo" ? "demo" : "live");})();
