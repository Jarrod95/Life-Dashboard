(() => {
"use strict";
const root=document.querySelector(".mfp");if(!root)return;
const food=root.dataset.view==="food",content=document.getElementById("mfp-content"),error=document.getElementById("mfp-error");
const p=new URLSearchParams(location.search),form=document.getElementById("mfp-filter");
const number=n=>n==null?"—":new Intl.NumberFormat("en-AU",{maximumFractionDigits:1}).format(n);
const html=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const day=s=>s?new Date(s+"T12:00:00Z").toLocaleDateString("en-AU",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"}):"—";
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const box=(title,body,cls="")=>'<section class="mfp-card '+cls+'"><h2>'+html(title)+'</h2>'+body+'</section>';
const metric=(name,value,unit="")=>'<article class="mfp-card mfp-kpi"><small>'+html(name)+'</small><strong>'+number(value)+'</strong><small>'+html(unit)+'</small></article>';
const canvas=id=>'<canvas id="'+id+'" role="img" tabindex="0" aria-label="'+html(id)+' interactive history chart"></canvas><p class="mfp-hint" id="'+id+'-hint">Hover or use arrow keys to inspect data.</p>';
const table=(id,rows,columns)=>'<div class="mfp-table-wrap"><table id="'+id+'"><thead><tr>'+columns.map((c,i)=>'<th><button type="button" data-sort="'+i+'">'+html(c[0])+'</button></th>').join("")+'</tr></thead><tbody></tbody></table></div>';
function drawTable(id,rows,columns){
 const table=document.getElementById(id),body=table.querySelector("tbody");let active=0,asc=false;
 const render=()=>{
  body.replaceChildren();
  const data=[...rows].sort((a,b)=>{const x=columns[active][1](a),y=columns[active][1](b);const cmp=typeof x==="number"&&typeof y==="number"?x-y:String(x??"").localeCompare(String(y??""));return asc?cmp:-cmp;});
  const fragment=document.createDocumentFragment();
  data.forEach(r=>{const tr=document.createElement("tr");columns.forEach(c=>{const td=document.createElement("td");const value=c[1](r);td.textContent=c[2]?c[2](value):value==null?"—":String(value);tr.appendChild(td);});fragment.appendChild(tr);});body.appendChild(fragment);
 };
 table.querySelectorAll("[data-sort]").forEach(b=>b.onclick=()=>{const i=Number(b.dataset.sort);asc=active===i?!asc:true;active=i;render();});render();
}
function plot(id,series,{x="date",y="value",secondary=null,unit="",mode="line",goal=null}={}){
 const canvasEl=document.getElementById(id),hint=document.getElementById(id+"-hint");if(!canvasEl)return;let selected=0,points=[];
 const valid=series.filter(r=>Number.isFinite(Number(r[y]))&&r[y]!=null);
 const draw=()=>{
  const rect=canvasEl.getBoundingClientRect(),w=rect.width,h=rect.height;if(!w||!h)return;
  const dpr=devicePixelRatio||1;canvasEl.width=Math.round(w*dpr);canvasEl.height=Math.round(h*dpr);
  const c=canvasEl.getContext("2d");c.scale(dpr,dpr);c.clearRect(0,0,w,h);
  if(!valid.length){c.fillStyle=css("--text-primary");c.fillText("No logged data in this period",18,35);return;}
  const left=56,right=18,top=18,bottom=42,iw=w-left-right,ih=h-top-bottom;
  const values=valid.flatMap(r=>[Number(r[y]),...(secondary&&r[secondary]!=null?[Number(r[secondary])]:[])]);if(goal!=null&&Number.isFinite(goal))values.push(goal);
  let min=Math.min(...values),max=Math.max(...values);const pad=Math.max((max-min)*.12,Math.abs(max)*.025,.25);min=Math.max(0,min-pad);max+=pad;
  c.strokeStyle=css("--chart-grid");c.fillStyle=css("--text-primary");c.font="11px system-ui";
  for(let i=0;i<=4;i++){const yy=top+ih*i/4,v=max-(max-min)*i/4;c.beginPath();c.moveTo(left,yy);c.lineTo(w-right,yy);c.stroke();c.fillText(number(v),4,yy+3);}
  const pointsFor=field=>valid.map((r,i)=>({x:left+(i+.5)*iw/valid.length,y:top+ih*(max-Number(r[field]??r[y]))/(max-min),r}));
  const renderLine=(field,color,dashed=false)=>{
    const pts=pointsFor(field).filter(t=>t.r[field]!=null);
    c.beginPath();c.strokeStyle=css(color);c.lineWidth=2;c.setLineDash(dashed?[5,5]:[]);
    pts.forEach((pt,i)=>i?c.lineTo(pt.x,pt.y):c.moveTo(pt.x,pt.y));c.stroke();c.setLineDash([]);
    if(pts.length<120)pts.forEach(pt=>{c.beginPath();c.arc(pt.x,pt.y,2.3,0,Math.PI*2);c.fillStyle=css(color);c.fill();});
  };
  points=pointsFor(y);
  if(mode==="bar"){const bar=Math.max(1,Math.min(24,iw/valid.length*.75));points.forEach(pt=>{c.fillStyle=css("--accent");c.fillRect(pt.x-bar/2,pt.y,bar,top+ih-pt.y);});}
  else{renderLine(y,"--accent");if(secondary)renderLine(secondary,"--solarized-orange",true);}
  if(goal!=null&&Number.isFinite(goal)){const yy=top+ih*(max-goal)/(max-min);c.beginPath();c.strokeStyle=css("--solarized-orange")||"#cb4b16";c.setLineDash([6,4]);c.moveTo(left,yy);c.lineTo(w-right,yy);c.stroke();c.setLineDash([]);c.fillStyle=css("--text-primary")||"#002b36";c.textAlign="right";c.fillText("Goal "+number(goal)+" "+unit,w-right-3,Math.max(11,yy-5));}
  c.textAlign="center";const step=Math.max(1,Math.ceil(points.length/7));points.forEach((pt,i)=>{if(i%step===0)c.fillText(String(pt.r[x]).slice(-7),pt.x,h-15);});
 };
 const focus=i=>{if(!points.length)return;selected=Math.max(0,Math.min(i,points.length-1));const r=points[selected].r;hint.textContent=r[x]+" · "+number(r[y])+" "+unit+(secondary&&r[secondary]!=null?" · 7-day average: "+number(r[secondary]):"");};
 canvasEl.addEventListener("pointermove",ev=>{if(!points.length)return;const px=ev.clientX-canvasEl.getBoundingClientRect().left;focus(points.reduce((best,pt,i)=>Math.abs(pt.x-px)<Math.abs(points[best].x-px)?i:best,0));});
 canvasEl.addEventListener("keydown",ev=>{if(["ArrowRight","ArrowLeft","Home","End"].includes(ev.key)){ev.preventDefault();focus(ev.key==="Home"?0:ev.key==="End"?points.length-1:selected+(ev.key==="ArrowLeft"?-1:1));}});
 canvasEl.addEventListener("focus",()=>focus(selected));
 new ResizeObserver(draw).observe(canvasEl);document.addEventListener("life-theme-change",draw);draw();
}
for(const k of ["year","month","from","to"]){if(p.has(k))form.elements.namedItem(k).value=p.get(k);}
form.onsubmit=e=>{e.preventDefault();const q=new URLSearchParams();for(const k of ["year","month","from","to"]){const v=form.elements.namedItem(k).value;if(v)q.set(k,v);}location.search=q.toString();};
document.getElementById("mfp-clear").onclick=()=>location.href=location.pathname;
async function load(path,params={}){const q=new URLSearchParams(p);for(const [k,v] of Object.entries(params))q.set(k,v);const r=await fetch("/api/v1/fitness/mfp/"+path+"?"+q);const result=await r.json();if(!r.ok)throw Error(result.error?.message||"Data unavailable");return result;}
function weightProjection(id,history,projection){
 const el=document.getElementById(id),hint=document.getElementById(id+"-hint");
 if(!el)return;
 const measured=history.filter(r=>r.weight_kg!=null);
 const future=(projection?.points||[]);
 if(!measured.length)return;
 let points=[],selected=0;
 const redraw=()=>{
  const rect=el.getBoundingClientRect(),w=rect.width,h=rect.height;if(!w||!h)return;
  const scale=devicePixelRatio||1;el.width=Math.round(w*scale);el.height=Math.round(h*scale);
  const ctx=el.getContext("2d");ctx.scale(scale,scale);ctx.clearRect(0,0,w,h);
  const combined=[...measured.map(r=>({...r,kind:"Measured"})),...future.slice(1).map(r=>({...r,kind:"Projected"}))];
  const allValues=combined.flatMap(r=>[r.weight_kg,...(r.lower_kg!=null?[r.lower_kg,r.upper_kg]:[])]);
  const lo=Math.max(0,Math.min(...allValues)-1),hi=Math.max(...allValues)+1;
  const l=57,r=18,t=18,b=39,iw=w-l-r,ih=h-t-b;
  const start=new Date(combined[0].date+"T00:00:00Z").getTime(),end=new Date(combined.at(-1).date+"T00:00:00Z").getTime();
  const xpos=d=>l+(new Date(d+"T00:00:00Z").getTime()-start)/Math.max(1,end-start)*iw;
  const ypos=v=>t+(hi-v)/(hi-lo)*ih;
  const line=(items,field,color,dash=[])=>{const filtered=items.filter(x=>x[field]!=null);ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2;ctx.setLineDash(dash);filtered.forEach((v,i)=>i?ctx.lineTo(xpos(v.date),ypos(v[field])):ctx.moveTo(xpos(v.date),ypos(v[field])));ctx.stroke();ctx.setLineDash([]);};
  ctx.font="11px system-ui";ctx.strokeStyle=css("--chart-grid");ctx.fillStyle=css("--text-muted");
  for(let i=0;i<=4;i++){const yy=t+ih*i/4;ctx.beginPath();ctx.moveTo(l,yy);ctx.lineTo(w-r,yy);ctx.stroke();ctx.fillText(number(hi-(hi-lo)*i/4),5,yy+4);}
  const split=xpos(measured.at(-1).date);
  if(future.length){ctx.fillStyle="rgba(100,120,130,.065)";ctx.fillRect(split,t,w-r-split,ih);ctx.strokeStyle=css("--text-muted");ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(split,t);ctx.lineTo(split,t+ih);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=css("--text-muted");ctx.fillText("Projection",Math.min(split+8,w-85),t+12);}
  if(future.length>1){ctx.beginPath();future.forEach((v,i)=>i?ctx.lineTo(xpos(v.date),ypos(v.upper_kg)):ctx.moveTo(xpos(v.date),ypos(v.upper_kg)));[...future].reverse().forEach(v=>ctx.lineTo(xpos(v.date),ypos(v.lower_kg)));ctx.closePath();ctx.fillStyle="rgba(38,139,210,.13)";ctx.fill();}
  line(measured,"weight_kg",css("--accent")||"#268bd2");
  line(measured,"rolling_7",css("--solarized-orange")||"#cb4b16",[5,4]);
  if(future.length)line(future,"weight_kg",css("--accent")||"#268bd2",[7,5]);
  ctx.textAlign="center";const labels=6;
  for(let i=0;i<=labels;i++){const stamp=start+(end-start)*i/labels;ctx.fillStyle=css("--text-muted");ctx.fillText(new Date(stamp).toLocaleDateString("en-AU",{day:"numeric",month:"short",timeZone:"UTC"}),l+iw*i/labels,h-13);}
  points=combined.map(v=>({...v,x:xpos(v.date)}));
 };
 const focus=i=>{if(!points.length)return;selected=Math.max(0,Math.min(i,points.length-1));const d=points[selected];hint.textContent=d.date+" · "+d.kind+" "+number(d.weight_kg)+" kg"+(d.lower_kg!=null?" · illustrative band "+number(d.lower_kg)+"–"+number(d.upper_kg)+" kg":"");};
 el.addEventListener("pointermove",e=>{const x=e.clientX-el.getBoundingClientRect().left;focus(points.reduce((best,v,i)=>Math.abs(v.x-x)<Math.abs(points[best]?.x-x)?i:best,0));});
 el.addEventListener("keydown",e=>{if(["ArrowLeft","ArrowRight","Home","End"].includes(e.key)){e.preventDefault();focus(e.key==="Home"?0:e.key==="End"?points.length-1:selected+(e.key==="ArrowRight"?1:-1));}});
 new ResizeObserver(redraw).observe(el);document.addEventListener("life-theme-change",redraw);redraw();
}
async function weightPage(){
 const {data:d}=await load("weight");const s=d.summary;
 content.innerHTML='<div class="mfp-grid">'+metric("Latest weight",s.latest_kg,"kg")+metric("Change in range",s.change_kg,"kg")+metric("Lowest",s.min_kg,"kg")+metric("Average",s.average_kg,"kg")+
 box("Weight history & 3-month projection",canvas("mfp-weight") + '<p class="mfp-hint">Solid blue: measured · orange dashed: rolling average · blue dashed: estimated trajectory · shaded area: illustrative variation. Forecast is not a guaranteed outcome.</p>',"mfp-wide")+box("Seven-day weight trend",canvas("mfp-rolling"))+
 box("Monthly average weight",canvas("mfp-monthly"))+
 box("Monthly weight summary",table("mfp-month-table",d.monthly,[]),"mfp-wide")+
 box("Weight measurements",'<div class="mfp-toolbar"><button id="mfp-weight-export">Export filtered CSV</button></div>'+table("mfp-weight-table",d.history,[]),"mfp-wide")+'</div>';
 weightProjection("mfp-weight",d.history,d.projection);
 plot("mfp-rolling",d.history,{y:"rolling_7",unit:"kg"});
 plot("mfp-monthly",d.monthly,{x:"month",y:"average_kg",unit:"kg",mode:"bar"});
 const columns=[["Month",r=>r.month],["Average (kg)",r=>r.average_kg,number],["Lowest (kg)",r=>r.min_kg,number],["Highest (kg)",r=>r.max_kg,number]];
 drawTable("mfp-month-table",d.monthly,columns);
 drawTable("mfp-weight-table",d.history,[["Date",r=>r.date,day],["Weight (kg)",r=>r.weight_kg,number],["7-day average",r=>r.rolling_7,number]]);
 document.getElementById("mfp-weight-export").onclick=()=>exportCsv(d.history,["date","weight_kg","rolling_7"]);
}
function exportCsv(rows,cols){const escape=v=>'"'+String(v??"").replaceAll('"','""').replace(/^[=+@-]/,"'")+'"';const csv=[cols.join(","),...rows.map(r=>cols.map(c=>escape(r[c])).join(","))].join("\r\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="mfp-filtered.csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),500);}
async function foodPage(){
 let page=1;const initial=await load("food");const d=initial.data,s=d.summary;
 const goals=d.goals;
 content.innerHTML='<div class="mfp-grid">'+metric("Days with logged food",s.logged_days)+metric("Average calories",s.avg_calories,"kcal/day")+metric("Average protein",s.avg_protein_g,"g/day")+metric("Food entries",s.total_entries)+
 box("Daily calorie intake",canvas("mfp-calories"),"mfp-wide")+
 box("Daily protein",canvas("mfp-protein"))+box("Daily carbohydrate intake",canvas("mfp-carbs"))+
 box("Daily fat intake",canvas("mfp-fat"))+box("Calories by meal",canvas("mfp-meals"))+
 box("Daily nutrition totals",table("mfp-daily",d.daily,[]),"mfp-wide")+
 box("Most frequently logged foods",table("mfp-top",d.top_foods,[]),"mfp-wide")+
 box("Food diary",'<div class="mfp-toolbar"><input type="search" id="mfp-search" placeholder="Search foods" aria-label="Search food names"><select id="mfp-meal"><option value="">All meals</option><option>Breakfast</option><option>Lunch</option><option>Dinner</option><option>Snacks</option></select><button id="mfp-export">Export displayed entries</button></div><div id="mfp-food-table"></div><div class="mfp-toolbar"><button id="mfp-prev">Previous</button><span id="mfp-page"></span><button id="mfp-next">Next</button></div>',"mfp-wide")+'</div>';
 plot("mfp-calories",d.daily.filter(r=>r.food_entries>0),{y:"calories",unit:"kcal",mode:"bar",goal:goals.calories});
 plot("mfp-protein",d.daily.filter(r=>r.food_entries>0),{y:"protein_g",unit:"g",mode:"bar",goal:goals.protein_g});
 plot("mfp-carbs",d.daily.filter(r=>r.food_entries>0),{y:"carbs_g",unit:"g",mode:"bar",goal:goals.carbs_g});
 plot("mfp-fat",d.daily.filter(r=>r.food_entries>0),{y:"fat_g",unit:"g",mode:"bar",goal:goals.fat_g});
 plot("mfp-meals",d.meals.map(r=>({...r,date:r.meal})),{y:"calories",unit:"kcal",mode:"bar"});
 drawTable("mfp-daily",d.daily,[["Date",r=>r.date,day],["Calories",r=>r.calories,number],["Goal",r=>r.goal_calories,number],["Protein (g)",r=>r.protein_g,number],["Carbs (g)",r=>r.carbs_g,number],["Fat (g)",r=>r.fat_g,number],["Food entries",r=>r.food_entries,number]]);
 drawTable("mfp-top",d.top_foods,[["Food",r=>r.food],["Times logged",r=>r.count],["Total kcal",r=>r.calories,number],["Total protein (g)",r=>r.protein_g,number]]);
 let shown=[];
 async function refresh(){
  const ret=await load("food",{page,page_size:100,q:document.getElementById("mfp-search").value,meal:document.getElementById("mfp-meal").value});shown=ret.data.entries;
  document.getElementById("mfp-food-table").innerHTML=table("mfp-foods",shown,[]);
  drawTable("mfp-foods",shown,[["Date",r=>r.date,day],["Meal",r=>r.meal],["Food",r=>r.food],["Calories",r=>r.calories,number],["Protein (g)",r=>r.protein_g,number],["Carbs (g)",r=>r.carbs_g,number],["Fat (g)",r=>r.fat_g,number],["Sodium (mg)",r=>r.sodium_mg,number]]);
  document.getElementById("mfp-page").textContent="Page "+page+" · "+ret.meta.total+" entries";document.getElementById("mfp-prev").disabled=page<=1;document.getElementById("mfp-next").disabled=page*100>=ret.meta.total;
 }
 let timer;document.getElementById("mfp-search").oninput=()=>{clearTimeout(timer);timer=setTimeout(()=>{page=1;refresh().catch(fail);},250);};document.getElementById("mfp-meal").onchange=()=>{page=1;refresh().catch(fail);};
 document.getElementById("mfp-prev").onclick=()=>{page--;refresh().catch(fail);};
 document.getElementById("mfp-next").onclick=()=>{page++;refresh().catch(fail);};
 document.getElementById("mfp-export").onclick=()=>exportCsv(shown,["date","meal","food","calories","protein_g","carbs_g","fat_g","sodium_mg","sugar_g"]);
 await refresh();
}
function fail(e){error.hidden=false;error.textContent=e.message||String(e);}
(food?foodPage():weightPage()).catch(fail);
})();
