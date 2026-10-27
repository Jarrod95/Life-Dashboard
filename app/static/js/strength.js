/* Solarized Gym Day explorer. All information comes from same-origin APIs. */
(() => {
"use strict";
const root=document.getElementById("gym-view");if(!root)return;
const base="/api/v1/fitness/strength",path=decodeURI(location.pathname);
const error=document.getElementById("gym-error"),form=document.getElementById("strength-filters");
const year=document.getElementById("gym-year"),month=document.getElementById("gym-month");
const state=new URLSearchParams(location.search);
const fmt=n=>n==null?"—":new Intl.NumberFormat("en-AU",{maximumFractionDigits:1}).format(n);
const fmtDate=d=>d?new Date(d+"T12:00:00Z").toLocaleDateString("en-AU",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}):"—";
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const url=(endpoint,params={})=>{const p=new URLSearchParams(state);for(const [k,v] of Object.entries(params)){if(v===null||v===undefined||v==="")p.delete(k);else p.set(k,v);}return base+endpoint+"?"+p;};
async function get(endpoint,params){const r=await fetch(url(endpoint,params));const j=await r.json();if(!r.ok)throw Error(j.error?.message||"Unable to load strength data");return j;}
function showError(e){error.hidden=false;error.textContent=e.message||String(e);}
function card(title,contents,cls="strength-half"){return '<section class="strength-card '+cls+'"><h2>'+esc(title)+'</h2>'+contents+'</section>';}
function kpi(label,val,unit=""){return '<article class="strength-card strength-kpi"><small>'+esc(label)+'</small><strong>'+fmt(val)+'</strong><small>'+esc(unit)+'</small></article>';}
function canvas(id){return '<canvas class="strength-chart" id="'+id+'" tabindex="0" role="img" aria-label="Interactive '+esc(id.replaceAll("-"," "))+' chart"></canvas><p class="strength-tooltip" id="'+id+'-detail">Focus or hover over a data point for details.</p>';}
function dataTable(rows,cols){if(!rows.length)return '<p class="strength-empty">No matching records.</p>';return '<div class="strength-table-wrap"><table class="strength-table"><thead><tr>'+cols.map(c=>'<th scope="col">'+esc(c[0])+'</th>').join("")+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+cols.map(c=>'<td>'+String(c[1](row))+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>';}
function link(s,label,type="sessions"){return '<a href="/fitness/strength/'+type+'/'+encodeURIComponent(s)+'">'+esc(label)+'</a>';}
function chart(id,items,{x="label",y="value",mode="bar",unit="",click}={}){
 const el=document.getElementById(id);if(!el)return;const tooltip=document.getElementById(id+"-detail");
 let hits=[],selected=0;
 const color=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 function draw(){
  const box=el.getBoundingClientRect(),width=box.width,height=box.height;if(!width||!height)return;
  const dpr=window.devicePixelRatio||1;el.width=width*dpr;el.height=height*dpr;
  const c=el.getContext("2d");c.scale(dpr,dpr);c.clearRect(0,0,width,height);
  if(!items.length){c.fillStyle=color("--text-muted");c.fillText("No data in selected period",15,32);return;}
  const p={l:58,r:14,t:18,b:42},w=width-p.l-p.r,h=height-p.t-p.b;
  const max=Math.max(1,...items.map(a=>Number(a[y])||0))*1.1;
  c.font="11px system-ui";c.strokeStyle=color("--chart-grid");c.fillStyle=color("--text-muted");
  for(let i=0;i<=4;i++){const v=max*i/4,yy=p.t+h-v/max*h;c.beginPath();c.moveTo(p.l,yy);c.lineTo(width-p.r,yy);c.stroke();c.fillText(fmt(v),5,yy+4);}
  hits=[];
  items.forEach((item,i)=>{
   const value=Number(item[y])||0,xx=p.l+(i+.5)*w/items.length,yy=p.t+h-value/max*h;
   if(mode==="bar"){const bar=Math.max(2,Math.min(26,w/items.length*.7));c.fillStyle=color("--accent");c.fillRect(xx-bar/2,yy,bar,p.t+h-yy);}
   hits.push({x:xx,y:yy,item});
  });
  if(mode==="line"){c.beginPath();hits.forEach((hit,i)=>i?c.lineTo(hit.x,hit.y):c.moveTo(hit.x,hit.y));c.strokeStyle=color("--accent");c.lineWidth=2;c.stroke();hits.forEach(hit=>{c.beginPath();c.arc(hit.x,hit.y,2.8,0,Math.PI*2);c.fillStyle=color("--accent");c.fill();});}
  c.textAlign="center";c.fillStyle=color("--text-muted");
  const every=Math.max(1,Math.ceil(items.length/7));hits.forEach((hit,i)=>{if(i%every===0)c.fillText(String(items[i][x]).slice(-9),hit.x,height-18);});
 }
 function focus(i){if(!hits.length)return;selected=Math.max(0,Math.min(i,hits.length-1));const hit=hits[selected];tooltip.textContent=String(hit.item[x])+" · "+fmt(hit.item[y])+(unit?" "+unit:"");}
 el.addEventListener("pointermove",e=>{if(!hits.length)return;const rect=el.getBoundingClientRect(),xx=e.clientX-rect.left;focus(hits.reduce((best,h,i)=>Math.abs(h.x-xx)<Math.abs(hits[best].x-xx)?i:best,0));});
 el.addEventListener("click",()=>{if(click&&hits[selected])click(hits[selected].item);});
 el.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Home","End","Enter"].includes(e.key)){e.preventDefault();if(e.key==="Enter"&&click&&hits[selected])click(hits[selected].item);else focus(e.key==="Home"?0:e.key==="End"?hits.length-1:selected+(e.key==="ArrowLeft"?-1:1));}});
 const resize=new ResizeObserver(draw);resize.observe(el);document.addEventListener("life-theme-change",draw);draw();
}
function setControls(){const now=new Date().getFullYear();for(let y=now;y>=2015;y--)year.add(new Option(String(y),String(y)));for(const key of ["year","month","from","to"]){const input=form.elements.namedItem(key);if(state.has(key))input.value=state.get(key);}form.addEventListener("submit",e=>{e.preventDefault();const p=new URLSearchParams;for(const key of ["year","month","from","to"]){const value=form.elements.namedItem(key).value;if(value&&value!=="all")p.set(key,value);}location.search=p.toString();});document.getElementById("gym-reset").addEventListener("click",()=>location.href=location.pathname);document.querySelectorAll(".strength-tabs a").forEach(a=>a.classList.toggle("active",a.pathname===path));}
async function overview(){
 const [{data:d},{data:vol}]=await Promise.all([get("/overview"),get("/volume")]);
 root.innerHTML='<div class="strength-grid">'+
 kpi("Workout sessions",d.kpis.sessions)+kpi("Training days",d.kpis.training_days)+kpi("Time under training",d.kpis.hours,"hours")+kpi("Average duration",d.kpis.avg_minutes,"minutes")+
 kpi("Working sets",d.kpis.working_sets)+kpi("Total reps",d.kpis.reps)+kpi("Logged load × reps",d.kpis.volume_kg,"kg")+kpi("Exercises trained",d.kpis.exercises)+
 card("Sessions by ISO week",canvas("gym-weekly"))+card("Training volume by week",canvas("gym-volume"))+
 card("Sets by primary muscle",'<div class="strength-controls"><label for="gym-role">Attribution</label><select id="gym-role"><option value="primary">Primary</option><option value="secondary">Secondary</option></select></div>'+canvas("gym-muscles"))+
 card("Most performed exercises",dataTable(d.top_exercises,[[ "Exercise",r=>esc(r.name) ],["Working sets",r=>fmt(r.sets)]]))+
 card("Training calendar",'<div class="gym-calendar-toolbar"><button id="gym-calendar-prev" type="button" aria-label="Previous month">‹</button><label for="gym-calendar-month">Month</label><input type="month" id="gym-calendar-month" aria-label="Choose calendar month"><button id="gym-calendar-next" type="button" aria-label="Next month">›</button><span id="gym-calendar-label" aria-live="polite"></span></div><div class="gym-calendar-weekdays" aria-hidden="true"><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span><span>Fri</span><span>Sat</span><span>Sun</span></div><div class="strength-calendar" id="gym-calendar" role="grid" aria-label="Monthly training sessions"></div><p class="muted gym-calendar-legend">Volume = completed working sets × logged external load (kg). Click a workout to view its sets.</p>',"strength-full")+
 '</div>';
 chart("gym-weekly",d.weekly,{x:"week",y:"count",unit:"sessions"});
 chart("gym-volume",vol,{x:"period",y:"volume_kg",mode:"line",unit:"kg"});
 async function drawMuscles(){const r=await get("/muscles",{role:document.getElementById("gym-role").value});chart("gym-muscles",r.data.slice(0,20),{x:"name",y:"sets",unit:"sets"});}
 document.getElementById("gym-role").onchange=()=>drawMuscles().catch(showError);await drawMuscles();
 const cal=document.getElementById("gym-calendar");
 const picker=document.getElementById("gym-calendar-month");
 const inSydney=new Intl.DateTimeFormat("en-CA",{timeZone:"Australia/Sydney",year:"numeric",month:"2-digit"}).formatToParts(new Date());
 const component=name=>inSydney.find(p=>p.type===name).value;
 const currentMonth=component("year")+"-"+component("month");
 // The standalone calendar has its own month state; overview analytics filters are independent.
 picker.value=(state.get("year")&&state.get("month")&&state.get("month")!=="all")
   ?state.get("year")+"-"+state.get("month").padStart(2,"0"):currentMonth;
 async function drawCalendar(){
   const match=/^(\\d{4})-(\\d{2})$/.exec(picker.value);
   if(!match)return;
   const y=Number(match[1]),m=Number(match[2]);
   if(y<1900||y>2200||m<1||m>12)return;
   const response=await get("/calendar",{year:y,month:m,from:null,to:null,exercise:null,muscle:null,workout:null});
   const days=new Map(response.data.days.map(d=>[d.date,d]));
   document.getElementById("gym-calendar-label").textContent=new Intl.DateTimeFormat("en-AU",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(Date.UTC(y,m-1,1)));
   const first=(new Date(Date.UTC(y,m-1,1)).getUTCDay()+6)%7;
   const count=new Date(Date.UTC(y,m,0)).getUTCDate();
   cal.replaceChildren();
   for(let i=0;i<first;i++){const blank=document.createElement("div");blank.className="gym-calendar-outside";blank.setAttribute("aria-hidden","true");cal.appendChild(blank);}
   for(let day=1;day<=count;day++){
     const date=picker.value+"-"+String(day).padStart(2,"0");
     const record=days.get(date);
     const cell=document.createElement("div");cell.className="gym-calendar-day"+(record?" has-training":"");
     cell.setAttribute("role","gridcell");cell.setAttribute("aria-label",fmtDate(date)+(record?" - "+record.sessions.length+" workouts":" - no workouts"));
     const number=document.createElement("span");number.className="gym-calendar-date";number.textContent=String(day);cell.appendChild(number);
     if(record){
       for(const session of record.sessions){
         const item=document.createElement("a");item.className="gym-calendar-session";
         item.href="/fitness/strength/sessions/"+encodeURIComponent(session.id);
         const title=document.createElement("strong");title.textContent=session.name;
         const volume=document.createElement("small");volume.textContent=fmt(session.volume_kg)+" kg";
         item.append(title,volume);cell.appendChild(item);
       }
     }
     cal.appendChild(cell);
   }
 }
 function moveMonth(change){
   const [y,m]=picker.value.split("-").map(Number);
   const next=new Date(Date.UTC(y,m-1+change,1));
   picker.value=next.toISOString().slice(0,7);
   drawCalendar().catch(showError);
 }
 document.getElementById("gym-calendar-prev").onclick=()=>moveMonth(-1);
 document.getElementById("gym-calendar-next").onclick=()=>moveMonth(1);
 picker.onchange=()=>drawCalendar().catch(showError);
 await drawCalendar();
}
async function exercises(){
 root.innerHTML=card("Exercise explorer",'<div class="strength-controls"><input id="gym-search" type="search" placeholder="Search exercises" aria-label="Search exercises"><button id="gym-download">Export CSV</button></div><div id="gym-results"></div><div class="strength-controls"><button id="gym-prev">Previous</button><span id="gym-page"></span><button id="gym-next">Next</button></div>',"strength-full");
 let page=1,rows=[];const search=document.getElementById("gym-search");
 async function refresh(){const result=await get("/exercises",{q:search.value,page,page_size:25});rows=result.data;document.getElementById("gym-results").innerHTML=dataTable(rows,[["Exercise",e=>link(e.id,e.name,"exercises")],["Category",e=>esc(e.category)],["Primary muscle",e=>esc((e.primary_muscles||[]).join(", "))],["Equipment",e=>esc(e.equipment)]]);document.getElementById("gym-page").textContent="Page "+page+" · "+result.meta.total+" exercises";document.getElementById("gym-prev").disabled=page<=1;document.getElementById("gym-next").disabled=page*25>=result.meta.total;}
 let pending;search.addEventListener("input",()=>{clearTimeout(pending);pending=setTimeout(()=>{page=1;refresh().catch(showError);},250);});
 document.getElementById("gym-prev").onclick=()=>{page--;refresh().catch(showError);};
 document.getElementById("gym-next").onclick=()=>{page++;refresh().catch(showError);};
 document.getElementById("gym-download").onclick=()=>csv(rows,["name","category","equipment"]);
 await refresh();
}
function csv(rows,fields){const safe=v=>'"'+String(v??"").replaceAll('"','""').replace(/^[=+@-]/,"'")+'"';const body=[fields.join(","),...rows.map(r=>fields.map(f=>safe(r[f])).join(","))].join("\r\n");const blob=new Blob([body],{type:"text/csv;charset=utf-8"});const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="gymday-export.csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function exerciseDetail(id){
 const r=await get("/exercises/"+encodeURIComponent(id)+"/progress",{metric:"e1rm"}),name=r.meta.exercise;
 root.innerHTML=card(name+' · progression','<div class="strength-controls"><label for="gym-metric">Metric</label><select id="gym-metric"><option value="e1rm">Estimated 1RM</option><option value="weight">Heaviest weight</option><option value="reps">Most reps</option><option value="volume">Session tonnage</option><option value="sets">Sets per session</option></select></div>'+canvas("gym-progression"),"strength-full")+
 card("Logged sets",'<div id="gym-set-table"></div><button id="gym-more">Load more sets</button>',"strength-full");
 async function draw(){const metric=document.getElementById("gym-metric").value,ret=await get("/exercises/"+encodeURIComponent(id)+"/progress",{metric});const old=document.getElementById("gym-progression");const replacement=old.cloneNode();old.replaceWith(replacement);chart("gym-progression",ret.data,{x:"date",y:"value",mode:"line",unit:metric==="weight"||metric==="e1rm"||metric==="volume"?"kg":""});}
 document.getElementById("gym-metric").onchange=()=>draw().catch(showError);await draw();
 let page=1;async function sets(){const ret=await get("/exercises/"+encodeURIComponent(id)+"/sets",{page,page_size:50});const content=dataTable(ret.data,[["Date",r=>fmtDate(r.date)],["Session",r=>link(r.session_id,"View")],["Weight (kg)",r=>fmt(r.weight_kg)],["Reps",r=>fmt(r.reps)],["e1RM (kg)",r=>fmt(r.e1rm)],["Status",r=>r.complete?(r.warmup?"Warm-up":"Complete"):"Incomplete"]]);document.getElementById("gym-set-table").insertAdjacentHTML("beforeend",content);document.getElementById("gym-more").hidden=page*50>=ret.meta.total;}
 document.getElementById("gym-more").onclick=()=>{page++;sets().catch(showError);};await sets();
}
async function history(){
 const ret=await get("/sessions",{page_size:200});root.innerHTML=card("Workout history",'<p class="muted">'+ret.meta.total+' sessions · newest first</p>'+dataTable(ret.data,[["Date",s=>fmtDate(s.date)],["Session",s=>link(s.id,s.name||"Workout")],["Duration",s=>s.duration_seconds==null?"—":fmt(s.duration_seconds/60)+" min"]]),"strength-full");
}
async function session(id){
 const ret=await get("/sessions/"+encodeURIComponent(id)),s=ret.data;
 root.innerHTML='<div class="strength-grid">'+card(esc(s.name||"Workout")+' · '+fmtDate(s.date),'<p>Duration: '+(s.duration_seconds==null?"—":fmt(s.duration_seconds/60)+" minutes")+'</p>',"strength-full")+
 s.exercises.map(e=>card(esc(e.name),'<p>'+link(e.exercise_id,"View progression","exercises")+'</p>'+dataTable(e.sets,[["Set",s=>fmt(s.ordinal)],["Load (kg)",s=>fmt(s.weight_kg)],["Reps",s=>fmt(s.reps)],["Status",s=>s.complete?(s.warmup?"Warm-up":s.drop_set?"Drop set":"Complete"):"Incomplete"],["Failure",s=>s.failure?"Yes":"No"]]),"strength-half")).join("")+'</div>';
}
async function records(){
 const ret=await get("/records");root.innerHTML=card("Estimated 1RM personal records",'<div class="strength-controls"><button id="gym-download">Export CSV</button></div>'+dataTable(ret.data,[["Date",r=>fmtDate(r.date)],["Exercise",r=>link(r.exercise_id,r.exercise,"exercises")],["Weight (kg)",r=>fmt(r.weight_kg)],["Reps",r=>fmt(r.reps)],["Estimated 1RM",r=>fmt(r.e1rm)],["Improvement",r=>fmt(r.improvement)]]),"strength-full");
 document.getElementById("gym-download").onclick=()=>csv(ret.data,["date","exercise","weight_kg","reps","e1rm","improvement"]);
}
async function imports(){
 const {data:d}=await get("/imports/status");
 root.innerHTML=card("Latest Gym Day export",'<p><strong>Discovered:</strong> '+esc(d.discovery.filename||d.discovery.error||"Unavailable")+'</p><p><strong>Last imported:</strong> '+esc(d.latest?.filename||"Never")+'</p><p><strong>Status:</strong> '+esc(d.latest?.status||"Not imported")+'</p><pre>'+esc(JSON.stringify(d.latest?.counts||{},null,2))+'</pre><p>'+esc((d.latest?.warnings||[]).join("; "))+'</p><button id="gym-refresh">Refresh from latest export</button><p id="gym-sync"></p>',"strength-full");
 document.getElementById("gym-refresh").onclick=async()=>{
  const button=document.getElementById("gym-refresh");button.disabled=true;const status=document.getElementById("gym-sync");status.textContent="Importing…";
  try{const response=await fetch(base+"/imports/refresh",{method:"POST",headers:{"Content-Type":"application/json","X-CSRFToken":document.querySelector('meta[name="csrf-token"]').content},body:"{}"});const result=await response.json();if(!response.ok)throw Error(result.error?.message||"Import failed");status.textContent="Import "+result.data.status+" · "+result.data.filename;}catch(e){status.textContent=e.message;}finally{button.disabled=false;}
 };
}
setControls();
const task=path==="/fitness/strength"?overview():path.endsWith("/exercises")?exercises():path.includes("/exercises/")?exerciseDetail(path.split("/").pop()):path.endsWith("/history")?history():path.includes("/sessions/")?session(path.split("/").pop()):path.endsWith("/records")?records():imports();
Promise.resolve(task).catch(showError);
})();