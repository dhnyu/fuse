'use strict';
// Display timing only. All rankings, hashes, scene bytes and band semantics stay fixed.
window.S10Perf = {sizes:new Map(), budget:16*1024*1024, limit:128,
 concurrency:window.S10PerfTestConcurrency||6, mainReady:0, thumbsReady:0, generation:0};
const perfPending=new Map();
function trimSceneCache(){
 let bytes=0;for(const key of cache.keys())bytes+=S10Perf.sizes.get(key)||0;
 while(cache.size>S10Perf.limit||bytes>S10Perf.budget){
  const key=[...cache.keys()].find(k=>!S10Perf.pinned?.has(k));if(!key)break;bytes-=S10Perf.sizes.get(key)||0;cache.delete(key);S10Perf.sizes.delete(key);
 }
 S10Perf.cacheBytes=bytes;
}
artifact=function(path){
 if(cache.has(path)){const p=cache.get(path);cache.delete(path);cache.set(path,p);return p}
 if(perfPending.has(path))return perfPending.get(path);
 const p=verified(path,config.files[path]).then(value=>{perfPending.delete(path);cache.set(path,Promise.resolve(value));trimSceneCache();return value},error=>{perfPending.delete(path);S10Perf.sizes.delete(path);throw error});
 perfPending.set(path,p);return p;
};
const eagerDetails=details;
details=function(s,i){
 const host=panel(s,i),d=document.createElement('details');
 d.innerHTML='<summary class="detail-toggle">Detailed summaries</summary>';
 let built=false;
 d.addEventListener('toggle',()=>{
  if(d.open&&!built){try{const original=eagerDetails(s,i).querySelector('details');d.append(original.querySelector('.thematic-grid'));built=true;d.dataset.loaded='true'}catch(e){bandFail(e)}}
 });host.append(d);return host;
};
const nextPaint=()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
function lazyRasters(s){
 const d=document.createElement('details');d.className='row lazy-rasters';
 d.innerHTML='<summary class="detail-toggle">Raster data · LC / DEM</summary>';
 let built=false;
 d.addEventListener('toggle',async()=>{
  if(!d.open||built)return;built=true;
  try{
   const body=document.createElement('div');body.className='raster-pair';body.innerHTML=rasterBlock(s,'LC')+rasterBlock(s,'DEM');d.append(body);
   await drawLC(d.querySelector('canvas'));const img=d.querySelector('img');await img.decode();
   if(img.naturalWidth!==17||img.naturalHeight!==17)throw Error('Corrupt DEM raster dimensions');d.dataset.loaded='true';
  }catch(e){bandFail(e)}
 });return d;
}
async function renderBandColumns(token){
 S10Perf.mainReady=0;S10Perf.thumbsReady=0;S10Perf.generation=token;
 const cols=bandColumns();S10Perf.pinned=new Set(cols.map(c=>'scenes/'+c.item.gallery_scene_id+'.json'));S10Perf.pinned.add('queries/'+config.queries[queryIndex].scene_id+'.json');
 const loaded=await Promise.all(cols.map(c=>loadScene(c.item.gallery_scene_id)));
 if(token!==serial)return;
 scenes=loaded;rows=cols.slice(1).map(c=>c.item);
 const container=document.createDocumentFragment();
 cols.forEach((col,i)=>{
  const item=col.item,s=loaded[i],meta=item.rank?`Rank ${item.rank} · cos ${item.similarity.toFixed(6)} · ${(item.geographic_distance_m/1000).toFixed(2)} km`:'Fixed evaluation original';
  const strip=col.strip?`<div class="strip">${col.strip.map((x,j)=>`<button data-band="${col.key}" data-index="${j}" data-rank="${x.rank}" data-scene="${esc(x.gallery_scene_id)}" class="${j===bandsSelection[col.key]?'selected':''}" title="Rank ${x.rank} · ${esc(x.gallery_scene_id)} · cosine ${x.similarity} · ${x.geographic_distance_m} m" aria-label="Show rank ${x.rank}"><span>#${x.rank}</span></button>`).join('')}</div>`:'<div class="strip-spacer"></div>';
  const el=document.createElement('section');el.className='column';el.dataset.scene=s.scene_id;el.dataset.band=col.key;el.dataset.rank=item.rank||'';
  el.innerHTML=`<div class="column-head"><h2>${col.title}</h2><div class="rank-meta" title="${item.rank?`Exact cosine ${item.similarity}; ${item.geographic_distance_m} m`:meta}">${meta}</div><div class="scene-id">${esc(s.scene_id)}</div></div>${strip}`+
   (window.S10Locations?window.S10Locations.block(s):'')+
   bandRow('Vector data',`<div class="map-frame vector-map">${s.svg}</div>`)+
   bandRow('Attributes & spatial relations',`<div class="summary">${Object.entries(s.counts).map(([k,v])=>`<div><b>${v}</b>${esc(k)}</div>`).join('')}<div><b>${s.ordered_edges}</b>ordered edges</div></div><div class="display-note">EPSG:5186 · ${s.center.map(x=>x.toFixed(2)).join(', ')}</div>`);
  el.append(lazyRasters(s));const host=document.createElement('div');host.className='row detail-host';host.append(details(s,i));el.append(host);container.append(el);
 });
 $('comparison').replaceChildren(container);bindVectorInteraction();
 const buttons=[...$('comparison').querySelectorAll('[data-band][data-index]')];
 buttons.forEach(b=>b.onclick=()=>{bandsSelection[b.dataset.band]=+b.dataset.index;renderBandColumns(++serial).catch(bandFail)});
 await nextPaint();if(token!==serial)return;
 S10Perf.mainReady=performance.now();
 // Resolve caller and update navigation before starting background requests.
 setTimeout(()=>loadBandThumbnails(buttons,token).catch(e=>{if(token===serial)bandFail(e)}),0);
}
async function loadBandThumbnails(buttons,token){
 let cursor=0;
 async function worker(){
  while(cursor<buttons.length&&token===serial){
   const b=buttons[cursor++],s=await loadScene(b.dataset.scene);
   if(token!==serial)return;
   b.insertAdjacentHTML('afterbegin',s.svg);b.dataset.loaded='true';
   // Yield between geometry insertions, including warm-cache navigation.
   await new Promise(r=>setTimeout(r,0));
  }
 }
 await Promise.all(Array.from({length:S10Perf.concurrency},worker));
 if(token===serial){await nextPaint();S10Perf.thumbsReady=performance.now()}
}
