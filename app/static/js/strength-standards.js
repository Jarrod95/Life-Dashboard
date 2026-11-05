/* Strength standards: native Solarized charts, read-only APIs, no third-party services. */
(() => {
"use strict";
const root = document.getElementById("gym-view");
if (!root || !location.pathname.endsWith("/standards")) return;
const base = "/api/v1/fitness/strength/standards";
const error = document.getElementById("gym-error");
const form = document.getElementById("strength-filters");
const params = new URLSearchParams(location.search);
const esc = v => String(v ?? "").replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const kg = v => v == null || !Number.isFinite(Number(v)) ? "—" :
  Number(v).toLocaleString("en-AU", {maximumFractionDigits:1}) + " kg";
const ratio = v => v == null || !Number.isFinite(Number(v)) ? "—" :
  Number(v).toFixed(2) + "× BW";
const dateLabel = v => v || "—";
const color = token => getComputedStyle(document.documentElement).getPropertyValue(token).trim();
const query = (endpoint, overrides={}) => {
  const q = new URLSearchParams(params);
  for (const [k,v] of Object.entries(overrides)) {
    if (v === null || v === undefined || v === "") q.delete(k); else q.set(k, v);
  }
  return base + endpoint + "?" + q;
};
async function get(endpoint, overrides) {
  const response = await fetch(query(endpoint, overrides), {credentials:"same-origin"});
  const data = await response.json();
  if (!response.ok) throw Error(data.error?.message || "Strength data unavailable");
  return data;
}
let catalogue = [], selected = "", current = null, history = [], comparison = [];
let sorting = {field:"rated", descending:true};
let chartDisposers = [], progressDisposer = null, requestId = 0;
function clearCharts() {chartDisposers.forEach(fn => fn()); chartDisposers = []; progressDisposer = null;}
function card(heading, html, cls="strength-half") {
  return '<section class="strength-card ' + cls + '"><h2>' + esc(heading) + '</h2>' + html + '</section>';
}
function kpi(label, value, detail) {
  return '<article class="strength-card strength-kpi"><small>'+esc(label)+'</small><strong>'+
    esc(value)+'</strong><small>'+esc(detail)+'</small></article>';
}
function noData(message) {return '<p class="strength-empty">'+esc(message)+'</p>';}
function applyFilters() {
  const years = form.elements.namedItem("year"), month = form.elements.namedItem("month");
  for (let yr = new Date().getFullYear(); yr >= 2015; yr--) years.add(new Option(String(yr), String(yr)));
  for (const name of ["year","month","from","to"]) {
    if (params.has(name)) form.elements.namedItem(name).value = params.get(name);
  }
  form.addEventListener("submit", ev => {
    ev.preventDefault();
    for (const name of ["year","month","from","to"]) {
      const value = form.elements.namedItem(name).value;
      if (value && value !== "all") params.set(name, value); else params.delete(name);
    }
    historyState(); refresh();
  });
  document.getElementById("gym-reset").addEventListener("click", () => {
    ["year","month","from","to"].forEach(k => params.delete(k));
    for (const name of ["year","month","from","to"]) form.elements.namedItem(name).value =
      name === "month" ? "all" : "";
    historyState(); refresh();
  });
  document.querySelectorAll(".strength-tabs a").forEach(a => {
    a.classList.toggle("active", a.pathname === location.pathname);
    a.addEventListener("click", () => {
      // Preserve shared date filters, but never pass standards-only window/ID to other tabs.
      const keep = new URLSearchParams();
      for (const k of ["year","month","from","to"]) if (params.has(k)) keep.set(k, params.get(k));
      if (keep.size) a.search = keep.toString();
    });
  });
}
function historyState() {window.history.replaceState(null, "", location.pathname + "?" + params.toString());}
function labelPeriod(item) {
  return item.period.window === "all_time"
    ? "All-time heaviest eligible set · 90-day peak bodyweight at as-of date"
    : "Heaviest eligible set · " + (item.period.window === "90d" ? "past 90 days" : "past 365 days");
}
function groupOptions(rows) {
  const group = (rated, title) => {
    const options = rows.filter(r => r.rated === rated).map(r =>
      '<option value="'+esc(r.id)+'">'+esc(r.name)+'</option>').join("");
    return options ? '<optgroup label="'+esc(title)+'">'+options+'</optgroup>' : "";
  };
  return group(true,"Rated exercises") + group(false,"Unrated / ratio only");
}
function controls() {
  return card("Exercise and period",
    '<div class="standards-controls">'+
      '<label for="standard-search">Search exercises<input type="search" id="standard-search" placeholder="Filter exercises by name"></label>'+
      '<label for="standard-exercise">Exercise<select id="standard-exercise">'+groupOptions(catalogue)+'</select></label>'+
      '<label for="standard-window">Performance range<select id="standard-window">'+
      '<option value="90d">90 days</option><option value="365d">365 days</option><option value="all_time">All time</option>'+
      '</select></label>'+
      '<label for="standard-sex">Benchmark reference<select id="standard-sex">'+
      '<option value="male">Male</option><option value="female">Female</option>'+
      '</select></label></div><p id="standard-source" class="muted"></p>', "strength-full");
}
function render() {
  clearCharts();
  if (!current) {root.innerHTML = noData("No matching exercise records."); return;}
  const d = current.data, source = current.meta, weight = d.bodyweight, best = d.best_set;
  const detail = best ? kg(best.weight_kg)+" × "+best.reps+" · "+best.date+" · "+(best.one_rm_kind === "observed" ? "Actual single" : "Epley estimate") : "No eligible working sets";
  const sourceText = source.provider_version
    ? "OpenProgression · v"+source.provider_version+" · bodyweight-specific 1RM · simplified dashboard labels"
    : "Benchmarks unavailable — verify pinned OpenProgression source";
  const currentControls = controls();
  const milestone = d.next_milestone
    ? '<strong>'+esc(d.next_milestone.label)+' · '+kg(d.next_milestone.target_kg)+'</strong>'+
      '<p>'+kg(d.next_milestone.gap_kg)+' to go · '+Number(d.next_milestone.progress_pct).toFixed(1)+'% of target</p>'
    : d.status === "rated" ? '<strong>Elite achieved</strong>' :
      noData(d.reason || "A validated bodyweight and approved benchmark are required.");
  const barInfo = (d.status === "rated" && d.benchmarks)
    ? '<canvas id="standard-bars" class="strength-chart standards-bars" tabindex="0" role="img" aria-label="Your one-repetition maximum compared with Good, Excellent and Elite benchmark loads. Use arrow keys for values."></canvas>'+
      '<p id="standard-bars-detail" class="strength-tooltip" aria-live="polite">Focus or hover over a bar for its value.</p>'+
      '<div class="strength-table-wrap"><table class="strength-table"><caption>Benchmark loads in kilograms</caption>'+
      '<thead><tr><th scope="col">Bar</th><th scope="col">1RM (kg)</th></tr></thead><tbody>'+
      [
        ["Your 1RM",best.one_rm_kg],["Good",d.benchmarks.good_kg],
        ["Excellent",d.benchmarks.excellent_kg],["Elite",d.benchmarks.elite_kg],
      ].map(([label,value]) => '<tr><th scope="row">'+esc(label)+'</th><td>'+kg(value)+'</td></tr>').join("")+
      '</tbody></table></div>'
    : noData("Benchmark comparison unavailable for this exercise: "+(d.reason || d.status));
  root.innerHTML = '<div class="strength-grid">'+currentControls+
    kpi("Peak bodyweight · 90d",weight ? kg(weight.weight_kg) : "Unavailable",
        weight ? weight.source+" · "+weight.date+" · highest measured in past 90 days" : "No measured bodyweight in past 90 days")+
    kpi("e1RM · heaviest set",best ? kg(best.one_rm_kg) : "—",detail)+
    kpi("Relative strength",ratio(d.relative_strength), "e1RM of heaviest set ÷ peak 90-day bodyweight")+
    kpi("Strength category",d.classification?.label || "Unrated", d.status === "rated" ? "Verified "+(source.sex_category||"")+" standard" : d.reason || d.status)+
    card("Next milestone",milestone,"strength-full")+
    card("Your lift vs strength standards",barInfo,"strength-half")+
    card("Relative-strength progression",
      '<div class="strength-controls"><label for="standard-progress-mode">Metric</label>'+
      '<select id="standard-progress-mode"><option value="ratio">Ratio (× BW)</option>'+
      '<option value="kg">Estimated 1RM (kg)</option></select></div>'+
      '<canvas id="standard-progression" class="strength-chart standards-line" tabindex="0" role="img" aria-label="Historical strength by workout, arrow keys read individual observations."></canvas>'+
      '<p id="standard-progression-detail" class="strength-tooltip" aria-live="polite"></p>'+
      '<p class="muted">Each workout uses the highest recorded bodyweight in the preceding 90 days (no future readings). Missing measurements create gaps.</p>',
      "strength-half")+
    card("Workout evidence",historyTable(),"strength-full")+
    card("All exercise comparison",
      '<div class="strength-controls"><label for="standard-table-search">Filter table</label>'+
      '<input type="search" id="standard-table-search" placeholder="Exercise name or status">'+
      '<label class="standards-include-unrated"><input type="checkbox" id="standard-table-all"> Show unrated exercises</label>'+
      '<a class="button" id="standard-export" href="'+esc(query("/comparison.csv"))+'">Export all CSV</a></div>'+
      '<div id="standard-comparison-table"></div>',"strength-full")+
    '</div>';
  const ex = document.getElementById("standard-exercise");
  ex.value = selected;
  document.getElementById("standard-window").value = params.get("window") || "90d";
  document.getElementById("standard-sex").value = params.get("sex") || "male";
  const sourceEl = document.getElementById("standard-source");
  sourceEl.textContent = sourceText+" · "+(source.sex_category==="female"?"Female":"Male")+
    " benchmark · e1RM from heaviest eligible set · peak bodyweight from trailing 90 days";
  if (d.reason) sourceEl.textContent += " · "+d.reason;
  const search = document.getElementById("standard-search");
  search.addEventListener("input", () => {
    const needle = search.value.toLocaleLowerCase();
    const shown = catalogue.filter(x => x.name.toLocaleLowerCase().includes(needle));
    ex.innerHTML = groupOptions(shown);
    if (shown.some(x => x.id === selected)) ex.value = selected;
  });
  ex.addEventListener("change", () => {
    selected = ex.value; params.set("exercise_id", selected); historyState(); refresh();
  });
  document.getElementById("standard-window").addEventListener("change", e => {
    params.set("window", e.target.value); historyState(); reloadCatalog();
  });
  document.getElementById("standard-sex").addEventListener("change", e => {
    params.set("sex", e.target.value); historyState(); reloadCatalog();
  });
  document.getElementById("standard-progress-mode").addEventListener("change", drawProgress);
  document.getElementById("standard-table-search").addEventListener("input", drawComparison);
  document.getElementById("standard-table-all").addEventListener("change", drawComparison);
  if (d.status === "rated" && d.benchmarks) {
    chartDisposers.push(plotBars("standard-bars", [
      {label:"Your 1RM",value:best.one_rm_kg,color:"--strength-bar-current"},
      {label:"Good",value:d.benchmarks.good_kg,color:"--strength-bar-good"},
      {label:"Excellent",value:d.benchmarks.excellent_kg,color:"--strength-bar-excellent"},
      {label:"Elite",value:d.benchmarks.elite_kg,color:"--strength-bar-elite"},
    ]));
  }
  drawProgress(); drawComparison();
}
function historyTable() {
  if (!history.length) return noData("No eligible sessions in this period.");
  return '<div class="strength-table-wrap"><table class="strength-table"><caption>Workout and matched bodyweight evidence</caption>'+
    '<thead><tr><th>Date</th><th>Set</th><th>1RM</th><th>BW</th><th>Ratio</th><th>Category</th><th>Weight source</th></tr></thead><tbody>'+
    history.map(p => '<tr><td>'+esc(p.date)+'</td><td>'+kg(p.weight_kg)+' × '+p.reps+'</td>'+
      '<td>'+kg(p.one_rm_kg)+'</td><td>'+kg(p.bodyweight?.weight_kg)+'</td>'+
      '<td>'+ratio(p.relative_strength)+'</td><td>'+esc(p.classification?.label||"Unrated")+'</td>'+
      '<td>'+esc(p.bodyweight ? p.bodyweight.source+" · "+p.bodyweight.date+" · "+p.bodyweight.age_days+"d" : "Unavailable")+
      '</td></tr>').join("")+'</tbody></table></div>';
}
function drawComparison() {
  const element = document.getElementById("standard-comparison-table");
  if (!element) return;
  const filter = (document.getElementById("standard-table-search")?.value || "").toLocaleLowerCase();
  const includeUnrated = document.getElementById("standard-table-all")?.checked;
  const data = comparison.filter(r => (includeUnrated || r.status==="rated") &&
    (r.exercise+" "+r.status+" "+(r.reason||"")).toLocaleLowerCase().includes(filter)).slice();
  const fields = [
    ["exercise","Exercise"],["best_set","Heaviest set"],["one_rm_kg","e1RM (kg)"],
    ["bodyweight_kg","BW (kg)"],["ratio","Ratio"],["classification","Classification"],
    ["next_target_kg","Next target (kg)"],["gap_kg","Gap (kg)"],["last_record","Last record"]
  ];
  if (sorting.field) data.sort((a,b) => {
    const v = r => sorting.field === "best_set" ? r.best_set?.one_rm_kg : r[sorting.field];
    const av = v(a), bv = v(b);
    let diff = av == null ? 1 : bv == null ? -1 :
      typeof av === "number" && typeof bv === "number" ? av-bv :
      String(av).localeCompare(String(bv),"en-AU",{sensitivity:"base"});
    if (av != null && bv != null && sorting.descending) diff *= -1;
    return diff || a.exercise.localeCompare(b.exercise);
  });
  const cell = (r,k) => {
    if (k === "exercise") return '<a href="/fitness/strength/exercises/'+encodeURIComponent(r.exercise_id)+'">'+esc(r.exercise)+'</a>'+
      (r.status !== "rated" ? '<small class="standards-reason">'+esc(r.reason||r.status)+'</small>' : "");
    if (k === "best_set") return r.best_set ? kg(r.best_set.weight_kg)+" × "+r.best_set.reps : "No sets in range";
    if (k === "one_rm_kg" || k === "bodyweight_kg") return kg(r[k]);
    if (k === "next_target_kg" || k === "gap_kg")
      return r.status==="rated" ? (r[k] == null ? (k==="next_target_kg"?"Elite achieved":"0 kg") : kg(r[k]))
        : "Not benchmarked";
    if (k === "classification") return esc(r[k] || (r.status==="unrated_exercise"?"Not benchmarked":r.status));
    if (k === "ratio") return ratio(r[k]);
    return esc(r[k] ?? "—");
  };
  element.innerHTML = data.length ? '<div class="strength-table-wrap"><table class="strength-table">'+
    '<caption>Exercise standards are not interchangeable rankings</caption><thead><tr>'+
    fields.map(([field,name]) => '<th scope="col"'+(field === sorting.field ? ' aria-sort="'+(sorting.descending?"descending":"ascending")+'"' : "")+
      '><button type="button" data-sort="'+esc(field)+'">'+esc(name)+'</button></th>').join("")+
    '</tr></thead><tbody>'+data.map(r => '<tr>'+fields.map(([field])=>'<td>'+cell(r,field)+'</td>').join("")+'</tr>').join("")+
    '</tbody></table></div>' : noData(includeUnrated ?
      "No matching exercises in this period." :
      "No rated exercises in this period. Choose a different range or show unrated exercises.");
  element.querySelectorAll("[data-sort]").forEach(b => b.addEventListener("click", () => {
    const field = b.dataset.sort;
    sorting = {field,descending:sorting.field===field?!sorting.descending:false}; drawComparison();
  }));
}
function plotBase(id, renderer) {
  const el = document.getElementById(id), tooltip = document.getElementById(id+"-detail");
  if (!el) return () => {};
  let points=[], index=0;
  const draw = () => {
    const r = el.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
    if (r.width < 10 || r.height < 10) return;
    el.width = Math.round(r.width*dpr); el.height = Math.round(r.height*dpr);
    const ctx = el.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
    ctx.clearRect(0,0,r.width,r.height);ctx.font = "12px system-ui";
    points = renderer(ctx,r.width,r.height) || [];
  };
  function focus(i) {
    if (!points.length) return;
    index = Math.max(0,Math.min(points.length-1,i));
    tooltip.textContent = points[index].label;
  }
  const move = ev => {
    if (!points.length) return;
    const rect = el.getBoundingClientRect(), x=ev.clientX-rect.left;
    focus(points.reduce((best,p,i) => Math.abs(p.x-x)<Math.abs(points[best].x-x)?i:best,0));
  };
  const key = ev => {
    if (["ArrowLeft","ArrowRight","Home","End"].includes(ev.key)) {
      ev.preventDefault();
      focus(ev.key === "Home"?0:ev.key === "End"?points.length-1:index+(ev.key==="ArrowLeft"?-1:1));
    }
  };
  el.addEventListener("pointermove",move);el.addEventListener("keydown",key);
  el.addEventListener("focus",()=>focus(index));
  const observer = new ResizeObserver(draw);observer.observe(el);
  document.addEventListener("life-theme-change",draw);
  draw();
  return () => {observer.disconnect();document.removeEventListener("life-theme-change",draw);
    el.removeEventListener("pointermove",move);el.removeEventListener("keydown",key);};
}
function grid(ctx,width,height,max,left=46,bottom=47) {
  const top=25,right=12,w=Math.max(1,width-left-right),h=Math.max(1,height-top-bottom);
  ctx.strokeStyle=color("--chart-grid");ctx.fillStyle=color("--text-muted");
  ctx.textAlign="left";
  for(let tick=0;tick<=4;tick++){
    const value=max*tick/4,y=top+h-h*tick/4;
    ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();
    ctx.fillText(Number(value).toFixed(max<=5?2:0),3,y+4);
  }
  return {top,left,right,w,h};
}
function plotBars(id, bars) {
  return plotBase(id,(ctx,width,height)=>{
    const max=Math.max(1,...bars.map(b=>b.value))*1.12,area=grid(ctx,width,height,max,44,60);
    return bars.map((b,i)=>{
      const x=area.left+(i+.5)*area.w/bars.length;
      const y=area.top+area.h-b.value/max*area.h;
      const bw=Math.max(12,Math.min(74,area.w/bars.length*.58));
      ctx.fillStyle=color(b.color)||color("--accent");
      ctx.fillRect(x-bw/2,y,bw,area.top+area.h-y);
      ctx.textAlign="center";ctx.fillStyle=color("--text-primary");
      ctx.fillText(kg(b.value),x,Math.max(13,y-8));
      ctx.fillStyle=color("--text-muted");ctx.font=width<360?"10px system-ui":"12px system-ui";
      ctx.fillText(b.label,x,height-22);
      return {x,y,label:b.label+" · "+kg(b.value)};
    });
  });
}
function drawProgress() {
  const original = document.getElementById("standard-progression");
  if (!original) return;
  if (progressDisposer) {
    progressDisposer();
    chartDisposers=chartDisposers.filter(d=>d!==progressDisposer);
  }
  const mode=document.getElementById("standard-progress-mode").value;
  const series=history.map(p=>({label:p.date+" · "+kg(p.weight_kg)+" × "+p.reps+
    " · "+(p.bodyweight ? p.bodyweight.source+" "+p.bodyweight.date+" ("+kg(p.bodyweight.weight_kg)+")" : "bodyweight unavailable"),
    value:mode==="kg"?p.one_rm_kg:p.relative_strength,date:p.date}));
  const dispose=plotBase("standard-progression",(ctx,width,height)=>{
    if (!series.length) {ctx.fillStyle=color("--text-muted");ctx.fillText("No workouts in this period",15,30);return [];}
    const max=Math.max(1,...series.map(p=>p.value||0))*1.12,area=grid(ctx,width,height,max,44,43);
    const pts=series.map((p,i)=>{
      const x=area.left+(i+.5)*area.w/series.length;
      const y=p.value == null?null:area.top+area.h-p.value/max*area.h;
      return {x,y,label:p.label+" · "+(p.value==null?"ratio unavailable":mode==="kg"?kg(p.value):ratio(p.value))};
    });
    ctx.lineWidth=2;ctx.strokeStyle=color("--accent");ctx.fillStyle=color("--accent");
    let previous=null;
    pts.forEach(p=>{
      if(p.y==null){previous=null;return;}
      if(previous){ctx.beginPath();ctx.moveTo(previous.x,previous.y);ctx.lineTo(p.x,p.y);ctx.stroke();}
      ctx.beginPath();ctx.arc(p.x,p.y,3,0,Math.PI*2);ctx.fill();previous=p;
    });
    ctx.fillStyle=color("--text-muted");ctx.textAlign="center";
    const every=Math.max(1,Math.ceil(pts.length/(width<480?3:7)));
    pts.forEach((p,i)=>{if(i%every===0)ctx.fillText(series[i].date.slice(5),p.x,height-13);});
    return pts;
  });
  progressDisposer=dispose;chartDisposers.push(dispose);
}
async function loadComparison() {
  const first=await get("/comparison",{page:1,page_size:200});
  const rows=[...first.data],count=first.meta.total;
  for(let page=2;rows.length<count && page<=Math.ceil(count/200);page++){
    const next=await get("/comparison",{page,page_size:200});rows.push(...next.data);
  }
  return rows;
}
async function refresh() {
  const seq=++requestId;
  error.hidden=true;
  clearCharts();
  root.setAttribute("aria-busy","true");
  root.innerHTML='<p class="muted">Loading strength standards…</p>';
  try {
    const [summary, progress, rows]=await Promise.all([
      get("/summary",{exercise_id:selected}),
      get("/exercises/"+encodeURIComponent(selected)+"/progress"),
      loadComparison()
    ]);
    if(seq!==requestId)return;
    current=summary; history=progress.data;comparison=rows;
    render();
  } catch(e) {
    if(seq!==requestId)return;
    error.hidden=false;error.textContent=e.message || "Unable to load strength standards";
    root.innerHTML=noData("Unable to load the selected exercise. Check sources and filters.");
  } finally {if(seq===requestId)root.setAttribute("aria-busy","false");}
}
async function reloadCatalog() {
  try {
    const list=await get("/exercises");
    catalogue=list.data;
    if (!catalogue.length) {
      root.innerHTML=noData("No Gym Day working sets imported. Sync an export to begin.");
      return;
    }
    const candidate=catalogue.find(r=>r.id===selected);
    // Never default to an empty movement such as Ab Wheel Rollout.
    if (!candidate || !candidate.eligible_sessions) {
      selected=(catalogue.find(r=>r.rated && r.eligible_sessions) ||
        catalogue.find(r=>r.eligible_sessions) || catalogue[0]).id;
    }
    params.set("exercise_id",selected);
    historyState();
    await refresh();
  } catch(e) {
    error.hidden=false;error.textContent=e.message;
    root.innerHTML=noData("Strength data unavailable.");
  }
}
async function init() {
  applyFilters();
  if (!["90d","365d","all_time"].includes(params.get("window")))
    params.set("window","90d");
  // Visible editable reference, never derived from the workout itself.
  if (!["male","female"].includes(params.get("sex")))params.set("sex","male");
  selected=params.get("exercise_id") || "";
  await reloadCatalog();
}
init();
})();
