'use strict';
// Display-only lookup. Coordinates are transformed once at build time, never here.
window.S10Locations = (() => {
 let metadata;
 function statusName(row, level) {
  const prefix=level==='sigungu'?'sigungu':'eupmyeondong';
  const status=row[level==='sigungu'?'sigungu_join_status':'dong_join_status'];
  if(status==='unique_match')return row[prefix+'_name'];
  if(status==='boundary_ambiguous')return level==='sigungu'?'시군구 경계 지점':'행정동 경계 지점';
  if(status==='no_polygon_match')return level==='sigungu'?'시군구 확인 불가':'행정동 확인 불가';
  throw Error('Invalid location join status');
 }
 function block(scene) {
  const row=metadata?.scenes[scene.scene_id];
  if(!row||row.scene_id!==scene.scene_id||row.center_x!==scene.center[0]||row.center_y!==scene.center[1])throw Error('Location center binding invalid');
  const number=x=>x.toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1});
  const candidates=[...row.sigungu_candidate_names,...row.dong_candidate_names].join(' · ');
  return `<div class="scene-location" data-location-scene="${esc(scene.scene_id)}" title="${esc(candidates)}"><div class="location-name">${esc(statusName(row,'sigungu'))} · ${esc(statusName(row,'dong'))}</div><div class="location-lonlat">Lon ${row.longitude.toFixed(5)} · Lat ${row.latitude.toFixed(5)}</div><div class="location-xy">X ${number(row.center_x)} · Y ${number(row.center_y)}</div><small>Scene center · 행정동 경계 ${esc(row.boundary_date)}<br>EPSG:5186 X / Y</small></div>`;
 }
 async function init(config) {
  if(!config.location_metadata)throw Error('Missing location metadata binding');
  metadata=await artifact(config.location_metadata.path);
  if(metadata.artifact_id!==config.location_metadata.artifact_id||Object.keys(metadata.scenes).length!==9000)throw Error('Location metadata identity invalid');
 }
 return {init,block,statusName};
})();
