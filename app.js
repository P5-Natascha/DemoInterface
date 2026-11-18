const $=id=>document.getElementById(id);

/* ---- Texte aus TEXTE in die Seite einsetzen ---- */
const T=TEXTE;
const pfad=p=>p.split('.').reduce((o,k)=>o[k],T);
function setzeText(el,s){                    // "\n" wird zum Zeilenumbruch
  el.replaceChildren(...s.split('\n').flatMap((z,i)=>i?[document.createElement('br'),z]:[z]));
}
document.title=T.seitentitel;
document.querySelectorAll('[data-t]').forEach(el=>setzeText(el,pfad(el.dataset.t)));
document.querySelectorAll('[data-t-aria]').forEach(el=>el.setAttribute('aria-label',pfad(el.dataset.tAria)));
document.querySelectorAll('[data-t-alt]').forEach(el=>el.setAttribute('alt',pfad(el.dataset.tAlt)));
{
  const flow=$('flow');
  T.technik.schritte.forEach((st,i)=>{
    const d=document.createElement('div');
    d.innerHTML='<b></b><h3></h3><p></p>';
    d.children[0].textContent=i+1;d.children[1].textContent=st.titel;d.children[2].textContent=st.text;
    flow.append(d);
  });
  flow.style.setProperty('--n',T.technik.schritte.length);
  T.projekt.eckdaten.forEach(([name,wert])=>{
    const d=document.createElement('div'),sp=document.createElement('span');
    sp.textContent=name;d.append(sp,wert);$('specs').append(d);
  });
  document.querySelectorAll('[data-gh]').forEach(a=>{
    a.href=EINSTELLUNGEN.githubLink;
    a.prepend($('icon-github').content.cloneNode(true));
  });
}
const pad=$('pad'),knob=$('knob');
const INVERT_Y=EINSTELLUNGEN.yAchseUmkehren;
let nx=0,ny=0,drag=false,idle=99,ws,canCtrl=false;
const keys=new Set();

function setStick(x,y){
  const l=Math.hypot(x,y); if(l>1){x/=l;y/=l}
  nx=x;ny=y;
  const R=(pad.clientWidth-knob.clientWidth)/2;
  knob.style.transform=`translate(calc(-50% + ${x*R}px),calc(-50% - ${y*R}px))`;
  const yy=INVERT_Y?-y:y;
  $('rx').textContent=Math.round((x+1)/2*4095);
  $('ry').textContent=Math.round((yy+1)/2*4095);
  vizVals();
}
function fromPointer(e){
  const r=pad.getBoundingClientRect(),R=(r.width-knob.offsetWidth)/2;
  setStick((e.clientX-r.left-r.width/2)/R,-(e.clientY-r.top-r.height/2)/R);
}
pad.addEventListener('pointerdown',e=>{drag=true;pad.classList.add('drag');pad.setPointerCapture(e.pointerId);fromPointer(e)});
pad.addEventListener('pointermove',e=>drag&&fromPointer(e));
const release=()=>{drag=false;pad.classList.remove('drag');setStick(0,0)};
pad.addEventListener('pointerup',release);
pad.addEventListener('pointercancel',release);
document.addEventListener('visibilitychange',()=>document.hidden&&release());

const map={ArrowUp:'u',w:'u',ArrowDown:'d',s:'d',ArrowLeft:'l',a:'l',ArrowRight:'r',d:'r'};
function keyStick(){
  setStick((keys.has('r')?1:0)-(keys.has('l')?1:0),(keys.has('u')?1:0)-(keys.has('d')?1:0));
}
addEventListener('keydown',e=>{const k=map[e.key]||map[e.key.toLowerCase()];if(k&&!drag){e.preventDefault();keys.add(k);keyStick()}});
addEventListener('keyup',e=>{const k=map[e.key]||map[e.key.toLowerCase()];if(k&&!drag){keys.delete(k);keyStick()}});

setInterval(()=>{
  if(nx||ny)idle=0;
  if(idle++<6&&ws&&ws.readyState===1&&canCtrl){
    ws.send(JSON.stringify({x:+$('rx').textContent,y:+$('ry').textContent}));
    vizPuls();
  }
},33);

const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const colorFor=p=>p>.5?'var(--ok)':p>.2?'var(--warn)':'var(--bad)';
function setVal(id,v,fmt){$(id).textContent=v==null?T.telemetrie.leer:fmt(v)}

function render(s){
  $('pBack').classList.add('on');
  $('pCar').classList.toggle('on',s.tcp);
  $('pps').textContent=s.pps;
  $('pMode').classList.toggle('on',s.mode===1);
  canCtrl=s.ctrl;
  pad.classList.toggle('lock',!s.ctrl);
  const M=T.steuerung.meldungen;
  $('ctrlMsg').textContent=!s.ctrl?M.keinSchluessel:s.blocked?M.gesperrt:s.tcp?M.bereit:M.autoGetrennt;
  blocked=!!s.blocked;
  $('ctrlMsg').classList.toggle('ok',!!(s.ctrl&&!s.blocked&&s.tcp));
  for(const n of ['front','back'])setCam(n,s.cam||{});
  const t=s.tele||{};
  setVal('batt',t.BATT,v=>v.toFixed(2));
  const bp=t.BATT==null?0:clamp((t.BATT-3.3)/(4.2-3.3),0,1);
  Object.assign($('battBar').style,{width:bp*100+'%',background:colorFor(bp)});
  setVal('ampr',t.AMPR,v=>(Math.abs(v)<0.005?0:v).toFixed(2));
  $('amprBar').style.width=(t.AMPR==null?0:clamp(t.AMPR/2,0,1)*100)+'%';
  setVal('lenk',t.LENK,v=>v.toFixed(2));
  const lp=t.LENK==null?.5:clamp(t.LENK/2.4,0,1),b=$('lenkBar').style;
  b.left=Math.min(lp,.5)*100+'%';b.width=Math.abs(lp-.5)*100+'%';
  for(const [k,id] of [['ABSV','absv'],['ABSH','absh']]){
    const mm=t[k];
    setVal(id,mm,v=>(v/1000).toFixed(2));
    const p=mm==null?0:clamp(mm/3000,0,1);
    Object.assign($(id+'Bar').style,{width:p*100+'%',background:mm<500?'var(--bad)':mm<1000?'var(--warn)':'var(--ok)'});
  }
}
const KEY=new URLSearchParams(location.search).get('key')||'';
const camOn={};
function stopCam(n){camOn[n]=0;$('img-'+n).removeAttribute('src')}
function setCam(n,c){
  const img=$('img-'+n),msg=$('msg-'+n);
  if(c.allowed&&!camOn[n]){
    camOn[n]=1;
    const load=()=>{img.src='/camera/'+n+'?key='+encodeURIComponent(KEY)+'&t='+Date.now()};
    img.onerror=()=>setTimeout(()=>{if(camOn[n])load()},2000);
    load();
  }
  if(!c.allowed&&camOn[n])stopCam(n);
  const live=!!(c.allowed&&c[n]);
  img.hidden=!live;
  const K=T.kameras.meldungen;
  msg.textContent=live?'':!c.allowed?(c.disabled?K.adminAus:K.nurMitSchluessel):K.wartenAufBild;
  msg.hidden=live;
}
function connect(){
  const key=new URLSearchParams(location.search).get('key')||'';
  ws=new WebSocket((location.protocol==='https:'?'wss://':'ws://')+location.host+'/ws?key='+encodeURIComponent(key));
  ws.onmessage=e=>render(JSON.parse(e.data));
  ws.onclose=()=>{canCtrl=false;$('pBack').classList.remove('on');$('pCar').classList.remove('on');pad.classList.add('lock');['front','back'].forEach(n=>{stopCam(n);$('img-'+n).hidden=true;$('msg-'+n).textContent=T.kameras.meldungen.keineVerbindung;$('msg-'+n).hidden=false});setTimeout(connect,1500)};
}
pad.addEventListener('contextmenu',e=>e.preventDefault());
/* Vollbild und Querformat */
let blocked=false,fsAuto=true;
const FSROOT=document.documentElement;
const fsEl=()=>document.fullscreenElement||document.webkitFullscreenElement;
const fsCan=!!(FSROOT.requestFullscreen||FSROOT.webkitRequestFullscreen);
const driveMQ=matchMedia('(orientation:landscape) and (max-height:520px) and (hover:none) and (pointer:coarse)');
async function enterFs(){
  let fs=!!fsEl(),lock=false;
  if(!fs){
    try{
      if(FSROOT.requestFullscreen)await FSROOT.requestFullscreen({navigationUI:'hide'});
      else if(FSROOT.webkitRequestFullscreen){FSROOT.webkitRequestFullscreen();await new Promise(r=>setTimeout(r,200))}
    }catch{}
    fs=!!fsEl();
  }
  try{await screen.orientation.lock('landscape');lock=true}catch{}
  return{fs,lock};
}
function exitFs(){
  try{screen.orientation.unlock()}catch{}
  try{const r=(document.exitFullscreen||document.webkitExitFullscreen).call(document);r&&r.catch&&r.catch(()=>{})}catch{}
}
function onFs(){
  const on=!!fsEl();
  FSROOT.classList.toggle('fs',on);
  $('fsTx').textContent=on?T.steuerung.vollbild.aus:T.steuerung.vollbild.an;
  if(!on){try{screen.orientation.unlock()}catch{}}
  setStick(nx,ny);
}
document.addEventListener('fullscreenchange',onFs);
document.addEventListener('webkitfullscreenchange',onFs);
function note(t){const n=$('fsNote');n.textContent=t;n.hidden=false;setTimeout(()=>n.hidden=true,8000)}
$('fsBtn').onclick=async()=>{
  if(fsEl()){exitFs();return}
  const r=await enterFs();
  if(!r.fs)note(fsCan?T.steuerung.meldungen.vollbildAbgelehnt:T.steuerung.meldungen.vollbildNichtMoeglich);
  else if(!r.lock&&!driveMQ.matches)note(T.steuerung.meldungen.handyDrehen);
};
/* Automatisch: Browser erlauben Vollbild nur nach einer Berührung. Deshalb beim ersten Loslassen,
   sobald die Fahransicht aktiv ist und die Steuerung freigeschaltet ist. */
document.addEventListener('pointerup',e=>{
  if(e.target.closest&&e.target.closest('#fsBtn'))return;
  if(fsAuto&&!fsEl()&&driveMQ.matches&&canCtrl&&!blocked){fsAuto=false;enterFs()}
});
addEventListener('resize',()=>setStick(nx,ny));
/* Live-Visualisierung der Input-Kette */
let lvN=0;
function vizVals(){
  const x=+$('rx').textContent,y=+$('ry').textContent;
  $('lvXY').textContent='X '+x+' · Y '+y;
  const g=Math.round((y-2048)/2048*100),l=Math.round((x-2048)/2048*100);
  const gt=g>0?g+' % vorwärts':g<0?(-g)+' % rückwärts':'0 %';
  const lt=l>0?l+' % rechts':l<0?(-l)+' % links':'0 %';
  $('lvOut').textContent='Gas '+gt+' · Lenkung '+lt;
}
function vizPuls(){
  $('lvPkts').textContent=++lvN;
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const vert=matchMedia('(max-width:860px)').matches,step=240;
  const stages=[...document.querySelectorAll('#pipe .stage')];
  const links=[...document.querySelectorAll('#pipe .link')];
  stages.forEach((s,i)=>setTimeout(()=>{s.classList.add('hit');setTimeout(()=>s.classList.remove('hit'),280)},i*step));
  links.forEach((l,i)=>{
    const d=document.createElement('i');d.className='pkt';l.appendChild(d);
    const dist=vert?l.clientHeight:l.clientWidth;
    if(vert){d.style.left='-4px';d.style.top='0'}else{d.style.top='-4px';d.style.left='0'}
    const a=d.animate([{transform:vert?'translateY(0)':'translateX(0)'},{transform:vert?'translateY('+dist+'px)':'translateX('+dist+'px)'}],{duration:step,delay:i*step,easing:'linear',fill:'forwards'});
    a.onfinish=()=>d.remove();
  });
}
setStick(0,0);connect();
