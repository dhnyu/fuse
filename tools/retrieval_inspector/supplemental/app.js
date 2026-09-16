'use strict';
const $=id=>document.getElementById(id);
const esc=v=>String(v).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let config, queryIndex=+document.body.dataset.query, chosen=1, serial=0, scenes=[], rows=[];
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
function fail(error){serial++;$('error').hidden=false;$('error').textContent='Inspection stopped: '+error.message;$('focus').innerHTML='';$('strip').innerHTML='';$('summary').innerHTML='';console.error(error)}
function option(value,text){return `<option value="${esc(value)}">${esc(text)}</option>`}
function modelOptions(){const old=$('model').value;$('model').innerHTML=config.models.filter(m=>$('group').value==='all'||m.group===$('group').value).map(m=>option(m.id,m.id.replace(/^cmp_/,''))).join('');if([...$('model').options].some(o=>o.value===old))$('model').value=old}
function categoryColor(label){const colors=['#407b75','#607c9b','#a57b52','#80749b','#68884f','#a76c78'];let h=0;for(const c of label)h=(h*31+c.codePointAt(0))>>>0;return colors[h%colors.length]}
function chart(title,items){
 const isLC=title==='Land cover composition';const all=[...items].sort((a,b)=>b.value-a.value);const unknown=all.filter(x=>x.label==='Unknown / missing');const regular=all.filter(x=>x.label!=='Unknown / missing');const shown=[...regular.slice(0,5),...unknown];
 if(regular.length>5)shown.push({label:'Other',value:regular.slice(5).reduce((s,x)=>s+x.value,0),color:'#aeb9be'});
 const max=Math.max(1,...shown.map(x=>x.value));
 return `<div class="chart"><h5>${esc(title)}${isLC?' · %':''}</h5>${shown.length?shown.map(x=>`<div class="bar-row" data-value="${x.value}" title="${esc(x.label)}: ${x.value}"><div class="bar-label"><span>${esc(x.label)}</span><b>${isLC?x.value.toFixed(1)+'%':x.value}</b></div><div class="track"><div class="fill" style="width:${x.value/max*100}%;background:${x.color||categoryColor(x.label)}"></div></div></div>`).join(''):'<p class="empty">No observed values</p>'}</div>`;
}
function map(s,large=false){return `<div class="map ${large?'large-map':''}">${s.svg}</div>`}
function caption(i){return i===0?'Fixed query':`Rank ${i}${i===1?' · Most similar':''}`}
function meta(i){return i===0?'Evaluation original':`cos ${rows[i-1].similarity.toFixed(6)} · ${(rows[i-1].geographic_distance_m/1000).toFixed(2)} km`}
function panel(s,i){return `<article class="scene-panel" data-scene="${esc(s.scene_id)}"><h3>${caption(i)}</h3><div class="scene-meta"><div class="scene-id">${esc(s.scene_id)}</div><b>${meta(i)}</b> · ${esc($('mode').selectedOptions[0].text)}</div><section class="block"><h4>Vector data</h4>${map(s,true)}</section><section class="block"><h4>Raster data</h4><div class="raster-grid"><figure data-raster="LC"><img src="${s.lc}" alt="Stored land cover fractions"><figcaption>LC · 100 × 100 · ${s.lc_valid_cells} valid cells<br>Fraction-blended categorical colours</figcaption></figure><figure data-raster="DEM"><img src="${s.dem}" alt="Stored standardized DEM"><figcaption>DEM · 17 × 17 · ${s.dem_valid_cells} valid cells<br>Standardized value: blue −3 → orange +3</figcaption></figure></div></section><section class="block"><h4>Attributes & spatial relations</h4><div class="metrics">${Object.entries(s.counts).map(([k,v])=>`<div>${esc(k)}<b>${v}</b></div>`).join('')}<div>Ordered edges<b>${s.ordered_edges}</b></div></div><p class="note">Center EPSG:5186 (m): ${s.center.map(x=>x.toFixed(2)).join(', ')}</p><details><summary>Stored relation-mask counts</summary>${chart('Relation bit mask (stored codes)',s.relation_masks)}</details></section><details open class="block"><summary>Detailed summaries</summary><div class="chart-grid">${Object.entries(s.charts).map(([k,v])=>chart(k,v)).join('')}</div><p class="note">Top 5 categories + Other. Unknown values retained. LC % uses valid-support-weighted stored fractions.</p></details></article>`}
function focus(){document.querySelectorAll('.thumb').forEach((b,i)=>b.classList.toggle('selected',i===chosen));$('focus').innerHTML=panel(scenes[0],0)+panel(scenes[chosen],chosen)}
async function render(){
 const token=++serial;$('error').hidden=true;$('strip').innerHTML='';$('focus').innerHTML='';$('summary').textContent='Verifying display artifacts…';
 const q=config.queries[queryIndex], model=$('model').value, mode=$('mode').value;
 const data=await artifact('queries/'+q.scene_id+'.json');
 const nextRows=data[model]?.[mode];if(!nextRows||nextRows.length!==5||nextRows.some((r,i)=>r.rank!==i+1||r.query_id!==q.scene_id||r.model_id!==model||r.retrieval_mode!==mode))throw Error('Published Top-5 binding invalid');
 const nextScenes=await Promise.all([q.scene_id,...nextRows.map(r=>r.gallery_scene_id)].map(id=>artifact('scenes/'+id+'.json')));
 if(token!==serial)return;rows=nextRows;scenes=nextScenes;
 if(scenes.some((s,i)=>s.scene_id!==[q.scene_id,...rows.map(r=>r.gallery_scene_id)][i]))throw Error('Scene binding invalid');
 $('prev').disabled=queryIndex===0;$('next').disabled=queryIndex===config.queries.length-1;
 $('summary').innerHTML=[['Query',`${queryIndex+1} / ${config.queries.length}`],['Selected model',model],['Common gallery','9,000 originals'],['Published / displayed','Top 50 / Top 5'],['Retrieval setting',$('mode').selectedOptions[0].text],['Cosine similarity','Higher = more similar']].map(([k,v])=>`<div><small>${esc(k)}</small><b>${esc(v)}</b></div>`).join('');
 $('strip').innerHTML=scenes.map((s,i)=>`<button class="thumb" data-rank="${i}" data-scene="${esc(s.scene_id)}" aria-label="Enlarge ${caption(i)}"><h3>${caption(i)}</h3>${map(s)}<p>${meta(i)}<br><span class="scene-id">${esc(s.scene_id)}</span></p></button>`).join('');
 document.querySelectorAll('.thumb').forEach((b,i)=>b.onclick=()=>{chosen=i||1;focus()});focus();
 const url=new URL(location);url.searchParams.set('model',model);url.searchParams.set('mode',mode);history.replaceState(null,'',url);
}
function changeQuery(i){queryIndex=i;$('query').value=i;chosen=1;render().catch(fail);const url=new URL(location);url.pathname=url.pathname.replace(/[^/]*$/,`query_${String(config.queries[i].query_index).padStart(2,'0')}.html`);history.replaceState(null,'',url)}
async function init(){
 config=await verified('config.json',document.body.dataset.configSha);
 $('query').innerHTML=config.queries.map((q,i)=>option(i,`${q.query_index}. ${q.scene_id}`)).join('');$('query').value=queryIndex;
 modelOptions();const params=new URL(location).searchParams;if(config.models.some(m=>m.id===params.get('model')))$('model').value=params.get('model');if(['standard','nonlocal'].includes(params.get('mode')))$('mode').value=params.get('mode');
 $('query').onchange=()=>changeQuery(+$('query').value);$('prev').onclick=()=>changeQuery(queryIndex-1);$('next').onclick=()=>changeQuery(queryIndex+1);
 $('group').onchange=()=>{modelOptions();render().catch(fail)};for(const id of ['model','mode'])$(id).onchange=()=>render().catch(fail);
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));
 $('provenance').textContent=`Parent acceptance: ${config.acceptance}. Supplemental display only. 28 models, 30 fixed queries, common 9,000 gallery; published standard/non-local Top 50 unchanged. Payload checksums verified before display.`;
 await render();
}
init().catch(fail);
