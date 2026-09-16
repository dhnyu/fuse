'use strict';
// Legacy 10c02e4 columns()/columnHTML(): five columns and a 5x2 thumbnail strip.
let bandsSelection={top:0,middle:0,bottom:0}, activeEvidence;
function bandColumns(){
 const q=config.queries[queryIndex];return [
  {key:'query',title:'Query',item:{gallery_scene_id:q.scene_id},strip:null},
  {key:'most',title:'Rank 1 / Most similar',item:activeEvidence.bands.most[0],strip:null},
  ...['top','middle','bottom'].map(key=>({key,title:key[0].toUpperCase()+key.slice(1)+' band (10)',item:activeEvidence.bands[key][bandsSelection[key]],strip:activeEvidence.bands[key]}))];
}
function bandFail(error){serial++;$('comparison').replaceChildren();$('error').hidden=false;$('error').textContent='Inspection stopped: '+error.message;console.error(error)}
async function loadScene(id){const s=await artifact('scenes/'+id+'.json');if(s.scene_id!==id||s.thematic.binding.scene_id!==id)throw Error('Scene binding invalid');return s}
function bandRow(title,content){return `<div class="row"><div class="row-title">${title}</div>${content}</div>`}
function rasterBlock(s,kind){return `<div data-raster="${kind}"><div class="raster-title">${kind==='LC'?'LC · stored 100 × 100 class fractions':'DEM · stored 17 × 17 standardized means'}</div><div class="map-frame">${kind==='LC'?`<canvas class="lc-canvas" data-png="${s.lc}" aria-label="Land cover, nearest-neighbor display"></canvas>`:`<img src="${s.dem}" alt="Standardized DEM">`}</div></div>`}
async function drawLC(canvas){
 const img=new Image();img.src=canvas.dataset.png;await img.decode();
 if(img.naturalWidth!==100||img.naturalHeight!==100)throw Error('Corrupt LC raster dimensions');
 const box=canvas.getBoundingClientRect(),dpr=devicePixelRatio||1;
 canvas.width=Math.round(box.width*dpr);canvas.height=Math.round(box.height*dpr);
 const ctx=canvas.getContext('2d');ctx.imageSmoothingEnabled=false;ctx.drawImage(img,0,0,canvas.width,canvas.height);
 canvas.dataset.intrinsic='100x100';canvas.dataset.smoothing='false';
}
async function renderBandColumns(token){
 const cols=bandColumns();const loaded=await Promise.all(cols.map(c=>loadScene(c.item.gallery_scene_id)));
 const thumbs=await Promise.all(['top','middle','bottom'].flatMap(k=>activeEvidence.bands[k].map(x=>loadScene(x.gallery_scene_id))));
 if(token!==serial)return;
 const thumbMap=new Map(thumbs.map(s=>[s.scene_id,s]));scenes=loaded;rows=cols.slice(1).map(c=>c.item);
 const container=document.createDocumentFragment();
 cols.forEach((col,i)=>{
  const item=col.item,s=loaded[i],meta=item.rank?`Rank ${item.rank} · cos ${item.similarity.toFixed(6)} · ${(item.geographic_distance_m/1000).toFixed(2)} km`:'Fixed evaluation original';
  const strip=col.strip?`<div class="strip">${col.strip.map((x,j)=>`<button data-band="${col.key}" data-index="${j}" data-rank="${x.rank}" data-scene="${esc(x.gallery_scene_id)}" class="${j===bandsSelection[col.key]?'selected':''}" title="Rank ${x.rank} · ${esc(x.gallery_scene_id)} · cosine ${x.similarity} · ${x.geographic_distance_m} m">${thumbMap.get(x.gallery_scene_id).svg}<span>#${x.rank}</span></button>`).join('')}</div>`:'<div class="strip-spacer"></div>';
  const el=document.createElement('section');el.className='column';el.dataset.scene=s.scene_id;el.dataset.band=col.key;el.dataset.rank=item.rank||'';
  el.innerHTML=`<div class="column-head"><h2>${col.title}</h2><div class="rank-meta" title="${item.rank?`Exact cosine ${item.similarity}; ${item.geographic_distance_m} m`:meta}">${meta}</div><div class="scene-id">${esc(s.scene_id)}</div></div>${strip}`+
   (window.S10Locations?window.S10Locations.block(s):'')+
   bandRow('Vector data',`<div class="map-frame vector-map">${s.svg}</div>`)+
   bandRow('Raster data',`<div class="raster-pair">${rasterBlock(s,'LC')}${rasterBlock(s,'DEM')}</div>`)+
   bandRow('Attributes & spatial relations',`<div class="summary">${Object.entries(s.counts).map(([k,v])=>`<div><b>${v}</b>${esc(k)}</div>`).join('')}<div><b>${s.ordered_edges}</b>ordered edges</div></div><div class="display-note">EPSG:5186 · ${s.center.map(x=>x.toFixed(2)).join(', ')}</div>`);
  const host=document.createElement('div');host.className='row detail-host';host.append(details(s,i));el.append(host);container.append(el);
 });
 $('comparison').replaceChildren(container);bindVectorInteraction();
 $('comparison').querySelectorAll('[data-band][data-index]').forEach(b=>b.onclick=()=>{bandsSelection[b.dataset.band]=+b.dataset.index;renderBandColumns(++serial).catch(bandFail)});
 await Promise.all([...document.querySelectorAll('.lc-canvas')].map(drawLC));
 await Promise.all([...document.querySelectorAll('.raster-pair img')].map(async img=>{await img.decode();if(img.naturalWidth!==17||img.naturalHeight!==17)throw Error('Corrupt DEM raster dimensions')}));
}
async function renderBands(){
 const token=++serial;$('error').hidden=true;$('comparison').replaceChildren();$('caseTitle').textContent='Verifying supplemental bands…';
 const q=config.queries[queryIndex],mid=$('model').value,mode=$('mode').value;
 const data=await artifact('queries/'+q.scene_id+'.json');if(token!==serial)return;
 activeEvidence=data[mid]?.[mode];if(!activeEvidence)throw Error('Missing band evidence');
 for(const [key,items] of Object.entries(activeEvidence.bands))if(items.some(x=>x.query_id!==q.scene_id||x.model_id!==mid||x.retrieval_mode!==mode)||items.length!==(key==='most'?1:10))throw Error('Band binding invalid');
 $('caseTitle').textContent=`Query ${queryIndex+1} / ${config.queries.length} · ${mid} · ${$('mode').selectedOptions[0].text}`;
 $('identity').textContent=`${activeEvidence.candidate_count.toLocaleString()} eligible · full-order bands · cosine: higher = more similar`;
 $('prev').disabled=queryIndex===0;$('next').disabled=queryIndex===config.queries.length-1;
 await renderBandColumns(token);
 const url=new URL(location);url.searchParams.set('model',mid);url.searchParams.set('mode',mode);history.replaceState(null,'',url);
}
function navigateBandQuery(i){queryIndex=i;$('query').value=i;bandsSelection={top:0,middle:0,bottom:0};renderBands().catch(bandFail);const url=new URL(location);url.pathname=url.pathname.replace(/[^/]*$/,`query_${String(config.queries[i].query_index).padStart(2,'0')}.html`);history.replaceState(null,'',url)}
async function initBands(){
 config=await verified('config.json',document.body.dataset.configSha);
 if(window.S10Locations)await window.S10Locations.init(config);
 $('query').innerHTML=config.queries.map((q,i)=>option(i,`${q.query_index}. ${q.scene_id}`)).join('');$('query').value=queryIndex;modelOptions();
 const params=new URL(location).searchParams;if(config.models.some(m=>m.id===params.get('model')))$('model').value=params.get('model');if(['standard','nonlocal'].includes(params.get('mode')))$('mode').value=params.get('mode');
 $('query').onchange=()=>navigateBandQuery(+$('query').value);$('prev').onclick=()=>navigateBandQuery(queryIndex-1);$('next').onclick=()=>navigateBandQuery(queryIndex+1);
 $('group').onchange=()=>{modelOptions();renderBands().catch(bandFail)};for(const id of ['model','mode'])$(id).onchange=()=>{bandsSelection={top:0,middle:0,bottom:0};renderBands().catch(bandFail)};
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));
 $('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};updateZoom()};$('toggleProvenance').onclick=()=>$('provenance').classList.toggle('hidden');
 $('provenanceText').textContent=`Parent ${config.acceptance}\nSupplemental evidence ${config.evidence_id}\nAccepted normalized embeddings only; formal Top50 exact consistency verified.\nRank1 = full eligible rank 1; Top = 2–11; Middle starts floor((N−10)/2)+1; Bottom = N−9…N.\nNo checkpoint/inference/preprocessing/Fourier execution. Formal acceptance is unchanged.\nLC uses identical stored 100×100 fraction-colour pixels; canvas smoothing is off at device resolution.\nDEM is stored standardized 17×17, display smoothing only. Detailed thematic summaries are unchanged.`;
 if(config.location_metadata)$('provenanceText').textContent+='\nLocation: '+config.location_metadata.artifact_id+'\nScene center, WGS84 lon/lat; administrative-dong boundaries 2025-06-30. Metadata-only enrichment; no ranking recomputation or inference.';
 new ResizeObserver(()=>{document.documentElement.style.setProperty('--header-height',document.querySelector('header').getBoundingClientRect().height+'px');document.querySelectorAll('.lc-canvas').forEach(c=>drawLC(c).catch(bandFail))}).observe(document.querySelector('header'));
 window.addEventListener('resize',()=>document.querySelectorAll('.lc-canvas').forEach(c=>drawLC(c).catch(bandFail)));
 await renderBands();
}
initBands().catch(bandFail);
