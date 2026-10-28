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
 const target=document.getElementById(id);if(!target)return;
 const rows=data.filter(x=>typeof x[field]==="number").sort((a,b)=>a.date.localeCompare(b.date));
 if(!rows.length){target.replaceWith(document.createTextNode("No observations for this metric."));return;}
 const canvas=target,info=document.getElementById(id+"-info");let selected=rows.length-1,coords=[];
 function draw(){
 const box=canvas.getBoundingClientRect(),w=box.width,h=box.height;if(w<100)return;
 const dpr=window.devicePixelRatio||1;canvas.width=w*dpr;canvas.height=h*dpr;const c=canvas.getContext("2d");c.scale(dpr,dpr);
 const left=50,right=16,top=22,bottom=40,W=w-left-right,H=h-top-bottom;
 let vals=rows.map(x=>x[field]),min=Math.min(...vals),max=Math.max(...vals),pad=Math.max((max-min)*.12,.5);min=Math.max(0,min-pad);max+=pad;
 c.font="11px system-ui";c.fillStyle=css("--text-primary")||"#002b36";c.strokeStyle=css("--chart-grid")||"#ddd";
 for(let n=0;n<5;n++){let y=top+n*H/4;c.beginPath();c.moveTo(left,y);c.lineTo(w-right,y);c.stroke();c.fillText(fmt(max-(max-min)*n/4),4,y+4);}
 const t0=Date.parse(rows[0].date+"T00:00:00Z"),t1=Date.parse(rows.at(-1).date+"T00:00:00Z");
 const xp=x=>left+(Date.parse(x.date+"T00:00:00Z")-t0)/Math.max(1,t1-t0)*W;
 const yp=x=>top+(max-x[field])/(max-min)*H;coords=rows.map(x=>({...x,px:xp(x)}));
 c.strokeStyle=css("--accent")||"#268bd2";c.fillStyle=css("--accent")||"#268bd2";c.lineWidth=2;c.beginPath();
 rows.forEach((x,i)=>{if(asBars){let bw=Math.min(25,W/rows.length*.65);c.fillRect(xp(x)-bw/2,yp(x),bw,top+H-yp(x));}else{i?c.lineTo(xp(x),yp(x)):c.moveTo(xp(x),yp(x));}});if(!asBars)c.stroke();
 c.fillStyle=css("--text-primary")||"#002b36";c.textAlign="center";for(let n=0;n<5;n++){const t=t0+(t1-t0)*n/4;c.fillText(new Date(t).toLocaleDateString("en-AU",{month:"short",year:"2-digit",timeZone:"UTC"}),left+W*n/4,h-14);}
 }
 const focus=n=>{selected=Math.max(0,Math.min(n,rows.length-1));info.textContent=rows[selected].date+": "+fmt(rows[selected][field])+" "+unit;};
 canvas.addEventListener("pointermove",e=>{let x=e.clientX-canvas.getBoundingClientRect().left;focus(coords.reduce((best,c,i)=>Math.abs(c.px-x)<Math.abs(coords[best].px-x)?i:best,0));});
 canvas.addEventListener("keydown",e=>{if(["ArrowRight","ArrowLeft","Home","End"].includes(e.key)){e.preventDefault();focus(e.key==="Home"?0:e.key==="End"?rows.length-1:selected+(e.key==="ArrowRight"?1:-1));}});
 new ResizeObserver(draw).observe(canvas);document.addEventListener("life-theme-change",draw);draw();focus(selected);
}
function chart(label,data,field,unit,bars=false){const id="bc-chart-"+series.length;series.push(id);panels.insertAdjacentHTML("beforeend",'<section class="panel"><h2>'+esc(label)+'</h2><div class="bc-chart"><canvas tabindex="0" role="img" aria-label="'+esc(label)+' by observation date" id="'+id+'"></canvas></div><p class="muted" id="'+id+'-info"></p></section>');renderGraph(id,data,field,unit,bars);}
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
 panels.replaceChildren();kpis.replaceChildren();series=[];message.textContent="";document.getElementById("composition-filters").hidden=["overview","data","projections"].includes(view);
 if(view==="data"){const s=await get("imports/status");message.textContent="Workbook: "+s.status+(s.source_filename?" · "+s.source_filename:"");kpis.innerHTML=Object.entries(s.counts).map(([k,v])=>card(k,v,"rows",s.last_import,"last import")).join("");panels.innerHTML='<div class="panel"><h2>Source health</h2><p>File available: '+s.file_available+'</p><p>Last successful import: '+esc(s.last_import||"Never")+'</p><p>'+esc((s.warnings||[]).join("; ")||"No importer warnings")+'</p></div>';table([]);return;}
 if(view==="projections"){const [weight,waist]=await Promise.all([get("projections?metric=weight&horizon_days=90"),get("projections?metric=waist&horizon_days=90")]);for(const [name,result,unit] of [["Weight",weight,"kg"],["Waist",waist,"cm"]]){message.textContent="Estimates use manual measurements only. Historical variation is not a confidence interval.";if(result.points?.length)chart(name+" · illustrative 90-day projection",result.points.map(p=>({date:p.date,[name]:p.value})),name,unit);else panels.insertAdjacentHTML("beforeend",'<div class="panel"><h2>'+name+'</h2><p>Insufficient recent observations to project.</p></div>');}table([]);return;}
 if(view==="overview"){const all=await get("overview");kpis.innerHTML=[["manual","Weight","kg"],["manual","Waist","cm"],["manual","Shoulders","cm"],["evolt","Total Body Fat Percentage","%"],["evolt","Lean Body Mass","kg"],["dexa","Tissue % Fat","%"]].map(([s,f,u])=>card(f,all[s]?.[f],u,all[s]?.date,s)).join("");const [manual,evolt]=await Promise.all([get("measurements"),get("evolt")]);chart("Manual weight",manual,"Weight","kg");chart("Waist",manual,"Waist","cm");chart("Evolt body fat",evolt,"Total Body Fat Percentage","%");chart("Evolt lean mass",evolt,"Lean Body Mass","kg");table([...manual].reverse());return;}
 const cfg=config[view],data=await get(cfg.url+params());kpiSet(data,cfg.metrics,view);
 cfg.metrics.forEach(([field,unit])=>chart(field,data,field,unit,view==="dexa"));
 if(view==="dexa"){const regions=await get("dexa/regions");chart("Regional fat mass (kg)",regions.map((r,i)=>({...r,date:r.date, "Fat_kg":r.Fat_kg})).filter(r=>!String(r.Region).endsWith("Diff.")),"Fat_kg","kg",true);table(regions);message.textContent="One DEXA scan cannot establish a longitudinal trend. Regional aggregates may overlap; do not sum these rows.";}
 else table([...data].reverse());
}
document.getElementById("bc-filter").onclick=()=>load().catch(e=>message.textContent=e.message);
document.getElementById("bc-reset").onclick=()=>{document.getElementById("bc-year").value="";document.getElementById("bc-month").value="";load().catch(e=>message.textContent=e.message);};
load().catch(e=>message.textContent="Unable to load composition data: "+e.message);
})();