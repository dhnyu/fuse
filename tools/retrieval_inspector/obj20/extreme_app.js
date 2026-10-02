// Supplemental fixed memberships; browser reads stored rankings only.
async function renderExtreme(){
 const token=++serial;document.body.dataset.readyMode='';document.body.dataset.readyQuery='';
 $('error').hidden=true;$('comparison').replaceChildren();
 const name=$('set').value,q=config.queries[queryIndex],mode=$('mode').value;
 const data=await artifact('queries/'+q.scene_id+'.json');if(token!==serial)return;
 activeEvidence=data.cmp_FM?.[mode];if(!activeEvidence)throw Error('Missing FM evidence');
 for(const [key,items] of Object.entries(activeEvidence.bands))if(items.some(x=>x.query_id!==q.scene_id||x.model_id!=='cmp_FM'||x.retrieval_mode!==mode)||items.length!==(key==='most'?1:10))throw Error('Invalid band binding');
 $('caseTitle').textContent=`${name.replaceAll('_',' ')} · Query ${queryIndex+1} / 100 · FM · ${mode}`;
 $('identity').textContent=`Selection mode: ${q.selection_mode} · selection Rank-1 cosine: ${q.rank1_cosine} · fixed set position: ${q.query_index} · ${activeEvidence.candidate_count} gallery candidates · ${q.set_name.endsWith('_OBJ20')?'OBJ20 display-only: B+R+P ≥ 20; gallery unchanged':q.set_name.endsWith('_NONEMPTY')?'Historical display-only: B+R+P ≥ 1; gallery unchanged':'Original all-scene set; unchanged'}`;
 $('prev').disabled=queryIndex===0;$('next').disabled=queryIndex===99;
 await renderBandColumns(token);if(token!==serial)return;
 const url=new URL(location);url.searchParams.set('set',name);url.searchParams.set('mode',mode);url.searchParams.set('query',queryIndex+1);history.replaceState(null,'',url);
 document.body.dataset.readyMode=mode;document.body.dataset.readyQuery=String(queryIndex);
}
function navigateExtreme(i){queryIndex=i;$('query').value=i;bandsSelection={top:0,middle:0,bottom:0};renderExtreme().catch(bandFail)}
function chooseSet(name,initial=false){
 config.queries=config.sets[name];queryIndex=initial?Math.min(99,Math.max(0,Number(new URL(location).searchParams.get('query')||1)-1)):0;
 $('query').innerHTML=config.queries.map((q,i)=>option(i,`${q.query_index}. ${q.scene_id}`)).join('');$('query').value=queryIndex;
 $('mode').value=config.queries[0].selection_mode;
 if(initial&&['standard','nonlocal'].includes(new URL(location).searchParams.get('mode')))$('mode').value=new URL(location).searchParams.get('mode');
 navigateExtreme(queryIndex);
}
async function initExtreme(){
 config=await verified('config.json',document.body.dataset.configSha);
 if(config.models.length!==1||config.models[0].id!=='cmp_FM')throw Error('Final FM only');
 await window.S10Locations.init(config);
 $('set').innerHTML='<optgroup label="Display inspection">'+config.display_order.map(s=>option(s,config.set_labels[s])).join('')+'</optgroup><optgroup label="Original / historical HIGH · advanced">'+['STANDARD_HIGH','NONLOCAL_HIGH','STANDARD_HIGH_NONEMPTY','NONLOCAL_HIGH_NONEMPTY'].map(s=>option(s,config.set_labels[s])).join('')+'</optgroup>';
 $('set').value='STANDARD_HIGH_OBJ20';
 const requested=new URL(location).searchParams.get('set');if(config.sets[requested])$('set').value=requested;
 $('set').onchange=()=>chooseSet($('set').value);$('query').onchange=()=>navigateExtreme(+$('query').value);
 $('prev').onclick=()=>navigateExtreme(queryIndex-1);$('next').onclick=()=>navigateExtreme(queryIndex+1);
 $('mode').onchange=()=>{bandsSelection={top:0,middle:0,bottom:0};renderExtreme().catch(bandFail)};
 document.querySelectorAll('[data-layer]').forEach(x=>x.onchange=()=>document.body.classList.toggle('hide-'+x.dataset.layer,!x.checked));
 $('resetZoom').onclick=()=>{view={scale:1,dx:0,dy:0};updateZoom()};$('toggleProvenance').onclick=()=>$('provenance').classList.toggle('hidden');
 $('provenanceText').textContent=`Supplemental generation ${config.evidence_id}\nFinal FM: cmp_FM. OBJ20 is an inspection-oriented object-bearing query subset: B+R+P >= 20. It is not a new scientific evaluation protocol and does not redefine HIGH. Historical NONEMPTY (>=1) is preserved. Gallery candidates are not filtered by object counts. Original HIGH/LOW sets and full-population statistics are unchanged. Stored accepted embeddings; no model inference.\nHIGH: Queries with the highest [Standard/Non-local] Rank-1 cosine similarity.\nLOW: Queries with the lowest [Standard/Non-local] Rank-1 cosine similarity.\nLOW only means relatively low maximum cosine among eligible gallery scenes; no correctness ground truth.\nMembership stays fixed when changing display mode.\nRank1 = 1; upper = 2–11; middle starts floor((N−10)/2)+1; bottom = N−9…N.\nNo browser ranking computation. Display bytes reused from accepted supplemental viewer.\nLC stored 100×100; DEM stored standardized 17×17.\nThis diagnostic does not replace accepted S10 results or the thesis query protocol.`;
 new ResizeObserver(()=>{document.documentElement.style.setProperty('--header-height',document.querySelector('header').getBoundingClientRect().height+'px');document.querySelectorAll('.lc-canvas').forEach(c=>drawLC(c).catch(bandFail))}).observe(document.querySelector('header'));
 chooseSet($('set').value,true);
}
initExtreme().catch(bandFail);
