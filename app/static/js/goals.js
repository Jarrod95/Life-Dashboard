document.querySelectorAll('.goal-plot').forEach(el=>{
 const points=JSON.parse(el.dataset.points), target=Number(el.dataset.target), forecast=JSON.parse(el.dataset.forecast);
 const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
 svg.setAttribute('viewBox','0 0 640 210'); svg.setAttribute('aria-hidden','true');
 const dates=points.map(p=>Date.parse(p.date)), values=points.map(p=>p.value);
 const estimate=forecast.status==='estimated'?Date.parse(forecast.date):dates.at(-1);
 const start=dates[0], end=Math.max(dates.at(-1),estimate), lo=Math.min(target,...values), hi=Math.max(target,...values);
 const span=Math.max(hi-lo,1), x=d=>48+552*(d-start)/Math.max(end-start,86400000), y=v=>175-145*(v-lo)/span;
 function node(tag, attrs, text){const n=document.createElementNS(ns,tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,v));if(text!==undefined)n.textContent=text;svg.append(n);}
 for(let i=0;i<=4;i++){const v=lo+span*i/4;node('line',{x1:48,x2:600,y1:y(v),y2:y(v),stroke:'var(--border)'});node('text',{x:43,y:y(v)+4,'text-anchor':'end',fill:'var(--text-muted)','font-size':10},v.toFixed(1));}
 node('line',{x1:48,x2:600,y1:y(target),y2:y(target),stroke:'var(--solarized-yellow)','stroke-dasharray':'5 4'});
 node('polyline',{points:points.map((p,i)=>x(dates[i])+','+y(p.value)).join(' '),fill:'none',stroke:'var(--accent)','stroke-width':2});
 points.forEach((p,i)=>node('circle',{cx:x(dates[i]),cy:y(p.value),r:2,fill:'var(--accent)'}));
 if(forecast.status==='estimated')node('line',{x1:x(dates.at(-1)),y1:y(values.at(-1)),x2:x(estimate),y2:y(target),stroke:'var(--solarized-cyan)','stroke-width':2,'stroke-dasharray':'5 4'});
 node('text',{x:48,y:198,fill:'var(--text-muted)','font-size':11},points[0].date);
 node('text',{x:600,y:198,'text-anchor':'end',fill:'var(--text-muted)','font-size':11},forecast.status==='estimated'?forecast.date:points.at(-1).date);
 el.append(svg);
});
