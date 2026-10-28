(() => {
 const csrf=document.querySelector('meta[name="csrf-token"]')?.content||'';
 const request=async(path,options={})=>{
   const response=await fetch(path,{...options,headers:{'X-CSRFToken':csrf,...(options.headers||{})}});
   const data=await response.json();
   if(!response.ok)throw Error(data.error?.message||'Request failed');
   return data;
 };
 const aud=(v)=>v==null?'Unavailable':new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(v));
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

 const mortgageChart=document.getElementById('mortgage-history-chart');
 if(mortgageChart)(async()=>{
   const status=document.getElementById('mortgage-status'), kpis=document.getElementById('mortgage-kpis');
   try{
     const result=await request('/api/v1/finance/mortgage'),data=result.data;
     if(data.status!=='ok'){status.textContent=data.message||'Mortgage data unavailable';return;}
     status.textContent='Latest source observation: '+data.indicators.as_of;
     const fields=[['Mortgage outstanding','principal',aud],['Interest rate','interest_rate',v=>(Number(v)*100).toFixed(2)+'%'],
       ['Months remaining','months_remaining',v=>v],['Offset balance','offset',aud],
       ['Next estimated monthly interest','next_month_interest_estimate',aud],
       ['Estimated monthly offset saving','monthly_offset_interest_saving',aud],
       ['Estimated daily offset saving','daily_offset_interest_saving',aud],
       ['Average monthly reduction','average_monthly_principal_reduction',aud]];
     for(const [label,key,format] of fields){
       const value=data.indicators[key],card=document.createElement('article');card.className='metric';
       const caption=document.createElement('span');caption.textContent=label;
       const amount=document.createElement('strong');amount.textContent=value==null?'Unavailable':format(value);
       card.append(caption,amount);kpis.appendChild(card);
     }
     document.getElementById('mortgage-assumptions').textContent=data.assumptions;
     const history=data.history,projection=data.projection,all=[...history,...projection];
     function draw(){
       const width=mortgageChart.clientWidth,height=mortgageChart.clientHeight;
       if(!width||!height)return;
       const dpr=window.devicePixelRatio||1; mortgageChart.width=width*dpr;mortgageChart.height=height*dpr;
       const ctx=mortgageChart.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
       const p={left:88,right:24,top:18,bottom:40},w=width-p.left-p.right,h=height-p.top-p.bottom;
       const values=all.map(x=>Number(x.balance)),min=Math.min(...values),max=Math.max(...values);
       const margin=Math.max(1,(max-min)*.1),lo=Math.max(0,min-margin),hi=max+margin;
       const dates=all.map(x=>Date.parse(x.as_of+'T00:00:00Z')),x0=Math.min(...dates),x1=Math.max(...dates);
       const x=d=>p.left+(Date.parse(d+'T00:00:00Z')-x0)/(x1-x0||1)*w;
       const y=v=>p.top+(hi-v)/(hi-lo||1)*h;
       ctx.font='12px system-ui';ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
       ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue('--chart-grid').trim();
       for(let i=0;i<=4;i++){const value=lo+(hi-lo)*i/4,yy=y(value);
         ctx.beginPath();ctx.moveTo(p.left,yy);ctx.lineTo(width-p.right,yy);ctx.stroke();
         ctx.textAlign='right';ctx.fillText(aud(value).replace('.00',''),p.left-8,yy+4);}
       function line(series,dashed){ctx.beginPath();ctx.setLineDash(dashed?[7,5]:[]);
         series.forEach((item,i)=>i?ctx.lineTo(x(item.as_of),y(Number(item.balance))):ctx.moveTo(x(item.as_of),y(Number(item.balance))));
         ctx.strokeStyle=getComputedStyle(document.documentElement).getPropertyValue(dashed?'--solarized-orange':'--accent').trim();
         ctx.lineWidth=2.3;ctx.stroke();ctx.setLineDash([]);}
       line(history,false);line([history[history.length-1],...projection],true);
       ctx.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim();
       ctx.textAlign='left';ctx.fillText(history[0].as_of,p.left,height-8);
       ctx.textAlign='right';ctx.fillText(projection[projection.length-1].as_of,width-p.right,height-8);
     }
     new ResizeObserver(draw).observe(mortgageChart);
     document.addEventListener('life-theme-change',draw);draw();
   }catch(error){status.textContent='Unable to load mortgage history: '+error.message;}
 })();
 const imports=document.getElementById('import-form');
 if(imports){const execute=async(commit)=>{const output=document.getElementById('import-result');output.textContent='Validating workbook…';
   try{const data=await request(commit?'/api/v1/imports/finance':'/api/v1/imports/finance/preview',{method:'POST',body:new FormData(imports)});
    output.textContent=JSON.stringify(data.data,null,2);if(commit)location.reload();}catch(err){output.textContent=err.message;}};
  document.getElementById('preview-import').addEventListener('click',()=>execute(false));
  document.getElementById('commit-import').addEventListener('click',()=>execute(true));}
})();