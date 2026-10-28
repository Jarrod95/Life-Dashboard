(() => {
  const root=document.getElementById('spending-year');if(!root)return;
  const month=document.getElementById('spending-month'), money=v=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(v)||0);
  const state={year:null,month:'all',sequence:0,abort:null,summary:null,opportunities:[]};
  const el=id=>document.getElementById(id);
  async function get(path,signal){const res=await fetch(path,{signal});const json=await res.json();if(!res.ok)throw Error(json.error?.message||'Unable to load spending data');return json;}
  function params(){const p=new URLSearchParams({year:String(state.year),month:state.month});return p;}
  function updateURL(){const url=new URL(location.href);url.searchParams.set('year',state.year);if(state.month==='all')url.searchParams.delete('month');else url.searchParams.set('month',state.month);history.pushState({},'',url);}
  function rowTable(headers,items){
    const table=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');
    for(const h of headers){const th=document.createElement('th');th.textContent=h;tr.append(th);}head.append(tr);table.append(head);
    const body=document.createElement('tbody');
    for(const item of items){const r=document.createElement('tr');for(const value of item){const cell=document.createElement('td');if(value instanceof Node)cell.append(value);else cell.textContent=String(value);r.append(cell);}body.append(r);}
    if(!items.length){const r=document.createElement('tr'),cell=document.createElement('td');cell.colSpan=headers.length;cell.textContent='No matching records for this period';r.append(cell);body.append(r);}
    table.append(body);return table;
  }
  function drill(label,kind){const form=el('transaction-filters');form.elements.merchant.value=kind==='merchant'?label:'';
    if(kind==='category'){const option=[...form.elements.category.options].find(o=>o.text.toLowerCase()===label.toLowerCase());form.elements.category.value=option?.value||'';}
    else form.elements.category.value='';
    form.dispatchEvent(new Event('submit',{cancelable:true}));form.scrollIntoView({behavior:'smooth',block:'start'});
  }
  function link(label,kind){const a=document.createElement('button');a.type='button';a.className='text-link';a.textContent=label;a.addEventListener('click',()=>drill(label,kind));return a;}
  function metric(label,value,note){const article=document.createElement('article');article.className='metric';const heading=document.createElement('span');heading.textContent=label;const strong=document.createElement('strong');strong.textContent=value;const small=document.createElement('small');small.textContent=note||'';article.append(heading,strong,small);return article;}
  function renderSummary(s){state.summary=s;el('spending-kpis').replaceChildren(
    metric('Total consumption',money(s.total_consumption_aud),s.period.label),
    metric('Discretionary',money(s.discretionary_aud),'Classified adjustable costs'),
    metric('Average per transaction',money(s.average_transaction_aud),s.transactions+' eligible transactions'),
    metric('Average per observed month',money(s.average_month_aud),'Not an annual forecast'),
    metric('Cash-flow debits',money(s.cash_debits_aud),'Includes transfers and BNPL')
  );
    el('spending-coverage').textContent=s.period.label+' · '+(s.period.last_transaction_date?'Data through '+s.period.last_transaction_date:'No transactions')+(s.period.is_partial_period?' · incomplete period':'');
    el('spending-warnings').textContent=s.warnings.join(' ');
  }
  function renderMerchants(items){el('spending-merchants').replaceChildren(rowTable(['Merchant','Categories','Spend','Transactions','Average purchase','Share'],items.map(x=>[
    link(x.merchant,'merchant'),x.categories.join(', '),money(x.spend_aud),x.transactions,money(x.average_aud),x.share_pct==null?'Unavailable':x.share_pct+'%'
  ])));}
  function renderRecurring(items){el('spending-recurring').replaceChildren(rowTable(['Merchant','Cadence','Occurrences','Last amount','Monthly estimate','Next expected'],items.map(x=>[
    link(x.merchant,'merchant'),x.cadence,x.occurrences,money(x.last_amount_aud),money(x.monthly_equivalent_aud),x.next_expected_date+' (estimated)'
  ])));}
  function renderOpportunities(items){
    state.opportunities=items;
    const container=el('spending-opportunities');container.replaceChildren();
    if(!items.length){container.textContent='Not enough classified discretionary purchases to identify opportunities.';recalculate();return;}
    for(const x of items){
      const card=document.createElement('article');card.className='spending-opportunity';
      const header=document.createElement('div');header.className='opportunity-heading';
      const name=link(x.category,'category');name.classList.add('opportunity-name');
      const total=document.createElement('strong');total.textContent=money(x.amount_aud);
      header.append(name,total);
      const evidence=document.createElement('p');evidence.className='muted';
      evidence.textContent=x.transactions+' purchases · '+money(x.average_ticket_aud)+' average · '+x.signal+' · confidence: '+x.confidence;
      const reason=document.createElement('p');reason.textContent=x.rationale;
      const baseline=document.createElement('p');baseline.className='muted';
      baseline.textContent=x.baseline_monthly_aud===null?'Historical comparison unavailable: '+x.baseline_label:
        'Prior 3-month average: '+money(x.baseline_monthly_aud)+'/month'+(x.change_pct!==null?' · change: '+x.change_pct+'%':' · comparison unavailable for partial periods');
      const line=document.createElement('label');line.className='scenario-row';
      const label=document.createElement('span');label.textContent='Hypothetical spending reduction';
      const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='60';slider.step='5';slider.value='20';slider.dataset.amount=x.amount_aud;
      const output=document.createElement('output');output.textContent='20%';
      const saving=document.createElement('strong');saving.className='opportunity-saving';saving.textContent=money(Number(x.amount_aud)*.2);
      slider.addEventListener('input',()=>{output.textContent=slider.value+'%';saving.textContent=money(Number(x.amount_aud)*Number(slider.value)/100);recalculate();});
      line.append(label,slider,output);
      card.append(header,evidence,reason,baseline,line,saving);container.append(card);
    }
    recalculate();
  }
  function periodsObserved(){const p=state.summary?.period;if(!p)return 1;if(p.month)return 1;
    const limit=p.last_transaction_date?new Date(p.last_transaction_date+'T00:00:00Z').getUTCMonth()+1:12;
    return p.is_partial_period?Math.max(1,limit-1):12;
  }
  function recalculate(){let total=0;for(const slider of el('spending-opportunities').querySelectorAll('input[type="range"]'))total+=Number(slider.dataset.amount)*Number(slider.value)/100;
    const observed=periodsObserved(),monthly=total/observed;
    el('savings-period').textContent=money(total);el('savings-month').textContent=money(monthly);el('savings-year').textContent=money(monthly*12);
    el('savings-caveat').textContent='Hypothetical scenario based on '+(state.summary?.period.label||'selected period')+'; '+(state.summary?.period.is_partial_period?'partial observations are not reliable annual forecasts.':'annualised figures assume the spending pattern repeats, not guaranteed savings.');
  }
  async function load(){if(!state.year)return;state.abort?.abort();const controller=new AbortController();state.abort=controller;const id=++state.sequence;
    const q=params().toString();el('spending-coverage').textContent='Loading '+state.year+'…';
    try{const [summary,merchants,insights,recurring]=await Promise.all([
      get('/api/v1/finance/spending/summary?'+q,controller.signal),
      get('/api/v1/finance/spending/merchants?'+q+'&sort='+el('merchant-sort').value,controller.signal),
      get('/api/v1/finance/spending/insights?'+q,controller.signal),
      get('/api/v1/finance/spending/recurring?'+q,controller.signal)]);
      if(id!==state.sequence)return;
      renderSummary(summary.data);renderMerchants(merchants.data);renderOpportunities(insights.data);renderRecurring(recurring.data);
      document.dispatchEvent(new CustomEvent('life-spending-period-changed',{detail:{year:state.year,month:state.month}}));
    }catch(error){if(error.name!=='AbortError'&&id===state.sequence)el('spending-coverage').textContent='Spending data unavailable: '+error.message;}
  }
  function sync(){root.value=state.year;month.value=state.month;}
  function choose(){state.year=root.value;state.month=month.value;updateURL();load();}
  root.addEventListener('change',choose);month.addEventListener('change',choose);
  el('merchant-sort').addEventListener('change',load);
  el('spending-reset').addEventListener('click',()=>{state.year=state.latest;state.month='all';sync();updateURL();load();});
  el('savings-reset').addEventListener('click',()=>renderOpportunities(state.opportunities));
  window.addEventListener('popstate',()=>{const p=new URLSearchParams(location.search);state.year=root.querySelector('option[value="'+p.get('year')+'"]')?p.get('year'):state.latest;state.month=/^(?:[1-9]|1[0-2])$/.test(p.get('month')||'')?p.get('month'):'all';sync();load();});
  (async()=>{try{const json=await get('/api/v1/finance/spending/periods');const data=json.data;state.latest=String(data.default.year);
    root.replaceChildren(...data.years.map(year=>{const o=document.createElement('option');o.value=String(year);o.textContent=String(year);return o;}));
    if(!data.years.length){const o=document.createElement('option');o.value=state.latest;o.textContent=state.latest;root.append(o);}
    const url=new URLSearchParams(location.search),y=url.get('year'),m=url.get('month');
    state.year=data.years.map(String).includes(y)?y:state.latest;state.month=/^(?:[1-9]|1[0-2])$/.test(m||'')?m:'all';sync();load();
  }catch(err){el('spending-coverage').textContent='Unable to load periods: '+err.message;}})();
})();
