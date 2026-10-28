(() => {
 const canvas=document.getElementById('offset-chart');if(!canvas)return;
 const status=document.getElementById('offset-status'),metrics=document.getElementById('offset-metrics'),note=document.getElementById('offset-note');
 const aud=x=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(x));
 let data=null;
 function metric(label,value){const item=document.createElement('article');item.className='metric';const t=document.createElement('span');t.textContent=label;const strong=document.createElement('strong');strong.textContent=value;item.append(t,strong);return item;}
 function draw(){
  if(!data||!data.history?.length)return;
  const w=canvas.clientWidth,h=canvas.clientHeight;if(w<100||h<100)return;
  const dpr=window.devicePixelRatio||1;canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);
  const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
  const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const all=[...data.history,...data.projection],values=all.map(x=>Number(x.balance_aud));
  const lo=Math.min(...values),hi=Math.max(...values),padding=Math.max(100,(hi-lo)*.12),min=Math.max(0,lo-padding),max=hi+padding;
  const origin=Date.parse(all[0].as_of+'T00:00:00Z'),end=Date.parse(all[all.length-1].as_of+'T00:00:00Z');
  const p={left:90,right:28,top:25,bottom:38},cw=w-p.left-p.right,ch=h-p.top-p.bottom;
  const x=item=>p.left+(Date.parse(item.as_of+'T00:00:00Z')-origin)/Math.max(1,end-origin)*cw;
  const y=item=>p.top+(max-Number(item.balance_aud))/Math.max(1,max-min)*ch;
  ctx.font='12px system-ui';ctx.fillStyle=css('--text-muted');ctx.strokeStyle=css('--chart-grid');
  for(let i=0;i<=4;i++){const yy=p.top+i*ch/4;ctx.beginPath();ctx.moveTo(p.left,yy);ctx.lineTo(w-p.right,yy);ctx.stroke();ctx.textAlign='right';ctx.fillText(aud(max-(max-min)*i/4).replace('.00',''),p.left-9,yy+4);}
  function line(items,color,dashed){ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.setLineDash(dashed?[7,5]:[]);items.forEach((item,i)=>i?ctx.lineTo(x(item),y(item)):ctx.moveTo(x(item),y(item)));ctx.stroke();ctx.setLineDash([]);}
  line(data.history,css('--accent'),false);
  line([data.history[data.history.length-1],...data.projection],css('--solarized-orange'),true);
  ctx.fillStyle=css('--text-muted');ctx.textAlign='left';ctx.fillText(all[0].as_of,p.left,h-7);ctx.textAlign='right';ctx.fillText(all[all.length-1].as_of,w-p.right,h-7);
 }
 (async()=>{try{const response=await fetch('/api/v1/finance/net-worth/offset');if(!response.ok)throw Error('Offset API unavailable');
  data=(await response.json()).data;
  if(data.status!=='ok'){status.textContent=data.message||'No offset account history available';return;}
  status.textContent='Actual through '+data.latest_as_of+' · blue: actual · dashed orange: illustrative projection';
  metrics.replaceChildren(metric('Latest balance',aud(data.current_balance_aud)),metric('Observed average change / month',aud(data.average_monthly_change_aud)),metric('Projected in 12 months',aud(data.projected_12mo_aud)));
  note.textContent=data.assumptions;
  draw();if(typeof ResizeObserver!=='undefined')new ResizeObserver(draw).observe(canvas);document.addEventListener('life-theme-change',draw);
 }catch(err){status.textContent='Unable to load offset chart: '+err.message;}})();
})();
