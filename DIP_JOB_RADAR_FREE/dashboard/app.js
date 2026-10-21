let jobs=[];
const $=(id)=>document.getElementById(id);
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=String(text);return node;};
function tag(text){return el('span','tag',text);}
function render(){
  const term=$('query').value.toLowerCase().trim(),quality=$('quality').value,source=$('source').value,progress=$('progress').value;
  const root=$('jobs');root.replaceChildren();
  const visible=jobs.filter(j=>(!term||[j.title,j.company,j.location,j.source].join(' ').toLowerCase().includes(term))&&(quality==='all'||(quality==='qualified'?!j.rejection_reason:!!j.rejection_reason))&&(source==='all'||j.source_kind===source)&&(progress==='all'||j.status===progress));
  if(!visible.length){root.append(el('div','empty','No matching discoveries yet. Configure an employer watchlist and run a scan.'));return;}
  visible.forEach(j=>{
    const card=el('article','job'),top=el('div','top'),left=el('div');left.append(el('h3','',j.title),el('div','company',j.company||'Employer not identified'));top.append(left,el('div','score',j.score+'/100'));card.append(top);
    card.append(tag(j.location||'Location unavailable'),tag(j.source_kind==='ats'?'ATS · published':'RSS · not verified'),tag(j.status||'Untracked'));
    card.append(el('div','muted',j.source));
    card.append(el('div','muted','Discovered: '+j.first_seen_at+(j.published?' · Listed date: '+j.published:'')));
    if(j.rejection_reason)card.append(el('p','reject','Filtered: '+j.rejection_reason));
    const id=el('button','','Copy job ID');id.type='button';id.title=j.fingerprint;id.addEventListener('click',()=>{navigator.clipboard.writeText(j.fingerprint).then(()=>{id.textContent='Copied';}).catch(()=>{id.textContent=j.fingerprint;});});card.append(id);
    const link=el('a','','View vacancy ↗');try{const u=new URL(j.apply_url||j.url);if(u.protocol==='https:'){link.href=u.href;link.target='_blank';link.rel='noopener noreferrer';card.append(link);}}catch(e){}
    root.append(card);
  });
}
async function init(){try{
 const [list,stats]=await Promise.all([fetch('/api/jobs').then(x=>x.json()),fetch('/api/stats').then(x=>x.json())]);jobs=list;
 ['discovered','qualified','alerts_sent','runs'].forEach(k=>$(k).textContent=stats[k]||0);
 $('sources').textContent=(stats.sources||[]).map(x=>`${x.source}: ${x.ok} success / ${x.fail} failure`).join(' · ')||'No sources checked yet';render();
}catch(e){$('jobs').replaceChildren(el('div','empty','Unable to load database. Run a scan first.'));}}
['query','quality','source','progress'].forEach(k=>$(k).addEventListener(k==='query'?'input':'change',render));init();
