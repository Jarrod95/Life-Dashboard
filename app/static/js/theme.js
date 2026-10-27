(() => {
 const root=document.documentElement,button=document.getElementById('theme-toggle');
 if(!button)return;
 const sync=()=>{button.textContent=root.dataset.theme==='dark'?'Light mode':'Dark mode';};
 button.addEventListener('click',()=>{const next=root.dataset.theme==='dark'?'light':'dark';
 root.dataset.theme=next;localStorage.setItem('life-theme',next);sync();
 document.dispatchEvent(new CustomEvent('life-theme-change'));});
 sync();
})();