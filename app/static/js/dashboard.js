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
 const imports=document.getElementById('import-form');
 if(imports){const execute=async(commit)=>{const output=document.getElementById('import-result');output.textContent='Validating workbook…';
   try{const data=await request(commit?'/api/v1/imports/finance':'/api/v1/imports/finance/preview',{method:'POST',body:new FormData(imports)});
    output.textContent=JSON.stringify(data.data,null,2);if(commit)location.reload();}catch(err){output.textContent=err.message;}};
  document.getElementById('preview-import').addEventListener('click',()=>execute(false));
  document.getElementById('commit-import').addEventListener('click',()=>execute(true));}
})();