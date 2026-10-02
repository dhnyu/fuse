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
const summaryCache=new ByteLRU(8*1024*1024,96), detailCache=new ByteLRU(8*1024*1024,12), bandCache=new ByteLRU(2*1024*1024,20), vectorCache=new ByteLRU(2*1024*1024,16);
let catalog,filtered=[],displayOrder=[],searchTimer,activeOrder,navSerial=0,navigationReady=false;
const orderCache=new ByteLRU(3*1024*1024,4),lcCache=new ByteLRU(2*1024*1024,64);
async function checked(path,expected){
 if(!expected)throw Error('Missing artifact hash');const response=await fetch(path);if(!response.ok)throw Error(`HTTP ${response.status}: ${path}`);
 const bytes=await response.arrayBuffer();const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');if(hash!==expected)throw Error('Artifact checksum mismatch: '+path);
 return {value:path.endsWith('.bin')?bytes:JSON.parse(new TextDecoder().decode(bytes)),bytes:bytes.byteLength};
}
function rowFor(id){return config.queries[id-1]}
async function summary(id){const row=rowFor(id);const s=await summaryCache.get(row.scene_id,()=>checked('summaries/'+row.scene_id+'.json',row.summary_sha256));if(s.scene_id!==row.scene_id)throw Error('Scene binding');return s}
async function heavy(row,s){const d=await detailCache.get(row.scene_id,()=>checked('details/'+row.scene_id+'.json',row.detail_sha256));if(d.scene_id!==s.scene_id||d.source_sha256!==s.source_sha256||d.thematic.binding.scene_id!==s.scene_id)throw Error('Detail binding');const color=await lcCache.get(row.scene_id,()=>checked('lc/'+row.scene_id+'.json',row.lc_sha256));if(color.scene_id!==s.scene_id||color.source_sha256!==s.source_sha256||color.palette_sha256!==config.palette_sha256)throw Error('LC binding');return {...s,...d,lc:color.lc,charts:{...d.charts,'Land cover composition':color.chart}}}
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
function decodeShard(buffer,q,mode){
 const view=new DataView(buffer);if(new TextDecoder().decode(buffer.slice(0,8))!=='S10BND01')throw Error('Band schema');
 const start=view.getUint32(8,true),count=view.getUint32(12,true);if(q<start||q>=start+count||buffer.byteLength!==16+1000*count)throw Error('Band bounds');
 let offset=16+(q-start)*1000+(mode==='nonlocal'?500:0);const n=view.getUint16(offset,true);if(view.getUint16(offset+2,true)!==0)throw Error('Band reserved');offset+=4;
 const bands={};for(const [key,length] of [['most',1],['top',10],['middle',10],['bottom',10]]){bands[key]=[];for(let i=0;i<length;i++){
  const rank=view.getUint16(offset,true),index=view.getUint16(offset+2,true),similarity=view.getFloat32(offset+4,true),geographic_distance_m=view.getFloat64(offset+8,true);offset+=16;
  if(index===q||index<1||index>9000||!Number.isFinite(similarity)||(mode==='nonlocal'&&geographic_distance_m<2000))throw Error('Band candidate');
  bands[key].push({query_id:rowFor(q).scene_id,model_id:$('model').value,retrieval_mode:mode,rank,gallery_scene_id:rowFor(index).scene_id,scene_index:index,similarity,geographic_distance_m});
 }}return {candidate_count:n,bands};
}
async function ranking(q,model,mode){
 const registry=config.models.find(m=>m.configuration===model);if(!registry||activeOrder.configuration!==model||activeOrder.checkpoint!==registry.checkpoint||activeOrder.embedding_manifest!==registry.embedding_manifest)throw Error('Model lineage');
 const shard=activeOrder.shards[Math.floor((q-1)/config.shard_size)];const raw=await bandCache.get(shard.path,()=>checked('bands/'+shard.path,shard.sha256));return decodeShard(raw,q,mode);
}
async function render(){
 if(!navigationReady)return;const token=++serial;inspection.started=performance.now();inspection.mainReady=inspection.thumbsReady=inspection.metadataReady=0;$('error').hidden=true;$('progress').textContent='Loading band metadata…';$('comparison').replaceChildren();
 const q=config.queries[queryIndex],mode=$('mode').value,model=$('model').value;
 const evidence=await ranking(q.query_index,model,mode);if(token!==serial)return;activeEvidence=evidence;inspection.metadataReady=performance.now();
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
 updateNavigation();
 await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));if(token!==serial)return;inspection.mainReady=performance.now();inspection.criticalResources=performance.getEntriesByType('resource').filter(r=>r.startTime>=inspection.started).map(r=>r.toJSON());$('progress').textContent='Main cards ready · thumbnails loading…';
 setTimeout(()=>thumbnails(buttons,token).catch(e=>{if(token===serial)failure(e)}),0);
}
async function thumbnails(buttons,token){let cursor=0;async function work(){while(cursor<buttons.length&&serial===token){const button=buttons[cursor++],s=await summary(+button.dataset.sceneIndex);if(serial!==token)return;const svg=await vector(s);if(serial!==token)return;button.querySelector('.pending').replaceWith(svg);button.dataset.loaded='true';await new Promise(r=>setTimeout(r,0))}}await Promise.all(Array.from({length:inspection.concurrency},work));if(serial===token){await new Promise(r=>requestAnimationFrame(r));inspection.thumbsReady=performance.now();$('progress').textContent='All thumbnails ready · details load only when opened'}}
function syncURL(){const url=new URL(location);for(const key of ['query','preset'])url.searchParams.delete(key);for(const [k,v] of Object.entries({model:$('model').value,mode:$('mode').value,order:$('order').value,pos:displayOrder.indexOf(queryIndex+1)+1,scene:rowFor(queryIndex+1).scene_id}))url.searchParams.set(k,v);history.replaceState(null,'',url)}
function updateNavigation(){
 const pos=displayOrder.indexOf(queryIndex+1),q=rowFor(queryIndex+1);$('prev').disabled=!navigationReady||pos<=0;$('next').disabled=!navigationReady||pos===8999;$('position').value=pos+1;$('global').value=q.query_index;
 $('caseTitle').textContent=`Position ${pos+1} / 9000 · Global index ${q.query_index} · ${$('model').value} · ${$('mode').value}`;
 const score=activeOrder?.modes[$('mode').value]?.scores[q.query_index-1];$('identity').textContent=`${q.scene_id} · Query Rank-1 cosine ${score??'loading'} · ${activeEvidence?.candidate_count??'…'} eligible candidates`;
 syncURL();
}
function filters(){
 const text=$('search').value.trim().toLowerCase();filtered=displayOrder.filter(i=>{const r=rowFor(i);return !text||[r.scene_id,r.sigungu,r.dong].some(x=>(x||'').toLowerCase().includes(text))});$('matchCount').textContent=`${filtered.length.toLocaleString()} search matches · population 9,000`;$('searchResults').replaceChildren();
 for(const i of filtered.slice(0,30)){const r=rowFor(i),b=document.createElement('button');b.textContent=`Global ${i} · ${r.scene_id} · ${r.sigungu||''} ${r.dong||''} · B/R/P ${r.n_buildings}/${r.n_roads}/${r.n_pois}`;b.onclick=()=>go(i);$('searchResults').append(b)}
}
function setOrder(){
 if(!navigationReady)return;const t=performance.now(),mode=$('mode').value,order=$('order').value;displayOrder=order==='original'?config.queries.map(r=>r.query_index):activeOrder.modes[mode][order];if(displayOrder.length!==9000)throw Error('Order population');filters();updateNavigation();inspection.orderUpdateMs=performance.now()-t;
}
function go(i){if(!navigationReady||!Number.isInteger(i)||i<1||i>9000)return;queryIndex=i-1;bandsSelection={top:0,middle:0,bottom:0};render().catch(failure)}
async function switchModelMode(initial=false){
 const token=++navSerial;++serial;navigationReady=false;$('prev').disabled=$('next').disabled=true;const started=performance.now(),model=config.models.find(m=>m.configuration===$('model').value);if(!model)throw Error('Unknown model');
 const orders=await orderCache.get(model.configuration,()=>checked('bands/'+model.orders,model.orders_sha256));if(token!==navSerial)return;
 if(orders.configuration!==model.configuration||orders.checkpoint!==model.checkpoint||orders.embedding_manifest!==model.embedding_manifest||orders.generation!==config.generation)throw Error('Order lineage binding');activeOrder=orders;navigationReady=true;
 if(initial){const params=new URL(location).searchParams,scene=params.get('scene');const q=scene?config.queries.find(r=>r.scene_id===scene):null;if(scene&&!q)throw Error('Unknown scene');setOrder();if(q)queryIndex=q.query_index-1;else{const pos=Number(params.get('pos')||1);if(!Number.isInteger(pos)||pos<1||pos>9000)throw Error('Invalid position');queryIndex=displayOrder[pos-1]-1}}
 setOrder();inspection.modelOrderMs=performance.now()-started;bandsSelection={top:0,middle:0,bottom:0};await render();
}
async function init(){
 config=(await checked('config.json',document.body.dataset.configSha)).value;catalog=(await checked('index.json',config.index_sha256)).value;config.queries=catalog.rows.map(a=>Object.fromEntries(catalog.columns.map((k,i)=>[k,a[i]])));if(config.queries.length!==9000||config.models.length!==28)throw Error('Population/registry');
 for(const [group,label] of [['COMPARISON','Final / comparison / ablation'],['OFAT','Hyperparameter / OFAT']]){const opt=document.createElement('optgroup');opt.label=label;for(const m of config.models.filter(m=>group==='COMPARISON'?m.group==='COMPARISON':m.group!=='COMPARISON')){const o=document.createElement('option');o.value=m.configuration;o.textContent=m.label;opt.append(o)}$('model').append(opt)}
 const params=new URL(location).searchParams,model=params.get('model')||'cmp_FM';if(!config.models.some(m=>m.configuration===model))throw Error('Unsupported model');$('model').value=model;
 const mode=params.get('mode')||'standard',order=params.get('order')||'original';if(!['standard','nonlocal'].includes(mode)||!['original','asc','desc'].includes(order))throw Error('Invalid mode/order');$('mode').value=mode;$('order').value=order;
 $('positionGo').onclick=()=>go(displayOrder[+$('position').value-1]);$('position').onchange=$('positionGo').onclick;$('globalGo').onclick=()=>go(+$('global').value);$('global').onchange=$('globalGo').onclick;
 $('prev').onclick=()=>go(displayOrder[displayOrder.indexOf(queryIndex+1)-1]);$('next').onclick=()=>go(displayOrder[displayOrder.indexOf(queryIndex+1)+1]);$('random').onclick=()=>go(displayOrder[Math.floor(Math.random()*9000)]);
 $('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(filters,120)};$('order').onchange=()=>{try{setOrder()}catch(e){failure(e)}};for(const id of ['model','mode'])$(id).onchange=()=>switchModelMode().catch(failure);
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));$('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};updateZoom()};window.addEventListener('resize',()=>document.querySelectorAll('.lc-canvas').forEach(c=>drawLC(c).catch(failure)));
 $('provenanceText').textContent=`Supplemental ${config.generation}\n28 accepted model embedding matrices; no browser ranking/inference. All 9000 evaluation originals; self excluded. Non-local distance >=2000m.\nCandidate ranking: cosine descending, exact ties lexical scene ID. Bands 1; 2–11; floor((N−10)/2)+1…+10; N−9…N.\nQuery ordering changes navigation only: Rank-1 cosine asc/desc, exact ties lexical query ID. Original = accepted global order. Model/mode/order switches preserve selected scene.\nLC bases: official EGIS22 middle classes; unchanged fraction blend, alpha mask and nearest-neighbor display. DEM standardized17×17, not metres. No thesis protocol change.`;
 queryIndex=0;await switchModelMode(true);
}
init().catch(failure);
