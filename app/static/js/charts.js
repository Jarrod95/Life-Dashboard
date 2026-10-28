/* Native Canvas charts: responsive and hoverable; no CDN or chart framework. */
(() => {
 const aud=v=>new Intl.NumberFormat('en-AU',{style:'currency',currency:'AUD'}).format(Number(v));
 const dateLabel=s=>new Intl.DateTimeFormat('en-AU',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(s+'T00:00:00Z'));
 const css=name=>getComputedStyle(document.documentElement).getPropertyValue(name).trim();
 const fetchData=async url=>{const response=await fetch(url);if(!response.ok)throw Error('Unable to load chart data');return response.json();};
 const charts=[];
 function chart(id,render){
   const canvas=document.getElementById(id);if(!canvas)return null;
   const tooltip=document.getElementById(id.replace('-chart','-tooltip'));
   const state={canvas,tooltip,points:[],focus:-1,render,frame:null,labels:[]};
   const draw=()=>{
     const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
     if(!rect.width||!rect.height)return;
     canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
     const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);
     ctx.clearRect(0,0,rect.width,rect.height);
     ctx.font='12px system-ui';state.points=render(ctx,rect.width,rect.height,state)||[];
   };
   const show=i=>{
     if(!state.points.length)return;
     state.focus=Math.max(0,Math.min(i,state.points.length-1));
     const p=state.points[state.focus];
     tooltip.hidden=false;tooltip.textContent=p.label;
     const left=Math.min(Math.max(8,p.x+12),canvas.clientWidth-185);
     const top=Math.max(5,p.y-60);
     tooltip.style.left=left+'px';tooltip.style.top=top+'px';
   };
   canvas.setAttribute('tabindex','0');
   canvas.addEventListener('pointermove',event=>{
     const rect=canvas.getBoundingClientRect();
     if(!state.points.length)return;
     const x=event.clientX-rect.left,y=event.clientY-rect.top;
     const nearest=state.points.reduce((acc,p,i)=>{
       const dist=(p.x-x)**2+(p.y-y)**2;
       return dist<acc.dist?{i,dist}:acc;
     },{i:0,dist:Infinity});
     if(nearest.dist<2500)show(nearest.i);else tooltip.hidden=true;
   });
   canvas.addEventListener('pointerleave',()=>tooltip.hidden=true);
   canvas.addEventListener('focus',()=>show(state.focus<0?0:state.focus));
   canvas.addEventListener('blur',()=>tooltip.hidden=true);
   canvas.addEventListener('keydown',event=>{
     if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
       event.preventDefault();
       const index=event.key==='Home'?0:event.key==='End'?state.points.length-1:
         state.focus+(event.key==='ArrowLeft'?-1:1);
       show(index);
     }
   });
   state.draw=draw;charts.push(state);
   if(typeof ResizeObserver!=='undefined')new ResizeObserver(draw).observe(canvas);
   return state;
 }
 function axes(ctx,w,h,min,max){
   const p={left:100,right:24,top:18,bottom:32},usable=h-p.top-p.bottom,span=max-min||1;
   ctx.strokeStyle=css('--chart-grid');ctx.fillStyle=css('--text-muted');ctx.textAlign='right';
   for(let i=0;i<=4;i++){
     const y=p.top+usable*i/4;
     ctx.beginPath();ctx.moveTo(p.left,y);ctx.lineTo(w-p.right,y);ctx.stroke();
     ctx.fillText(aud(max-span*i/4).replace('.00',''),p.left-9,y+4);
   }
   return {p,y:value=>p.top+(max-value)/span*usable,width:w-p.left-p.right,height:usable};
 }
 const net=chart('networth-chart',(ctx,w,h,state)=>{
   const data=(state.data||[]).filter(x=>x.reported!==null && Number.isFinite(Number(x.reported)));
   if(!data.length){ctx.fillStyle=css('--text-muted');ctx.fillText('No historical net worth snapshots available.',16,45);return [];}
   const day=86400000, date=x=>new Date(x.as_of+'T00:00:00Z').getTime();
   // Calendar-time 90-day rolling mean, not an arbitrary number of snapshots.
   const rolling=data.map(item=>{
     const window=data.filter(x=>date(x)>=date(item)-90*day && date(x)<=date(item));
     return window.reduce((v,x)=>v+Number(x.reported),0)/window.length;
   });
   const last=data[data.length-1],start=date(last);
   const first=Math.max(0,data.length-1);
   const monthly=[];
   for(let i=1;i<data.length;i++){
     const elapsed=(date(data[i])-date(data[i-1]))/day;
     if(elapsed>0)monthly.push((rolling[i]-rolling[i-1])*30.4375/elapsed);
   }
   const rate=monthly.length?monthly.reduce((a,v)=>a+v,0)/monthly.length:0;
   const projected=Array.from({length:12},(_,i)=>{
     const d=new Date(start);d.setUTCMonth(d.getUTCMonth()+i+1);
     return {as_of:d.toISOString().slice(0,10),reported:String(rolling[first]+rate*(i+1))};
   });
   const values=[...data.map(x=>Number(x.reported)),...rolling,...projected.map(x=>Number(x.reported))];
   const min=Math.min(...values),max=Math.max(...values),margin=Math.max(1,(max-min)*.08);
   const axis=axes(ctx,w,h,min-margin,max+margin),end=date(projected[projected.length-1]);
   const pos=(timestamp,value)=>({x:axis.p.left+(timestamp-date(data[0]))/(end-date(data[0])||1)*axis.width,y:axis.y(value)});
   const actual=data.map(item=>({...pos(date(item),Number(item.reported)),label:dateLabel(item.as_of)+' · actual '+aud(item.reported)}));
   const mean=data.map((item,i)=>pos(date(item),rolling[i]));
   const future=[pos(start,rolling[first]),...projected.map(item=>pos(date(item),Number(item.reported)))];
   function drawLine(points,color,dash=[]){ctx.beginPath();ctx.strokeStyle=color;ctx.lineWidth=2.2;ctx.setLineDash(dash);points.forEach((p,i)=>i?ctx.lineTo(p.x,p.y):ctx.moveTo(p.x,p.y));ctx.stroke();ctx.setLineDash([]);}
   drawLine(actual,css('--accent'));
   drawLine(mean,css('--solarized-orange'));
   drawLine(future,css('--solarized-orange'),[6,5]);
   ctx.fillStyle=css('--text-muted');ctx.textAlign='left';ctx.fillText(dateLabel(data[0].as_of),axis.p.left,h-8);
   ctx.textAlign='right';ctx.fillText(dateLabel(projected[11].as_of),w-axis.p.right,h-8);
   const legend=document.getElementById('networth-legend');
   if(legend)legend.textContent='Blue: actual · Orange: trailing 90-day average · Dashed: 12-month projection ('+aud(rate)+'/month average change). Projection is illustrative, not a forecast guarantee.';
   return [...actual,...projected.map((item,i)=>({...future[i+1],label:dateLabel(item.as_of)+' · projected '+aud(item.reported)}))];
 });
 let history=[],selectedRange='all';
 const renderHistory=()=>{
   if(!net)return;
   let data=history;
   if(selectedRange!=='all'&&history.length){
     const count={'1m':1,'3m':3,'6m':6,'1y':12}[selectedRange];
     const last=new Date(history[history.length-1].as_of+'T00:00:00Z');
     const cutoff=new Date(last);cutoff.setUTCMonth(last.getUTCMonth()-count);
     data=history.filter(x=>new Date(x.as_of+'T00:00:00Z')>=cutoff);
   }
   net.data=data;net.focus=-1;net.tooltip.hidden=true;net.draw();
 };
 if(net){
   fetchData('/api/v1/finance/net-worth').then(res=>{
     history=res.data.filter(x=>x.reported!==null);
     renderHistory();
   }).catch(err=>{net.canvas.insertAdjacentText('afterend',err.message);});
   document.querySelectorAll('[data-range]').forEach(button=>button.addEventListener('click',()=>{
     selectedRange=button.dataset.range;
     document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('selected',b===button));
     renderHistory();
   }));
 }
 const cash=chart('spending-chart',(ctx,w,h,state)=>{
   const data=state.data||[];if(!data.length){ctx.fillStyle=css('--text-muted');ctx.fillText('No spending data.',16,30);return [];}
   const items=data.slice(-12),max=Math.max(1,...items.flatMap(x=>[Math.max(0,Number(x.income)),Math.max(0,Number(x.spending))]));
   const a=axes(ctx,w,h,0,max*1.1),points=[];
   const width=a.width/items.length,bar=Math.min(25,width*.28);
   items.forEach((item,i)=>{
     const x=a.p.left+(i+.5)*width;
     [['spending','--solarized-orange',-bar],['income','--accent',1]].forEach(([field,color,offset])=>{
       const value=Math.max(0,Number(item[field])),y=a.y(value);
       ctx.fillStyle=css(color);ctx.fillRect(x+offset,y,bar,a.y(0)-y);
       points.push({x:x+offset+bar/2,y:y+Math.min(20,(a.y(0)-y)/2),
         label:item.label+' · '+field+': '+aud(item[field])});
     });
     ctx.textAlign='center';ctx.fillStyle=css('--text-muted');
     ctx.fillText(item.label.slice(2),x,h-7);
   });
   return points;
 });
 if(cash){
   let cashSequence=0;
   const loadCash=async detail=>{
     const token=++cashSequence;
     const params=new URLSearchParams({group_by:'month'});
     if(detail?.year){params.set('year',detail.year);params.set('month',detail.month||'all');}
     try{const result=await fetchData('/api/v1/finance/spending?'+params);
       if(token!==cashSequence)return;cash.data=result.data;cash.draw();
     }catch(err){if(token===cashSequence)console.error(err);}
   };
   if(!document.getElementById('spending-year'))loadCash();
   document.addEventListener('life-spending-period-changed',event=>loadCash(event.detail));
 }
 const category=chart('category-chart',(ctx,w,h,state)=>{
   const data=(state.data||[]).filter(x=>Number(x.spending)>0);
   if(!data.length){ctx.fillStyle=css('--text-muted');ctx.fillText('No positive net category expenses for this period.',16,30);return [];}
   const visible=data.slice(0,12),max=Math.max(...visible.map(x=>Number(x.spending)));
   const labelWidth=Math.min(180,Math.max(100,w*.24)),right=90;
   const barSpace=(h-20)/visible.length,points=[];
   visible.forEach((item,i)=>{
     const y=12+i*barSpace,amount=Number(item.spending),length=Math.max(1,(w-labelWidth-right-18)*amount/max);
     ctx.textAlign='right';ctx.fillStyle=css('--text-primary');
     const name=item.category.length>24?item.category.slice(0,21)+'…':item.category;
     ctx.fillText(name,labelWidth-10,y+barSpace/2+4);
     ctx.fillStyle=css('--accent');ctx.fillRect(labelWidth,y+barSpace*.24,length,barSpace*.5);
     ctx.textAlign='left';ctx.fillStyle=css('--text-muted');
     ctx.fillText(aud(amount),labelWidth+length+7,y+barSpace/2+4);
     points.push({x:labelWidth+length/2,y:y+barSpace*.5,label:item.category+' · '+aud(amount)});
   });
   return points;
 });
 if(category){
   let categorySequence=0;
   const loadCategory=async detail=>{
     const token=++categorySequence;
     const params=new URLSearchParams();
     if(detail?.year){params.set('year',detail.year);params.set('month',detail.month||'all');}
     try{const result=await fetchData('/api/v1/finance/spending/categories?'+params);
       if(token!==categorySequence)return;
       category.data=result.data;category.focus=-1;category.tooltip.hidden=true;category.draw();
       const total=result.data.reduce((sum,x)=>sum+Number(x.spending),0);
       document.getElementById('category-total').textContent='Net spending: '+aud(total)+' · '+result.data.length+' categories';
     }catch(err){if(token===categorySequence)document.getElementById('category-total').textContent='Unable to load categories: '+err.message;}
   };
   document.addEventListener('life-spending-period-changed',event=>loadCategory(event.detail));
 }

 document.addEventListener('life-theme-change',()=>charts.forEach(c=>c.draw()));
})();
