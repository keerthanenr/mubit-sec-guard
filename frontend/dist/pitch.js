'use strict';
const slides=[...document.querySelectorAll('.slide')];
const stage=document.getElementById('deck-stage');
const canvas=document.getElementById('slide-canvas');
const overview=document.getElementById('overview-dialog');
const notes=document.getElementById('notes-dialog');
const dots=document.getElementById('slide-dots');
const grid=document.getElementById('overview-grid');
const symbols=['⌘ → ◎','! → ✓','⌘ → ✳','✳ → ◇','+','✳'];
let current=0;
function readHash(){const m=location.hash.match(/^#slide-(\d+)$/);return m?Math.min(slides.length-1,Math.max(0,Number(m[1])-1)):0;}
function show(index,{updateURL=true}={}){
 current=Math.max(0,Math.min(slides.length-1,index));
 slides.forEach((slide,i)=>{slide.hidden=i!==current;slide.setAttribute('aria-hidden',String(i!==current));});
 document.querySelectorAll('[data-slide]').forEach(button=>button.setAttribute('aria-current',String(Number(button.dataset.slide)===current)));
 document.getElementById('deck-counter').textContent=String(current+1).padStart(2,'0')+' / '+String(slides.length).padStart(2,'0');
 document.getElementById('deck-section').textContent=slides[current].dataset.title;
 document.getElementById('deck-progress').style.width=((current+1)/slides.length*100)+'%';
 document.getElementById('deck-prev').disabled=current===0;
 document.getElementById('deck-next').disabled=current===slides.length-1;
 document.getElementById('deck-live').textContent='Slide '+(current+1)+' of '+slides.length+': '+slides[current].dataset.title;
 document.title='VulHawk / '+slides[current].dataset.title+' / Pitch deck';
 if(updateURL)history.replaceState(null,'','#slide-'+(current+1));
 stage.scrollTop=0;
 if(notes.open)renderNotes();
}
slides.forEach((slide,i)=>{
 const dot=document.createElement('button');dot.type='button';dot.dataset.slide=i;dot.setAttribute('aria-label','Slide '+(i+1)+': '+slide.dataset.title);dot.addEventListener('click',()=>show(i));dots.appendChild(dot);
 const card=document.createElement('button');card.type='button';card.dataset.slide=i;card.className='overview-card';
 const art=document.createElement('div');art.className='overview-art'+(slide.classList.contains('slide-mubit')?' mubit-art':'');art.textContent=symbols[i];art.setAttribute('aria-hidden','true');
 const label=document.createElement('span');const number=document.createElement('small');number.textContent=String(i+1).padStart(2,'0')+' / VULHAWK';label.appendChild(number);label.appendChild(document.createTextNode(slide.dataset.title));card.append(art,label);card.addEventListener('click',()=>{show(i);overview.close();document.getElementById('overview-open').focus();});grid.appendChild(card);
});
function resize(){
 if(matchMedia('(max-width:700px) and (orientation:portrait)').matches){stage.style.width='';stage.style.height='';canvas.style.transform='';return;}
 const viewport=document.querySelector('.deck-viewport');const availableHeight=viewport.clientHeight;const availableWidth=viewport.clientWidth-44;
 const width=Math.min(availableWidth,availableHeight*16/9,1500);stage.style.width=width+'px';stage.style.height=width*9/16+'px';canvas.style.transform='scale('+(width/1280)+')';
}
function openOverview(){if(!overview.open)overview.showModal();}
function renderNotes(){document.getElementById('notes-title').textContent=String(current+1).padStart(2,'0')+' / '+slides[current].dataset.title;document.getElementById('notes-content').innerHTML=slides[current].querySelector('.presenter-notes').innerHTML;}
function openNotes(){renderNotes();if(!notes.open)notes.showModal();}
async function toggleFullscreen(){try{if(document.fullscreenElement)await document.exitFullscreen();else await document.documentElement.requestFullscreen();}catch{document.getElementById('deck-live').textContent='Fullscreen is unavailable in this browser. The deck remains usable in the current window.';}}
document.getElementById('deck-prev').addEventListener('click',()=>show(current-1));
document.getElementById('deck-next').addEventListener('click',()=>show(current+1));
document.getElementById('overview-open').addEventListener('click',openOverview);
document.getElementById('overview-close').addEventListener('click',()=>overview.close());
document.getElementById('notes-open').addEventListener('click',openNotes);
document.getElementById('notes-close').addEventListener('click',()=>notes.close());
document.getElementById('deck-fullscreen').addEventListener('click',toggleFullscreen);
document.getElementById('deck-print').addEventListener('click',()=>window.print());
window.addEventListener('resize',resize);window.addEventListener('hashchange',()=>show(readHash(),{updateURL:false}));
document.addEventListener('fullscreenchange',()=>{document.getElementById('deck-fullscreen').setAttribute('aria-label',document.fullscreenElement?'Exit fullscreen presentation':'Enter fullscreen presentation');resize();});
document.addEventListener('keydown',event=>{
 if(event.key.toLowerCase()==='n'&&!event.altKey&&!event.ctrlKey&&!event.metaKey&&!['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName)){event.preventDefault();if(notes.open)notes.close();else if(!overview.open)openNotes();return;}
 if(event.key===' '&&event.target.closest('a,button,input,textarea,select,[contenteditable=true]'))return;
 if(overview.open||notes.open||event.altKey||event.ctrlKey||event.metaKey||['INPUT','TEXTAREA','SELECT'].includes(event.target.tagName))return;
 if(['ArrowRight','PageDown',' '].includes(event.key)){event.preventDefault();show(current+1);}
 else if(['ArrowLeft','PageUp'].includes(event.key)){event.preventDefault();show(current-1);}
 else if(event.key==='Home'){event.preventDefault();show(0);}
 else if(event.key==='End'){event.preventDefault();show(slides.length-1);}
 else if(event.key.toLowerCase()==='o'){event.preventDefault();openOverview();}
 else if(event.key.toLowerCase()==='f'){event.preventDefault();toggleFullscreen();}
});
let startTouch=null;
stage.addEventListener('touchstart',event=>{if(event.target.closest('a,button')||event.touches.length!==1)return;startTouch={x:event.touches[0].clientX,y:event.touches[0].clientY};},{passive:true});
stage.addEventListener('touchend',event=>{if(!startTouch||!event.changedTouches.length)return;const dx=event.changedTouches[0].clientX-startTouch.x,dy=event.changedTouches[0].clientY-startTouch.y;startTouch=null;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.5)show(current+(dx<0?1:-1));},{passive:true});
show(readHash(),{updateURL:false});resize();
