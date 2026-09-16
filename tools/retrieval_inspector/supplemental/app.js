'use strict';
// Shell structure and interactions follow augmentation_inspector: section/grid/panel,
// linked vector wheel/drag, Reset zoom, Provenance and a shared fixed tooltip.
const $=id=>document.getElementById(id);
const esc=v=>String(v).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let config, queryIndex=+document.body.dataset.query, serial=0, scenes=[], rows=[];
let view={scale:1,dx:0,dy:0}, drag=null;
const cache=new Map();
async function verified(path,sha){
  if(!sha)throw Error('Missing artifact identity: '+path);
  const res=await fetch(path);if(!res.ok)throw Error('Artifact unavailable: '+path);
  const bytes=await res.arrayBuffer();
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
  if(hash!==sha)throw Error('Artifact checksum mismatch: '+path);
  return JSON.parse(new TextDecoder().decode(bytes));
}
function artifact(path){if(!cache.has(path))cache.set(path,verified(path,config.files[path]));return cache.get(path)}
function clear(){for(const id of ['vectorGrid','rasterGrid','summaryGrid','detailGrid'])$(id).replaceChildren()}
function fail(error){serial++;clear();$('error').hidden=false;$('error').textContent='Inspection stopped: '+error.message;$('caseTitle').textContent='Artifact error';console.error(error)}
function option(value,text){return `<option value="${esc(value)}">${esc(text)}</option>`}
function modelOptions(){const old=$('model').value;$('model').innerHTML=config.models.filter(m=>$('group').value==='all'||m.group===$('group').value).map(m=>option(m.id,m.id.replace(/^cmp_/,''))).join('');if([...$('model').options].some(o=>o.value===old))$('model').value=old}
function caption(i){return i===0?'Query':`Rank ${i}${i===1?' / Most similar':''}`}
function panel(s,i){let el=document.createElement('div');el.className='panel';el.dataset.scene=s.scene_id;el.dataset.rank=i;el.innerHTML=`<h3 title="${esc(s.scene_id)}">${caption(i)}</h3>`;return el}
function svgMap(svg,kind){return `<div class="canvas-wrap ${kind}">${svg}</div>`}
function legend(items,percent=false){return `<div class="categorical-legend">${items.length?items.map(x=>`<div class="legend-row" data-value="${percent?x.value:x.count}" title="${esc(x.label)}"><i style="--category-color:${x.color}"></i><span>${esc(x.label)}</span><b>${percent?x.value.toFixed(1)+'%':x.count}</b></div>`).join(''):'<span class="empty-state">No observed objects</span>'}</div>`}
function thematicMap(s,title){
 const theme=s.thematic.maps[title], doc=new DOMParser().parseFromString(s.svg,'image/svg+xml');
 if(doc.querySelector('parsererror'))throw Error('Invalid stored SVG');
 const svg=doc.documentElement, group=[...svg.children].find(x=>x.localName==='g');
 if(!group||group.children.length!==s.thematic.binding.entity_count)throw Error('SVG/entity binding mismatch');
 const assignment=new Map(theme.entities.map(e=>[e.svg_index,e]));
 [...group.children].forEach((node,index)=>{
   const item=assignment.get(index);if(!item){node.remove();return}
   node.setAttribute('data-entity-id',item.entity_id);node.setAttribute('data-category-index',item.category_index);
   node.setAttribute('data-color',item.color);
   // Preserve every geometry attribute and existing transform; change paint only.
   for(const shape of [node,...node.querySelectorAll('*')]){
     if(theme.layer==='R'&&shape.hasAttribute('stroke'))shape.setAttribute('stroke',item.color);
     if(theme.layer!=='R'&&shape.hasAttribute('fill')&&shape.getAttribute('fill')!=='none')shape.setAttribute('fill',item.color);
   }
   const text=doc.createElementNS('http://www.w3.org/2000/svg','title');text.textContent=`${item.entity_id} · ${item.label}`;node.append(text);
 });
 svg.setAttribute('aria-label',title+' · '+s.scene_id);
 return new XMLSerializer().serializeToString(svg);
}
function details(s,i){
 const el=panel(s,i);const maps=['POI categories · L1','Land cover composition','Building use','Building structure','Road rank','Road lane'];
 const d=document.createElement('details');d.open=true;d.innerHTML='<summary class="detail-toggle">Detailed summaries</summary><div class="thematic-grid"></div>';
 const grid=d.querySelector('.thematic-grid');
 for(const title of maps){
   const item=document.createElement('section');item.className='thematic-item';item.dataset.theme=title;
   if(title==='Land cover composition'){
     item.dataset.raster='LC';item.innerHTML=`<h3>Land cover</h3><div class="canvas-wrap"><img src="${s.lc}" alt="Existing land-cover display raster"></div>${legend(s.charts[title],true)}`;
   }else{
     const theme=s.thematic.maps[title];item.dataset.thematicLayer=theme.layer;
     item.innerHTML=`<h3>${esc(title)}</h3>${svgMap(thematicMap(s,title),'thematic-map')}${legend(theme.legend)}`;
   }
   grid.append(item);
 }
 el.append(d);return el;
}
function renderPanels(){
 scenes.forEach((s,i)=>{
   const v=panel(s,i);
   const metadata=i===0?'Evaluation original':`<span title="Exact stored cosine: ${rows[i-1].similarity}">cos ${rows[i-1].similarity.toFixed(6)}</span><br><span title="Exact stored metres: ${rows[i-1].geographic_distance_m}">${(rows[i-1].geographic_distance_m/1000).toFixed(2)} km</span>`;
   v.innerHTML+=`<div class="scene-meta"><code>${esc(s.scene_id)}</code>${metadata}<br>${esc($('mode').selectedOptions[0].text)}</div>${svgMap(s.svg,'vector-map')}`;
   $('vectorGrid').append(v);
   const r=panel(s,i);r.innerHTML+=`<div data-raster="LC"><div class="raster-title">Land cover · stored fractions</div><div class="canvas-wrap"><img src="${s.lc}" alt="Land cover"></div></div><div data-raster="DEM"><div class="raster-title">DEM · stored standardized mean</div><div class="canvas-wrap"><img src="${s.dem}" alt="Standardized DEM"></div><div class="display-note">Blue −3 → orange +3 · not elevation metres</div></div>`;$('rasterGrid').append(r);
   const a=panel(s,i);a.innerHTML+=`<div class="summary">${Object.entries(s.counts).map(([k,v])=>`<div><b>${v}</b>${esc(k)}</div>`).join('')}<div><b>${s.ordered_edges}</b>ordered edges</div></div><div class="display-note">Center EPSG:5186 (m)<br>${s.center.map(x=>x.toFixed(2)).join(', ')}</div><details><summary class="detail-toggle">Stored relation masks</summary><div class="display-note">${s.relation_masks.map(x=>`${esc(x.label)}: ${x.value}`).join(' · ')}</div></details>`;$('summaryGrid').append(a);
   $('detailGrid').append(details(s,i));
 });
 bindVectorInteraction();
}
function updateZoom(){document.querySelectorAll('.vector-map svg').forEach(el=>{el.style.transform=`translate(${view.dx}px,${view.dy}px) scale(${view.scale})`})}
function bindVectorInteraction(){
 document.querySelectorAll('.vector-map').forEach(el=>{
   el.onwheel=e=>{e.preventDefault();const factor=e.deltaY<0?1.2:1/1.2;view.scale=Math.max(1,Math.min(12,view.scale*factor));updateZoom()};
   el.onpointerdown=e=>{drag=[e.clientX,e.clientY,view.dx,view.dy];el.setPointerCapture(e.pointerId)};
   el.onpointermove=e=>{if(drag){view.dx=drag[2]+e.clientX-drag[0];view.dy=drag[3]+e.clientY-drag[1];updateZoom()}};
   el.onpointerup=el.onpointercancel=()=>drag=null;
 });updateZoom();
}
async function render(){
 const token=++serial;clear();$('error').hidden=true;$('caseTitle').textContent='Verifying display artifacts…';
 const q=config.queries[queryIndex], model=$('model').value, mode=$('mode').value;
 const data=await artifact('queries/'+q.scene_id+'.json'), nextRows=data[model]?.[mode];
 if(!nextRows||nextRows.length!==5||nextRows.some((r,i)=>r.rank!==i+1||r.query_id!==q.scene_id||r.model_id!==model||r.retrieval_mode!==mode))throw Error('Published Top-5 binding invalid');
 const ids=[q.scene_id,...nextRows.map(r=>r.gallery_scene_id)], nextScenes=await Promise.all(ids.map(id=>artifact('scenes/'+id+'.json')));
 if(token!==serial)return;
 if(nextScenes.some((s,i)=>s.scene_id!==ids[i]||s.thematic.binding.scene_id!==ids[i]))throw Error('Scene binding invalid');
 rows=nextRows;scenes=nextScenes;view={scale:1,dx:0,dy:0};
 $('prev').disabled=queryIndex===0;$('next').disabled=queryIndex===config.queries.length-1;
 $('caseTitle').textContent=`Query ${queryIndex+1} / ${config.queries.length} · ${model} · ${$('mode').selectedOptions[0].text}`;
 $('identity').textContent='9,000 gallery · Top 5 of stored Top 50 · cosine: higher = more similar';
 renderPanels();
 const url=new URL(location);url.searchParams.set('model',model);url.searchParams.set('mode',mode);history.replaceState(null,'',url);
}
function changeQuery(i){queryIndex=i;$('query').value=i;render().catch(fail);const url=new URL(location);url.pathname=url.pathname.replace(/[^/]*$/,`query_${String(config.queries[i].query_index).padStart(2,'0')}.html`);history.replaceState(null,'',url)}
async function init(){
 config=await verified('config.json',document.body.dataset.configSha);
 $('query').innerHTML=config.queries.map((q,i)=>option(i,`${q.query_index}. ${q.scene_id}`)).join('');$('query').value=queryIndex;
 modelOptions();const params=new URL(location).searchParams;if(config.models.some(m=>m.id===params.get('model')))$('model').value=params.get('model');if(['standard','nonlocal'].includes(params.get('mode')))$('mode').value=params.get('mode');
 $('query').onchange=()=>changeQuery(+$('query').value);$('prev').onclick=()=>changeQuery(queryIndex-1);$('next').onclick=()=>changeQuery(queryIndex+1);
 $('group').onchange=()=>{modelOptions();render().catch(fail)};for(const id of ['model','mode'])$(id).onchange=()=>render().catch(fail);
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));
 $('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};updateZoom()};$('toggleProvenance').onclick=()=>$('provenance').classList.toggle('hidden');
 $('provenanceText').textContent=`${config.acceptance}\nSupplemental display only. No selection or scientific recomputation.\nGeometry: unchanged accepted SVG; attributes: same-P3-payload, stored per-entity categorical values.\nAll models show common original scene context, including modalities they may not consume.\nLC uses the existing display's fraction-blended palette and valid-support-weighted legend; no new classification.\nDEM is a stored standardized tensor, not raw metres. No raster resampling.\nRoad lane: raw LANES from the exact accepted P3 parent payload, bound by payload SHA and ordered entity IDs. No spatial matching, inverse normalization or inference.\nS09, accepted S10 and S11 unchanged.`;
 await render();
}
init().catch(fail);
