(()=>{"use strict";
const root=document.querySelector(".composition");if(!root)return;
const view=root.dataset.view,base="/api/v1/fitness/body-composition",panels=document.getElementById("bc-panels"),kpis=document.getElementById("bc-kpis"),message=document.getElementById("bc-message");
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=v=>typeof v==="number"?new Intl.NumberFormat("en-AU",{maximumFractionDigits:2}).format(v):v??"—";
const css=key=>getComputedStyle(document.documentElement).getPropertyValue(key).trim();
let tableRows=[],sortKey="date",ascending=false,page=0,series=[];
const config={
 measurements:{url:"measurements",metrics:[["Weight","kg"],["Waist","cm"],["Chest","cm"],["Shoulders","cm"],["Bicep (flexed)","cm"],["Thigh","cm"],["FFMI",""],["Body Fat %","%"]]},
 evolt:{url:"evolt",metrics:[["Weight","kg"],["Total Body Fat Percentage","%"],["Lean Body Mass","kg"],["Skeletal Muscle Mass","kg"],["Body Fat Mass","kg"],["Total Body Water","kg"],["BMR","kcal"],["Visceral Fat Level","level"],["Left Arm Lean Mass","kg"],["Right Arm Lean Mass","kg"],["Left Leg Lean Mass","kg"],["Right Leg Lean Mass","kg"]]},
 dexa:{url:"dexa/scans",metrics:[["Total Mass","kg"],["Lean Mass","kg"],["Fat Mass","kg"],["Tissue % Fat","%"],["FFMI",""]]}
};
function card(label,value,unit,date,source){return '<article class="metric"><span>'+esc(label)+'</span><strong>'+fmt(value)+(value==null?"":" "+esc(unit))+'</strong><small>'+esc(source)+" · "+esc(date||"No measurement")+"</small></article>";}
async function get(url){const r=await fetch(base+"/"+url),j=await r.json();if(!r.ok)throw Error(j.error?.message||r.statusText);return j.data;}
function renderGraph(id,data,field,unit,asBars=false){
 const canvas=document.getElementById(id),info=document.getElementById(id+"-info");if(!canvas)return;
 const rows=data.filter(x=>typeof x[field]==="number"&&Number.isFinite(x[field])&&/^\d{4}-\d{2}-\d{2}$/.test(x.date)).sort((a,b)=>a.date.localeCompare(b.date));
 if(!rows.length){canvas.replaceWith(document.createTextNode("No observations for this metric."));return;}
 const day=d=>Date.parse(d+"T00:00:00Z"),msDay=86400000,last=rows.at(-1),first=rows[0];
 // Smooth historical values using the last seven OBSERVATIONS, never invented daily records.
 const average=rows.map((r,i)=>({...r,avg:rows.slice(Math.max(0,i-6),i+1).reduce((sum,v)=>sum+v[field],0)/Math.min(i+1,7)}));
 // Use up to the last 12 available observations across a 2-year history window.
 // Irregular tape measurements can be months apart; don't require five within 180 days.
 const eligible=average.filter(p=>day(last.date)-day(p.date)<=730*msDay);
 const recent=eligible.slice(-12);
 const span=recent.length>1?(day(recent.at(-1).date)-day(recent[0].date))/msDay:0;
 let future=[],slope=0,spread=0;
 if(!asBars&&recent.length>=3&&span>=30){
   const xs=recent.map(p=>(day(p.date)-day(recent[0].date))/msDay),ys=recent.map(p=>p.avg);
   const mx=xs.reduce((a,b)=>a+b,0)/xs.length,my=ys.reduce((a,b)=>a+b,0)/ys.length;
   const denom=xs.reduce((a,x)=>a+(x-mx)**2,0);
   slope=denom?xs.reduce((a,x,i)=>a+(x-mx)*(ys[i]-my),0)/denom:0;
   const bound=Math.max(.01,Math.abs(last[field])*.01)/7;
   slope=Math.max(-bound,Math.min(bound,slope));
   spread=Math.max(.01,Math.sqrt(xs.reduce((a,x,i)=>a+(ys[i]-(my+slope*(x-mx)))**2,0)/xs.length));
   const anchor=average.at(-1).avg;
   for(let delta=0;delta<=365;delta+=15){
     const futureDay=new Date(day(last.date)+delta*msDay).toISOString().slice(0,10);
     const value=Math.max(0,anchor+slope*delta),margin=spread*Math.sqrt(1+delta/30);
     future.push({date:futureDay,value,lower:Math.max(0,value-margin),upper:value+margin});
   }
   if(future.at(-1).date!==new Date(day(last.date)+365*msDay).toISOString().slice(0,10)){
     const delta=365,value=Math.max(0,anchor+slope*delta),margin=spread*Math.sqrt(1+delta/30);
     future.push({date:new Date(day(last.date)+delta*msDay).toISOString().slice(0,10),value,lower:Math.max(0,value-margin),upper:value+margin});
   }
 }
 const target=info;let selected=rows.length-1,coords=[];
 const touch=i=>{selected=Math.max(0,Math.min(i,rows.length-1));const p=rows[selected];target.textContent=p.date+" · Observed "+fmt(p[field])+" "+unit+" · 7-reading average "+fmt(average[selected].avg)+" "+unit+(future.length?" · 12-month estimate "+fmt(future.at(-1).value)+" "+unit:" · projection unavailable (requires 3 readings spanning at least 30 days within 2 years)");};
 const draw=()=>{
   const rect=canvas.getBoundingClientRect(),w=rect.width,h=rect.height;if(w<100||!h)return;
   const dpr=window.devicePixelRatio||1;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
   const c=canvas.getContext("2d");c.scale(dpr,dpr);
   const L=55,R=18,T=20,B=40,W=w-L-R,H=h-T-B,all=[...rows.map(p=>p[field]),...future.flatMap(p=>[p.lower,p.upper])];
   let lo=Math.min(...all),hi=Math.max(...all),pad=Math.max((hi-lo)*.12,.25);lo=Math.max(0,lo-pad);hi+=pad;
   const firstDay=day(first.date),endDay=future.length?day(future.at(-1).date):day(last.date);
   const x=d=>L+(day(d)-firstDay)/Math.max(1,endDay-firstDay)*W;
   const y=value=>T+(hi-value)/Math.max(.001,hi-lo)*H;
   c.font="11px system-ui";c.fillStyle=css("--text-primary")||"#002b36";c.strokeStyle=css("--chart-grid")||"#ddd";
   for(let n=0;n<=4;n++){const yy=T+n*H/4;c.beginPath();c.moveTo(L,yy);c.lineTo(w-R,yy);c.stroke();c.fillText(fmt(hi-(hi-lo)*n/4),3,yy+4);}
   if(future.length){
     const split=x(last.date);c.fillStyle="rgba(38,139,210,.06)";c.fillRect(split,T,w-R-split,H);
     c.beginPath();future.forEach((p,i)=>i?c.lineTo(x(p.date),y(p.upper)):c.moveTo(x(p.date),y(p.upper)));
     [...future].reverse().forEach(p=>c.lineTo(x(p.date),y(p.lower)));c.closePath();c.fillStyle="rgba(38,139,210,.15)";c.fill();
     c.beginPath();c.strokeStyle=css("--solarized-orange")||"#cb4b16";c.setLineDash([6,5]);c.lineWidth=2;
     future.forEach((p,i)=>i?c.lineTo(x(p.date),y(p.value)):c.moveTo(x(p.date),y(p.value)));c.stroke();c.setLineDash([]);
   }
   const drawLine=(arr,key,color,width=2,dashes=[])=>{c.beginPath();c.strokeStyle=color;c.lineWidth=width;c.setLineDash(dashes);arr.forEach((p,i)=>i?c.lineTo(x(p.date),y(p[key])):c.moveTo(x(p.date),y(p[key])));c.stroke();c.setLineDash([]);};
   if(asBars){rows.forEach(p=>{const width=Math.min(22,W/rows.length*.65);c.fillStyle=css("--accent")||"#268bd2";c.fillRect(x(p.date)-width/2,y(p[field]),width,T+H-y(p[field]));});}
   else {drawLine(rows,field,css("--accent")||"#268bd2");drawLine(average,"avg",css("--solarized-orange")||"#cb4b16",1.6,[3,3]);}
   c.fillStyle=css("--text-primary")||"#002b36";c.textAlign="center";
   for(let n=0;n<=4;n++){const stamp=firstDay+(endDay-firstDay)*n/4;const label=new Date(stamp).toLocaleDateString("en-AU",{month:"short",year:"2-digit",timeZone:"UTC"});c.fillText(label,L+W*n/4,h-12);}
   coords=rows.map(r=>x(r.date));
 };
 canvas.addEventListener("pointermove",ev=>{if(!coords.length)return;const px=ev.clientX-canvas.getBoundingClientRect().left;touch(coords.reduce((best,v,i)=>Math.abs(v-px)<Math.abs(coords[best]-px)?i:best,0));});
 canvas.addEventListener("keydown",ev=>{if(["ArrowRight","ArrowLeft","Home","End"].includes(ev.key)){ev.preventDefault();touch(ev.key==="Home"?0:ev.key==="End"?rows.length-1:selected+(ev.key==="ArrowLeft"?-1:1));}});
 new ResizeObserver(draw).observe(canvas);document.addEventListener("life-theme-change",draw);draw();touch(selected);
}
function chart(label,data,field,unit,bars=false){const id="bc-chart-"+series.length;series.push(id);panels.insertAdjacentHTML("beforeend",'<section class="panel"><h2>'+esc(label)+'</h2><div class="bc-chart"><canvas tabindex="0" role="img" aria-label="'+esc(label)+' by observation date" id="'+id+'"></canvas></div><p class="muted bc-chart-legend"><span>Blue solid: measured</span> · <span>Orange dotted: 7-reading average</span> · <span>Orange dashed: 12-month estimate</span> · <span>Shading: descriptive variation</span></p><p class="muted" id="'+id+'-info"></p></section>');renderGraph(id,data,field,unit,bars);}
function regionBars(rows,field,label,unit){
 const usable=rows.filter(r=>typeof r[field]==="number"&&!String(r.Region||"").endsWith("Diff."));
 if(!usable.length)return;
 const id="bc-regions-"+series.length;series.push(id);
 panels.insertAdjacentHTML("beforeend",'<section class="panel"><h2>'+esc(label)+'</h2><div class="bc-region-bars" id="'+id+'"></div><p class="muted">Individual and aggregate regions can overlap. Do not sum bars.</p></section>');
 const max=Math.max(...usable.map(r=>r[field]))||1,container=document.getElementById(id);
 usable.forEach(r=>{const item=document.createElement("div");item.className="bc-region-row";const name=document.createElement("span");name.textContent=r.Region;const rail=document.createElement("div");rail.className="bc-region-track";const bar=document.createElement("div");bar.className="bc-region-fill";bar.style.width=Math.max(0,100*r[field]/max)+"%";rail.appendChild(bar);const amount=document.createElement("strong");amount.textContent=fmt(r[field])+" "+unit;item.append(name,rail,amount);container.append(item);});
}
function exportCsv(rows){if(!rows.length)return;const keys=Object.keys(rows[0]);const quote=v=>'"'+String(v??"").replaceAll('"','""').replace(/^[=+@-]/,"'")+'"';const csv=[keys.join(","),...rows.map(r=>keys.map(k=>quote(r[k])).join(","))].join("\r\n");const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([csv],{type:"text/csv"}));a.download="body-composition.csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function table(rows){
 tableRows=rows;page=0;renderTable();
}
function renderTable(){
 const table=document.getElementById("bc-table"),keys=tableRows.length?Object.keys(tableRows[0]):[];
 table.querySelector("thead").innerHTML="<tr>"+keys.map(k=>'<th><button type="button" data-sort="'+esc(k)+'">'+esc(k)+'</button></th>').join("")+"</tr>";
 const sorted=[...tableRows].sort((a,b)=>{let x=a[sortKey],y=b[sortKey];const cmp=typeof x==="number"&&typeof y==="number"?x-y:String(x??"").localeCompare(String(y??""));return ascending?cmp:-cmp;});
 table.querySelector("tbody").innerHTML=sorted.slice(page*25,(page+1)*25).map(r=>"<tr>"+keys.map(k=>"<td>"+esc(fmt(r[k]))+"</td>").join("")+"</tr>").join("")||'<tr><td>No records available.</td></tr>';
 table.querySelectorAll("[data-sort]").forEach(b=>b.onclick=()=>{ascending=sortKey===b.dataset.sort?!ascending:true;sortKey=b.dataset.sort;page=0;renderTable();});
 document.getElementById("bc-page").textContent=(page+1)+" / "+Math.max(1,Math.ceil(sorted.length/25));
 document.getElementById("bc-prev").disabled=page===0;document.getElementById("bc-next").disabled=(page+1)*25>=sorted.length;
}
document.getElementById("bc-prev").onclick=()=>{page--;renderTable();};
document.getElementById("bc-next").onclick=()=>{page++;renderTable();};
document.getElementById("bc-download").onclick=()=>exportCsv(tableRows);
function kpiSet(data,fields,source){kpis.innerHTML=fields.map(([field,unit])=>{const last=[...data].reverse().find(x=>x[field]!=null);return card(field,last?.[field],unit,last?.date,source);}).join("");}
function params(){const y=document.getElementById("bc-year").value,m=document.getElementById("bc-month").value;return y?"?year="+y+(m?"&month="+m:""):"";}
async function load(){
 panels.replaceChildren();kpis.replaceChildren();series=[];message.textContent="";document.getElementById("composition-filters").hidden=["overview","data"].includes(view);
 if(view==="data"){const s=await get("imports/status");message.textContent="Workbook: "+s.status+(s.source_filename?" · "+s.source_filename:"");kpis.innerHTML=Object.entries(s.counts).map(([k,v])=>card(k,v,"rows",s.last_import,"last import")).join("");panels.innerHTML='<div class="panel"><h2>Source health</h2><p>File available: '+s.file_available+'</p><p>Last successful import: '+esc(s.last_import||"Never")+'</p><p>'+esc((s.warnings||[]).join("; ")||"No importer warnings")+'</p></div>';table([]);return;}
 if(view==="overview"){const all=await get("overview");kpis.innerHTML=[["manual","Weight","kg"],["manual","Waist","cm"],["manual","Shoulders","cm"],["evolt","Total Body Fat Percentage","%"],["evolt","Lean Body Mass","kg"],["dexa","Tissue % Fat","%"]].map(([s,f,u])=>card(f,all[s]?.[f],u,all[s]?.date,s)).join("");const [manual,evolt]=await Promise.all([get("measurements"),get("evolt")]);chart("Manual weight",manual,"Weight","kg");chart("Waist",manual,"Waist","cm");chart("Evolt body fat",evolt,"Total Body Fat Percentage","%");chart("Evolt lean mass",evolt,"Lean Body Mass","kg");table([...manual].reverse());return;}
 const cfg=config[view],data=await get(cfg.url+params());kpiSet(data,cfg.metrics,view);
 cfg.metrics.forEach(([field,unit])=>chart(field,data,field,unit));
 if(view==="dexa"){const regions=await get("dexa/regions");regionBars(regions,"Fat_kg","Regional fat mass","kg");regionBars(regions,"Lean_kg","Regional lean mass","kg");regionBars(regions,"Tissue_Fat_pct","Regional tissue fat","%");table(regions);message.textContent="DEXA trends and six-month estimates require at least five measurements spanning 30 days. Regional aggregates may overlap; do not sum these rows.";}
 else table([...data].reverse());
}
document.getElementById("bc-filter").onclick=()=>load().catch(e=>message.textContent=e.message);
document.getElementById("bc-reset").onclick=()=>{document.getElementById("bc-year").value="";document.getElementById("bc-month").value="";load().catch(e=>message.textContent=e.message);};
load().catch(e=>message.textContent="Unable to load composition data: "+e.message);
})();