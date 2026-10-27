(() => {
 const csrf=document.querySelector('meta[name="csrf-token"]')?.content||'';
 const request=async(path,options={})=>{
   const response=await fetch(path,{...options,headers:{'X-CSRFToken':csrf,...(options.headers||{})}});
   const data=await response.json();
   if(!response.ok)throw Error(data.error?.message||'Request failed');
   return data;
 };
 const aud=(v)=>v==null?'Unavailable':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(v));
 const svgNS='http://www.w3.org/2000/svg';
 function drawLine(target,points){
   if(!target)return;
   target.replaceChildren();
   if(points.length<2){target.textContent=points.length?'Only one historical snapshot available.':'No historical data to chart.';return;}
   const w=850,h=240,p=42,values=points.map(x=>Number(x.reported)),min=Math.min(...values),max=Math.max(...values),span=max-min||1;
   const el=(tag,attrs)=>{const e=document.createElementNS(svgNS,tag);Object.entries(attrs).forEach(([k,v])=>e.setAttribute(k,v));return e;};
   const svg=el('svg',{viewBox:`0 0 ${w} ${h}`,preserveAspectRatio:'none','aria-hidden':'true'});
   for(let i=0;i<=4;i++){const y=p+(h-p*2)*i/4;
     svg.appendChild(el('line',{x1:p,y1:y,x2:w-p,y2:y,stroke:'var(--chart-grid)'}));
     const label=el('text',{x:p-7,y:y+4,'text-anchor':'end',fill:'var(--text-muted)','font-size':'11'});
     label.textContent=aud(max-(max-min)*i/4);svg.appendChild(label);}
   const path=points.map((pt,i)=>`${i?'L':'M'} ${p+(w-2*p)*i/(points.length-1)} ${h-p-(Number(pt.reported)-min)/span*(h-2*p)}`).join(' ');
   svg.appendChild(el('path',{d:path,fill:'none',stroke:'var(--accent)','stroke-width':'2.8','vector-effect':'non-scaling-stroke'}));
   target.appendChild(svg);
   target.title=`${points[0].as_of}: ${aud(points[0].reported)} → ${points.at(-1).as_of}: ${aud(points.at(-1).reported)}`;
 }
 function drawBars(target,points){
   if(!target)return;target.replaceChildren();
   if(!points.length){target.textContent='No classified transaction data available.';return;}
   const items=points.slice(-12),max=Math.max(1,...items.flatMap(x=>[Math.abs(Number(x.income)),Math.abs(Number(x.spending))]));
   const chart=document.createElement('div');chart.className='bars';chart.style.cssText='display:flex;align-items:flex-end;height:100%;gap:10px';
   items.forEach(item=>{const group=document.createElement('div');group.style.cssText='flex:1;min-width:0;display:flex;flex-direction:column;justify-content:flex-end;height:100%;gap:2px';
    const bars=document.createElement('div');bars.style.cssText='display:flex;gap:3px;align-items:flex-end;height:85%';
    [['spending','var(--solarized-orange)'],['income','var(--accent)']].forEach(([field,color])=>{
      const bar=document.createElement('div');bar.style.cssText=`width:50%;height:${Math.max(1,Math.abs(Number(item[field]))/max*100)}%;background:${color};border-radius:3px 3px 0 0`;
      bar.title=`${item.label} ${field}: ${aud(item[field])}`;bars.appendChild(bar);});
    const label=document.createElement('span');label.style.cssText='font-size:10px;text-align:center;overflow:hidden;white-space:nowrap';
    label.textContent=item.label;group.append(bars,label);chart.appendChild(group);});
   target.appendChild(chart);
 }
 const net=document.getElementById('networth-chart'),cash=document.getElementById('spending-chart');
 let history=[];
 if(net){request('/api/v1/finance/net-worth').then(x=>{history=x.data.filter(v=>v.reported!==null);drawLine(net,history);}).catch(e=>net.textContent=e.message);
   document.querySelectorAll('[data-range]').forEach(b=>b.addEventListener('click',()=>{
     document.querySelectorAll('[data-range]').forEach(x=>x.classList.toggle('selected',x===b));
     const months={'1m':1,'3m':3,'6m':6,'1y':12}[b.dataset.range];
     if(!months)return drawLine(net,history);
     const start=new Date();start.setMonth(start.getMonth()-months);
     drawLine(net,history.filter(x=>new Date(x.as_of)>=start));}));}
 if(cash)request('/api/v1/finance/spending').then(x=>drawBars(cash,x.data)).catch(e=>cash.textContent=e.message);
 document.addEventListener('life-theme-change',()=>{if(net)drawLine(net,history);});
 const filters=document.getElementById('transaction-filters');
 if(filters){let page=1,total=1;
   const load=async()=>{const values=new FormData(filters),params=new URLSearchParams();
    for(const [key,value] of values.entries())if(value)params.set(key,value);
    params.set('page',page);const result=await request('/api/v1/finance/transactions?'+params);
    total=result.pages;const tbody=document.getElementById('transaction-rows');tbody.replaceChildren();
    for(const item of result.data){const tr=document.createElement('tr');
      [item.date,item.merchant||'',item.description||'',aud(item.amount),String(item.category_id||'')].forEach(value=>{
        const td=document.createElement('td');td.textContent=value;tr.appendChild(td);});tbody.appendChild(tr);}
    if(!result.data.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=5;td.textContent='No matching transactions';tr.appendChild(td);tbody.appendChild(tr);}
    document.getElementById('tx-page').textContent=`Page ${page} of ${total||1} · ${result.total} records`;
    document.getElementById('tx-prev').disabled=page<=1;document.getElementById('tx-next').disabled=page>=total;};
   filters.addEventListener('submit',e=>{e.preventDefault();page=1;load().catch(alert);});
   document.getElementById('tx-prev').addEventListener('click',()=>{page--;load().catch(alert);});
   document.getElementById('tx-next').addEventListener('click',()=>{page++;load().catch(alert);});load().catch(alert);
 }
 const mortgage=document.getElementById('mortgage-form');
 if(mortgage)mortgage.addEventListener('submit',async e=>{e.preventDefault();const vals=Object.fromEntries(new FormData(mortgage));
  const output=document.getElementById('mortgage-result');
  try{const result=await request('/api/v1/finance/mortgage/scenarios',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(vals)});
    output.textContent=result.data.paid_off?`Estimated payoff: ${result.data.months} months. Cumulative interest: ${aud(result.data.total_interest)}.`:`Not paid off within 50 years. Remaining principal: ${aud(result.data.remaining_principal)}.`;
  }catch(err){output.textContent=err.message;}});
 const imports=document.getElementById('import-form');
 if(imports){const execute=async(commit)=>{const output=document.getElementById('import-result');output.textContent='Validating workbook…';
   try{const data=await request(commit?'/api/v1/imports/finance':'/api/v1/imports/finance/preview',{method:'POST',body:new FormData(imports)});
    output.textContent=JSON.stringify(data.data,null,2);if(commit)location.reload();}catch(err){output.textContent=err.message;}};
  document.getElementById('preview-import').addEventListener('click',()=>execute(false));
  document.getElementById('commit-import').addEventListener('click',()=>execute(true));}
})();