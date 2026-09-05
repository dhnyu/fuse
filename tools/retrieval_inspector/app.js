"use strict";
const ROOT = window.RETRIEVAL_MANIFEST;
const PRESENTATION = window.RETRIEVAL_PRESENTATION || {};
let M = ROOT, renderEpoch = 0;
const modelOrder = ["cfg_d128", "cmp_a1_geometric_core", "cmp_a2_semantic_enriched", "cmp_a3_object_context_enriched", "cmp_a4_raster_complete_non_relational", "cmp_a5_relation_type_agnostic", "cmp_ssv_like", "cmp_ds_like"];
const models = modelOrder.filter(id => ROOT.models[id]);
const loaded = window.RETRIEVAL_SCENES = window.RETRIEVAL_SCENES || {};
const pending = new Map();
const state = {gallery:"canonical", model:models[0], query:M.queries[0].scene_id, setting:"standard", raster:"landcover", layers:new Set(["B","R","P"]), selected:{top:0,middle:0,bottom:0}};
const $ = s => document.querySelector(s), all = s => [...document.querySelectorAll(s)];
const galleryName = id => id === "supplemental" ? "Expanded 10,000" : "Canonical 1,600";
const sourceName = item => item.source === "supplemental" ? "Supplemental" : "Canonical";
const modelLabel = id => id === "cfg_d128" ? "FM / cfg_d128" : M.models[id].label;
function setGallery(id) {
  state.gallery = ROOT.galleries && ROOT.galleries[id] ? id : "canonical";
  M = ROOT.galleries ? ROOT.galleries[state.gallery] : ROOT;
}
function parseHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  setGallery(p.get("gallery") || "canonical");
  state.model = models.includes(p.get("model")) ? p.get("model") : models[0];
  state.query = M.queries.some(q => q.scene_id === p.get("query")) ? p.get("query") : M.queries[0].scene_id;
  state.setting = p.get("setting") === "nonlocal" ? "nonlocal" : "standard";
  state.raster = p.get("raster") === "dem" ? "dem" : "landcover";
  state.layers = new Set(p.has("layers") ? p.get("layers").split(",").filter(v => ["B","R","P"].includes(v)) : ["B","R","P"]);
  for (const b of ["top","middle","bottom"]) {
    const n = Number(p.get(b));
    state.selected[b] = Number.isInteger(n) && n >= 0 && n < 10 ? n : 0;
  }
}
function saveHash() {
  const p = new URLSearchParams({gallery:state.gallery, model:state.model, query:state.query, setting:state.setting,
    ...state.selected, layers:["B","R","P"].filter(x => state.layers.has(x)).join(","), raster:state.raster});
  const url = new URL(location.href);
  url.hash = p.toString();
  history.replaceState(null, "", url.href);
}
function syncControls() {
  $("#gallery").value = state.gallery;
  $("#model").value = state.model;
  $("#query").value = state.query;
  all('input[name=setting]').forEach(x => x.checked = x.value === state.setting);
  all('input[name=raster]').forEach(x => x.checked = x.value === state.raster);
  all('.checks input').forEach(x => x.checked = state.layers.has(x.value));
  $(".eyebrow").textContent = state.gallery === "supplemental" ? "Supplementary retrieval-only evidence" : "P10 qualitative evidence";
}
function loadScene(id) {
  if (loaded[id]) return Promise.resolve(loaded[id]);
  if (pending.has(id)) return pending.get(id);
  const promise = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `assets/scenes/${id}.js`;
    script.onload = () => { script.remove(); loaded[id] ? resolve(loaded[id]) : reject(new Error("Empty scene asset " + id)); };
    script.onerror = () => { script.remove(); reject(new Error("Missing scene asset " + id)); };
    document.head.append(script);
  }).finally(() => pending.delete(id));
  pending.set(id, promise);
  return promise;
}
function candidates() { return M.models[state.model].queries[state.query][state.setting]; }
function columns() {
  const c = candidates(), query = {scene_id:state.query, rank:null, similarity:null, distance_m:0, source:"canonical"};
  return [{key:"query",title:"Query",item:query,strip:null},
    {key:"most",title:"Rank 1 / Most similar",item:c.bands.most[0],strip:null},
    ...["top","middle","bottom"].map(key => ({key,title:key[0].toUpperCase()+key.slice(1)+" band (10)",item:c.bands[key][state.selected[key]],strip:c.bands[key]}))];
}
function fmt(v,d=2){return v==null?'Unavailable':Number(v).toLocaleString(undefined,{maximumFractionDigits:d})}
function decode(rle){const out=[];for(const [v,n] of rle)for(let i=0;i<n;i++)out.push(v);return out}
function pathSets(geometry){const c=geometry.coordinates,t=geometry.type;if(t==='Point')return[[[c]]];if(t==='MultiPoint')return c.map(p=>[[p]]);if(t==='LineString')return[[c]];if(t==='MultiLineString')return c.map(line=>[line]);if(t==='Polygon')return[c];if(t==='MultiPolygon')return c;return[]}
function drawVector(canvas,scene){const dpr=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*dpr;canvas.height=h*dpr;const x=canvas.getContext('2d');x.scale(dpr,dpr);x.fillStyle='#f7f8f4';x.fillRect(0,0,w,h);const sx=w/500,sy=h/500;for(const e of scene.vectors){if(!state.layers.has(e.type))continue;const color=e.type==='B'?'#d5a940':e.type==='R'?'#50616d':'#c33c54';for(const paths of pathSets(e.geometry)){x.beginPath();for(const path of paths){path.forEach((p,i)=>{const px=p[0]*sx,py=h-p[1]*sy;i?x.lineTo(px,py):x.moveTo(px,py)});if(e.type==='B')x.closePath()}if(e.type==='B'){x.fillStyle=color+'99';x.fill('evenodd');x.strokeStyle='#8e7028';x.lineWidth=.7;x.stroke()}else if(e.type==='R'){x.strokeStyle=color;x.lineWidth=1.2;x.stroke()}else{const p=paths[0][0];x.beginPath();x.arc(p[0]*sx,h-p[1]*sy,2,0,Math.PI*2);x.fillStyle=color;x.fill()}}}}
function drawRaster(canvas,scene,min,max){const dpr=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*dpr;canvas.height=h*dpr;const x=canvas.getContext('2d');x.scale(dpr,dpr);const r=state.raster==='landcover'?scene.landcover:scene.dem,values=decode(r.rle),rows=r.shape[0],cols=r.shape[1],cw=w/cols,ch=h/rows;for(let i=0;i<values.length;i++){const v=values[i];if(v==null||v===0)x.fillStyle='#e2e5e1';else if(state.raster==='landcover')x.fillStyle=M.render.landcover_colors[v-1];else{x.fillStyle=viridis((v-min)/Math.max(max-min,1e-9))}x.fillRect((i%cols)*cw,Math.floor(i/cols)*ch,Math.ceil(cw+.3),Math.ceil(ch+.3))}}
function viridis(t){t=Math.max(0,Math.min(1,t));const stops=[[68,1,84],[59,82,139],[33,145,140],[94,201,98],[253,231,37]],u=t*(stops.length-1),i=Math.min(stops.length-2,Math.floor(u)),f=u-i;return`rgb(${stops[i].map((v,j)=>Math.round(v+(stops[i+1][j]-v)*f)).join(',')})`}
function list(items){return items.length?items.map(x=>`<li>${x.label}: <b>${x.count}</b></li>`).join(''):'<li>None</li>'}
function summary(scene){const s=scene.summary,r=s.relations,lc=scene.landcover.composition.map((v,i)=>({label:`LC ${String(i+1).padStart(2,'0')}`,value:v})).sort((a,b)=>b.value-a.value).slice(0,5);return`<div class="summary"><div class="metric"><b>${fmt(s.building_count,0)}</b><span>buildings · ${fmt(s.building_coverage*100,1)}% cover</span></div><div class="metric"><b>${fmt(s.road_segment_count,0)}</b><span>roads · ${fmt(s.road_length_m,0)} m</span></div><div class="metric"><b>${fmt(s.poi_count,0)}</b><span>POIs</span></div><div class="metric"><b>${fmt(scene.dem.mean,1)} m</b><span>DEM ${fmt(scene.dem.min,1)}–${fmt(scene.dem.max,1)} m</span></div></div><div class="relations">${['SN','CNT','WIT','INT','CON'].map(k=>`<div class="relation"><b>${fmt(r[k],0)}</b>${k}</div>`).join('')}</div><details><summary>Detailed summaries</summary><p><b>Location</b> ${scene.district} (${scene.district_id}) · X ${fmt(scene.center[0],1)}, Y ${fmt(scene.center[1],1)}</p><b>POI categories</b><ul class="detail-list">${list(s.poi_categories)}</ul><b>Land cover composition</b><ul class="detail-list">${lc.map(x=>`<li>${x.label}: <b>${fmt(x.value*100,1)}%</b></li>`).join('')}</ul><b>Building use</b><ul class="detail-list">${list(s.building_types)}</ul><b>Building structure</b><ul class="detail-list">${list(s.building_structures)}</ul><b>Road rank</b><ul class="detail-list">${list(s.road_ranks)}</ul></details>`}
async function copyText(value){try{await navigator.clipboard.writeText(value)}catch(_){const input=document.createElement('textarea');input.value=value;document.body.append(input);input.select();document.execCommand('copy');input.remove()}}
function sceneID(id) {
  return `<div class="scene-id"><span title="${id}">${id}</span><button class="copy" data-copy="${id}" title="Copy scene ID" aria-label="Copy scene ID">&#10697;</button></div>`;
}
function columnHTML(col) {
  const item = col.item, source = sourceName(item);
  const meta = item.rank == null ? "Fixed P10 query" : `Rank ${item.rank.toLocaleString()} · sim ${item.similarity.toFixed(5)} · ${fmt(item.distance_m/1000,2)} km`;
  const strip = col.strip ? `<div class="strip">${col.strip.map((x,i) => `<button data-band="${col.key}" data-index="${i}" class="${i===state.selected[col.key]?'selected':''}" title="Rank ${x.rank} · similarity ${x.similarity.toFixed(5)} · ${fmt(x.distance_m/1000,2)} km · ${sourceName(x)} · ${x.scene_id}"><canvas data-thumb="${x.scene_id}"></canvas><span>#${x.rank}</span></button>`).join("")}</div>` : '<div class="strip-spacer"></div>';
  return `<section class="column" data-scene="${item.scene_id}" data-rank="${item.rank || ''}" data-source="${source.toLowerCase()}"><div class="column-head"><h2>${col.title}</h2><div class="rank-meta" title="${meta}">${meta}</div>${sceneID(item.scene_id)}<span class="source source-${source.toLowerCase()}">${source}</span>${state.setting === "nonlocal" && item.rank ? '<span class="distance-gate">Distance ≥ 2 km</span>' : ''}</div>${strip}<div class="row"><div class="row-title">Vector data</div><div class="map-frame"><canvas class="vector"></canvas><span class="north">N&#8593;</span><span class="scale">200 m</span></div><div class="legend"><span><i class="swatch" style="background:#d5a940"></i>Building</span><span><i class="swatch" style="background:#50616d"></i>Road</span><span><i class="swatch" style="background:#c33c54"></i>POI</span></div></div><div class="row"><div class="row-title">Raster data</div><div class="map-frame"><canvas class="raster"></canvas></div><div class="raster-legend"></div></div><div class="row attributes"><div class="row-title">Attributes & spatial relations</div><div class="loading">Loading scene</div></div></section>`;
}
function renderMetadata() {
  const q = M.queries.find(x => x.scene_id === state.query), c = candidates();
  $("#context").innerHTML = `<strong class="active-gallery">${galleryName(state.gallery)}</strong><span><b>${M.gallery_count.toLocaleString()}</b> gallery scenes</span><span><b>${c.candidate_count.toLocaleString()}</b> candidates</span><span>${modelLabel(state.model)}</span><span>Query ${q.index}/10 · ${q.district || "Unavailable"}</span><span class="context-id">${q.scene_id}</span><span>X ${fmt(q.center[0],1)} · Y ${fmt(q.center[1],1)}</span><span>${state.setting === "standard" ? "Standard" : "Non-local · distance ≥ 2 km"}</span><span>Cosine similarity: larger = more similar</span>`;
  const record = PRESENTATION.diagnostics?.[state.model]?.[state.query]?.[state.setting];
  $("#stability").hidden = !record;
  if (!record) return;
  const d = record.diagnostic, old = record.old_best;
  $("#stability").innerHTML = `<h2>1,600 vs 10,000</h2><div class="stability-grid"><div class="best"><span class="row-title">Canonical rank 1</span>${sceneID(old.scene_id)}<span>Similarity <b>${old.similarity.toFixed(5)}</b> · Expanded rank <b>${d.old_best_new_rank.toLocaleString()}</b></span></div><div class="best"><span class="row-title">Expanded rank 1 <span class="source source-${d.new_best_source}">${d.new_best_source === "supplemental" ? "Supplemental" : "Canonical"}</span></span>${sceneID(d.new_best_scene_id)}<span>Similarity <b>${d.new_best_similarity.toFixed(5)}</b> · ${fmt(d.new_best_distance_m/1000,2)} km</span></div><div class="stability-metric"><span>Top-10 overlap</span><b>${d.top10_overlap_count}/10 <small>(${fmt(d.top10_overlap_fraction*100,0)}%)</small></b></div><div class="stability-metric"><span>Top-100 overlap</span><b>${d.top100_overlap_count}/100 <small>(${fmt(d.top100_overlap_fraction*100,0)}%)</small></b></div><div class="stability-metric"><span>Expanded rank 1 − rank 10</span><b>${d.rank1_rank10_similarity_gap.toFixed(5)}</b></div></div>`;
}
async function render() {
  const epoch = ++renderEpoch;
  syncControls(); saveHash(); renderMetadata();
  const cols = columns();
  $("#comparison").innerHTML = cols.map(columnHTML).join("");
  $("#status").textContent = "Loading scene assets";
  try {
    const ids = [...new Set(cols.flatMap(c => [c.item.scene_id,...(c.strip || []).map(x => x.scene_id)]))];
    const values = await Promise.all(ids.map(loadScene));
    if (epoch !== renderEpoch) return;
    const sceneMap = Object.fromEntries(values.map(x => [x.scene_id,x])), scenes = cols.map(x => sceneMap[x.item.scene_id]);
    const validDem = scenes.flatMap(s => decode(s.dem.rle).filter(v => v != null));
    const min = Math.min(...validDem), max = Math.max(...validDem);
    all("[data-thumb]").forEach(canvas => drawVector(canvas,sceneMap[canvas.dataset.thumb]));
    all(".column").forEach((el,i) => {
      const scene = scenes[i];
      drawVector(el.querySelector(".vector"),scene);
      drawRaster(el.querySelector(".raster"),scene,min,max);
      el.querySelector(".attributes").innerHTML = `<div class="row-title">Attributes & spatial relations</div><div class="location">${scene.district || "Unavailable"} · X ${fmt(scene.center[0],1)} · Y ${fmt(scene.center[1],1)}</div>${summary(scene)}`;
      if (state.raster === "dem") {
        el.querySelector(".raster-legend").innerHTML = `<div class="dem-key"></div><div class="legend"><span>${fmt(min,1)} m</span><span style="margin-left:auto">${fmt(max,1)} m</span></div>`;
      } else {
        const present = scene.landcover.composition.map((v,i) => ({v,i})).filter(x => x.v > 0);
        el.querySelector(".raster-legend").innerHTML = `<div class="legend">${present.map(x => `<span title="LC class ${x.i+1}: ${fmt(x.v*100,1)}%"><i class="swatch" style="background:${M.render.landcover_colors[x.i]}"></i>${String(x.i+1).padStart(2,"0")}</span>`).join("")}</div>`;
      }
    });
    $("#status").textContent = "Evidence ready";
  } catch (error) {
    if (epoch !== renderEpoch) return;
    $("#status").textContent = "Asset error";
    console.error(error);
  }
}
function step(kind,n) {
  const values = kind === "gallery" ? Object.keys(ROOT.galleries || {canonical:ROOT}) : kind === "model" ? models : M.queries.map(q => q.scene_id);
  const next = values[(values.indexOf(state[kind])+n+values.length)%values.length];
  if (kind === "gallery") setGallery(next); else state[kind] = next;
  render();
}
function setup() {
  new ResizeObserver(() => document.documentElement.style.setProperty("--controls-height",`${$(".controls").getBoundingClientRect().height}px`)).observe($(".controls"));
  $("#galleryControl").hidden = !ROOT.galleries;
  $("#interpretation").hidden = !ROOT.galleries;
  $("#model").innerHTML = models.map(id => `<option value="${id}">${id === "cfg_d128" ? "FM / cfg_d128" : ROOT.models[id].label + " / " + id}</option>`).join("");
  $("#query").innerHTML = M.queries.map(q => `<option value="${q.scene_id}">${q.index}. ${q.scene_id} · ${q.district || "Unavailable"}</option>`).join("");
  parseHash();
  $("#gallery").onchange = () => { setGallery($("#gallery").value); render(); };
  $("#model").onchange = () => { state.model = $("#model").value; render(); };
  $("#query").onchange = () => { state.query = $("#query").value; render(); };
  all("input[name=setting]").forEach(x => x.onchange = () => { state.setting=x.value;render(); });
  all("input[name=raster]").forEach(x => x.onchange = () => { state.raster=x.value;render(); });
  all(".checks input").forEach(x => x.onchange = () => { x.checked ? state.layers.add(x.value) : state.layers.delete(x.value);render(); });
  for (const kind of ["Gallery","Model","Query"]) for (const [prefix,n] of [["prev",-1],["next",1]]) {
    $("#"+prefix+kind).onclick = () => step(kind.toLowerCase(),n);
  }
  $("#comparison").onclick = e => { const button=e.target.closest("[data-band]");if(button){state.selected[button.dataset.band]=Number(button.dataset.index);render();} };
  document.addEventListener("click",e => { const button=e.target.closest("[data-copy]");if(button)copyText(button.dataset.copy); });
  window.onhashchange = () => { parseHash();render(); };
  window.addEventListener("resize",() => { if ($("#status").textContent === "Evidence ready") render(); });
  render();
}
setup();
