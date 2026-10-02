'use strict';
// No embedding access, inference or ranking in the browser; stored bands only.
const inspection={mainReady:0,thumbsReady:0,metadataReady:0,started:0,concurrency:window.INSPECTOR_TEST_CONCURRENCY||6};
class ByteLRU{
 constructor(budget,limit){this.budget=budget;this.limit=limit;this.map=new Map();this.pending=new Map();this.bytes=0;this.pins=new Set()}
 async get(key,loader){
  if(this.map.has(key)){const x=this.map.get(key);this.map.delete(key);this.map.set(key,x);return x.value}
  if(this.pending.has(key))return this.pending.get(key);
  const p=loader().then(x=>{this.pending.delete(key);this.map.set(key,x);this.bytes+=x.bytes;this.trim();return x.value},e=>{this.pending.delete(key);throw e});this.pending.set(key,p);return p;
 }
 trim(){while(this.bytes>this.budget||this.map.size>this.limit){const key=[...this.map.keys()].find(k=>!this.pins.has(k));if(key===undefined)break;const x=this.map.get(key);this.bytes-=x.bytes;this.map.delete(key)}}
}
const summaryCache=new ByteLRU(8*1024*1024,96), detailCache=new ByteLRU(8*1024*1024,12), bandCache=new ByteLRU(1024*1024,32), vectorCache=new ByteLRU(2*1024*1024,16);
let catalog,filtered=[],sourceIndices=[],searchTimer;
async function checked(path,expected){
 if(!expected)throw Error('Missing artifact hash');const response=await fetch(path);if(!response.ok)throw Error(`HTTP ${response.status}: ${path}`);
 const bytes=await response.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==expected)throw Error('Artifact checksum mismatch: '+path);
 return {value:JSON.parse(new TextDecoder().decode(bytes)),bytes:bytes.byteLength};
}
function rowFor(id){return config.queries[id-1]}
async function summary(id){const row=rowFor(id);const s=await summaryCache.get(row.scene_id,()=>checked('summaries/'+row.scene_id+'.json',row.summary_sha256));if(s.scene_id!==row.scene_id)throw Error('Scene binding');return s}
async function heavy(row,s){const d=await detailCache.get(row.scene_id,()=>checked('details/'+row.scene_id+'.json',row.detail_sha256));if(d.scene_id!==s.scene_id||d.source_sha256!==s.source_sha256||d.thematic.binding.scene_id!==s.scene_id)throw Error('Detail binding');return {...s,...d}}
async function vector(s){const template=await vectorCache.get(s.scene_id,async()=>{const doc=new DOMParser().parseFromString(s.svg,'image/svg+xml');if(doc.querySelector('parsererror'))throw Error('SVG invalid');return {value:doc.documentElement,bytes:s.svg.length*2}});return template.cloneNode(true)}
function failure(e){serial++;$('error').hidden=false;$('error').textContent='Inspection stopped: '+e.message;console.error(e)}
function openDetails(s,row,i){
 const d=document.createElement('details');d.className='row detail-host';d.innerHTML='<summary>Details · thematic maps, LC, DEM, relations</summary>';
 let built=false,loading=false;
 d.addEventListener('toggle',async()=>{
  if(!d.open||built||loading)return;loading=true;const message=document.createElement('div');message.textContent='Loading verified details…';d.append(message);
  try{
   const full=await heavy(row,s);const rasters=document.createElement('div');rasters.className='raster-pair';rasters.innerHTML=rasterBlock(full,'LC')+rasterBlock(full,'DEM');d.append(rasters);
   // Exact original thematic renderer, only on first-open; reopen reuses DOM.
   d.append(details(full,i));const rel=document.createElement('div');rel.className='display-note';rel.textContent='Stored relation masks: '+JSON.stringify(full.relation_masks);d.append(rel);
   await drawLC(d.querySelector('canvas'));const img=rasters.querySelector('img');await img.decode();if(img.naturalWidth!==17||img.naturalHeight!==17)throw Error('DEM dimensions');
   message.remove();built=true;d.dataset.loaded='true';
  }catch(e){message.textContent=e.message;failure(e)}finally{loading=false}
 });return d;
}
function expand(data,mode){const entry=data.modes[mode];if(!entry)throw Error('Missing mode');return {candidate_count:entry.candidate_count,bands:Object.fromEntries(Object.entries(entry.bands).map(([band,rs])=>[band,rs.map(([rank,index,similarity,geographic_distance_m])=>({query_id:data.query_scene_id,model_id:'cmp_FM',retrieval_mode:mode,rank,gallery_scene_id:rowFor(index).scene_id,scene_index:index,similarity,geographic_distance_m}))]))}}
async function render(){
 const token=++serial;inspection.started=performance.now();inspection.mainReady=inspection.thumbsReady=inspection.metadataReady=0;$('error').hidden=true;$('progress').textContent='Loading band metadata…';$('comparison').replaceChildren();
 const q=config.queries[queryIndex],mode=$('mode').value;
 const data=await bandCache.get(q.scene_id,()=>checked('bands/'+String(q.query_index).padStart(4,'0')+'.json',q.band_sha256));if(token!==serial)return;
 if(data.query_scene_id!==q.scene_id||data.configuration!=='cmp_FM'||data.checkpoint!==config.checkpoint||data.embedding_manifest!==config.embedding_manifest)throw Error('Ranking lineage binding');activeEvidence=expand(data,mode);inspection.metadataReady=performance.now();
 const cols=bandColumns();cols[0].item.scene_index=q.query_index;summaryCache.pins=new Set(cols.map(c=>c.item.gallery_scene_id));
 const loaded=await Promise.all(cols.map(c=>summary(c.item.scene_index)));if(token!==serial)return;
 const vectors=await Promise.all(loaded.map(vector));if(token!==serial)return;
 scenes=loaded;rows=cols.slice(1).map(c=>c.item);const fragment=document.createDocumentFragment();
 cols.forEach((col,i)=>{
  const s=loaded[i],item=col.item,el=document.createElement('section');el.className='column';el.dataset.scene=s.scene_id;el.dataset.rank=item.rank||'';el.dataset.band=col.key;
  const meta=item.rank?`Rank ${item.rank} · cos ${item.similarity.toFixed(6)} · ${(item.geographic_distance_m/1000).toFixed(2)} km`:'Fixed evaluation original';
  el.innerHTML=`<div class="column-head"><h2>${col.title}</h2><div class="rank-meta" title="${item.rank?`Exact cosine ${item.similarity}; ${item.geographic_distance_m} m`:meta}">${meta}</div><div class="scene-id">${esc(s.scene_id)}</div></div>`;
  if(col.strip){const strip=document.createElement('div');strip.className='strip';strip.innerHTML=col.strip.map((x,j)=>`<button data-band="${col.key}" data-index="${j}" data-scene="${x.gallery_scene_id}" data-scene-index="${x.scene_index}" data-rank="${x.rank}" class="${j===bandsSelection[col.key]?'selected':''}" title="Rank ${x.rank} · ${esc(x.gallery_scene_id)} · cosine ${x.similarity} · ${x.geographic_distance_m} m"><i class="pending"></i><span>#${x.rank}</span></button>`).join('');el.append(strip)}else{const spacer=document.createElement('div');spacer.className='strip-spacer';el.append(spacer)}
  el.insertAdjacentHTML('beforeend',S10Locations.block(s));const box=document.createElement('div');box.className='row';box.innerHTML='<div class="row-title">Vector data</div><div class="map-frame vector-map"></div>';box.querySelector('.vector-map').append(vectors[i]);el.append(box);
  el.insertAdjacentHTML('beforeend',bandRow('Attributes & spatial relations',`<div class="summary">${Object.entries(s.counts).map(([k,v])=>`<div><b>${v}</b>${esc(k)}</div>`).join('')}<div><b>${s.ordered_edges}</b>ordered edges</div></div><div class="display-note">EPSG:5186 · ${s.center.map(x=>x.toFixed(2)).join(', ')}</div>`));el.append(openDetails(s,rowFor(item.scene_index),i));fragment.append(el);
 });
 $('comparison').replaceChildren(fragment);view={scale:1,dx:0,dy:0};bindVectorInteraction();const buttons=[...document.querySelectorAll('.strip button')];buttons.forEach(b=>b.onclick=()=>{bandsSelection[b.dataset.band]=+b.dataset.index;render().catch(failure)});
 $('caseTitle').textContent=`Query ${q.query_index} / 9000 · cmp_FM · ${mode}`;$('identity').textContent=`${activeEvidence.candidate_count} eligible candidates · ${q.scene_id} · ${$('preset').selectedOptions[0].text}`;$('query').value=q.query_index;
 const url=new URL(location);url.searchParams.set('query',q.query_index);url.searchParams.set('model','cmp_FM');url.searchParams.set('mode',mode);url.searchParams.set('preset',$('preset').value);history.replaceState(null,'',url);updateNavigation();
 await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(token!==serial)return;inspection.mainReady=performance.now();inspection.criticalResources=performance.getEntriesByType('resource').filter(r=>r.startTime>=inspection.started).map(r=>r.toJSON());$('progress').textContent='Main cards ready · thumbnails loading…';
 setTimeout(()=>thumbnails(buttons,token).catch(e=>{if(token===serial)failure(e)}),0);
}
async function thumbnails(buttons,token){let cursor=0;async function work(){while(cursor<buttons.length&&serial===token){const button=buttons[cursor++],s=await summary(+button.dataset.sceneIndex);if(serial!==token)return;const svg=await vector(s);if(serial!==token)return;button.querySelector('.pending').replaceWith(svg);button.dataset.loaded='true';await new Promise(r=>setTimeout(r,0))}}await Promise.all(Array.from({length:inspection.concurrency},work));if(serial===token){await new Promise(r=>requestAnimationFrame(r));inspection.thumbsReady=performance.now();$('progress').textContent='All thumbnails ready · details load only when opened'}}
function updateNavigation(){const pos=filtered.indexOf(queryIndex+1);$('prev').disabled=pos<=0;$('next').disabled=pos<0||pos===filtered.length-1}
function filters(){const text=$('search').value.trim().toLowerCase(),min=+$('minimum').value||0;sourceIndices=$('preset').value==='ALL'?config.queries.map(r=>r.query_index):catalog.presets[$('preset').value];filtered=sourceIndices.filter(i=>{const r=rowFor(i);return r.n_obj>=min&&(!text||[r.scene_id,r.sigungu,r.dong].some(x=>(x||'').toLowerCase().includes(text)))});$('matchCount').textContent=`${filtered.length.toLocaleString()} matches`;$('searchResults').replaceChildren();for(const i of filtered.slice(0,30)){const r=rowFor(i),b=document.createElement('button');b.textContent=`${i} · ${r.scene_id} · ${r.sigungu||''} ${r.dong||''} · B/R/P ${r.n_buildings}/${r.n_roads}/${r.n_pois}`;b.onclick=()=>go(i);$('searchResults').append(b)}updateNavigation()}
function go(i){if(!Number.isInteger(i)||i<1||i>9000){$('query').value=queryIndex+1;return}queryIndex=i-1;bandsSelection={top:0,middle:0,bottom:0};render().catch(failure)}
async function init(){
 config=(await checked('config.json',document.body.dataset.configSha)).value;catalog=(await checked('index.json',config.index_sha256)).value;config.queries=catalog.rows.map(a=>Object.fromEntries(catalog.columns.map((k,i)=>[k,a[i]])));if(config.queries.length!==9000)throw Error('Query population');
 const params=new URL(location).searchParams;if(params.has('model')&&params.get('model')!=='cmp_FM')throw Error('This prototype exposes final FM only');if(catalog.presets[params.get('preset')])$('preset').value=params.get('preset');if(['standard','nonlocal'].includes(params.get('mode')))$('mode').value=params.get('mode');
 $('go').onclick=()=>go(+$('query').value);$('query').onchange=()=>go(+$('query').value);$('prev').onclick=()=>go(filtered[filtered.indexOf(queryIndex+1)-1]);$('next').onclick=()=>go(filtered[filtered.indexOf(queryIndex+1)+1]);$('random').onclick=()=>{if(filtered.length)go(filtered[Math.floor(Math.random()*filtered.length)])};
 $('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(filters,120)};$('minimum').oninput=filters;$('preset').onchange=()=>{filters();if(filtered.length){$('mode').value=$('preset').value.startsWith('NONLOCAL')?'nonlocal':'standard';go(filtered[0])}};$('mode').onchange=()=>{bandsSelection={top:0,middle:0,bottom:0};render().catch(failure)};
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));$('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};updateZoom()};window.addEventListener('resize',()=>document.querySelectorAll('.lc-canvas').forEach(c=>drawLC(c).catch(failure)));
 $('provenanceText').textContent=`Supplemental ${config.generation}\n${config.configuration} / ${config.checkpoint}\nEmbedding ${config.embedding_manifest}\n9000 accepted evaluation originals; self excluded. Non-local distance >= 2000m.\nCosine descending, exact ties lexical scene ID. Rank1 1; upper 2–11; middle floor((N−10)/2)+1…+10; bottom N−9…N.\nNo browser ranking computation, model inference or model selection. Presets retain existing ordered membership; they filter query navigation, not gallery candidates. HIGH/LOW are cosine extremes, not correctness labels. OBJ20 is display-only.\nLC stored 100×100 class fractions, DEM stored standardized 17×17, not metres. All original thematic data remains under Details. This supplemental all-query inspector does not redefine the thesis query protocol.`;
 filters();const scene=params.get('scene'),found=scene?config.queries.find(r=>r.scene_id===scene):null;go(found?found.query_index:Math.min(9000,Math.max(1,Number(params.get('query'))||1)));
}
init().catch(failure);
