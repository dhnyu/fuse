#!/usr/bin/env python3
"""Local A/B and explicitly simulated network; no scientific computation."""
from pathlib import Path
import json,time,argparse
from playwright.sync_api import sync_playwright
P=Path('/mnt/hdd002/dhnyu/fusedata/tmp/fuse/variant_c_20260922')
INIT="performance.setResourceTimingBufferSize(30000);window.longTasks=[];new PerformanceObserver(l=>l.getEntries().forEach(e=>longTasks.push({start:e.startTime,duration:e.duration}))).observe({type:'longtask',buffered:true});"
def done(p):
 p.wait_for_function('navigationReady&&inspection.thumbsReady>0 || !document.getElementById("error").hidden',timeout=90000)
 assert p.locator('#error').is_hidden(),p.locator('#error').inner_text()
def snapshot(p,t):
 return p.evaluate('''t=>{const rs=performance.getEntriesByType('resource').filter(r=>r.startTime>=t);return {five_ms:inspection.mainReady-inspection.started,thumbs_ms:inspection.thumbsReady-inspection.started,metadata_ms:inspection.metadataReady-inspection.started,wall_ms:performance.now()-t,requests:rs.length,encoded:rs.reduce((s,r)=>s+r.encodedBodySize,0),decoded:rs.reduce((s,r)=>s+r.decodedBodySize,0),transfer:rs.reduce((s,r)=>s+r.transferSize,0),long_ms:longTasks.filter(r=>r.start>=t).reduce((s,r)=>s+r.duration,0),resources:rs.map(r=>({name:r.name,encoded:r.encodedBodySize,decoded:r.decodedBodySize,transfer:r.transferSize})),first_before_thumbs:inspection.mainReady<inspection.thumbsReady}}''',t)
def main():
 out={'rows':[],'memory':[],'errors':[],'profile':{'simulated_RTT_ms':100,'download_bytes_per_second':1250000,'upload_bytes_per_second':625000,'CPU_slowdown':4,'not_professor_device':True}}
 def save():(P/'performance.json').write_text(json.dumps(out,indent=2))
 with sync_playwright() as w:
  b=w.chromium.launch(headless=True,args=['--enable-precise-memory-info'])
  for edition,port in [('before',18769),('after',18773)]:
   for slow in [False,True]:
    for repeat in range(3):
     c=b.new_context(viewport={'width':1600,'height':1000});c.add_init_script(INIT);p=c.new_page();p.on('pageerror',lambda e:out['errors'].append(str(e)));cdp=c.new_cdp_session(p);cdp.send('Network.enable')
     if slow:cdp.send('Network.emulateNetworkConditions',{'offline':False,'latency':100,'downloadThroughput':1250000,'uploadThroughput':625000});cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
     p.goto(f'http://127.0.0.1:{port}/?model=cmp_FM&mode=standard&order=original&pos=1');done(p)
     def act(name,fn,cache):
      t=p.evaluate('performance.now()');fn();done(p);r=snapshot(p,t);r.update(edition=edition,slow=slow,repeat=repeat+1,action=name,cache=cache);out['rows'].append(r);save();print(edition,slow,repeat,name,cache,round(r['five_ms']),round(r['thumbs_ms']),flush=True)
     act('q1 → q50',lambda:p.evaluate('go',50),'cold');p.evaluate('go',1);done(p);act('q1 → q50',lambda:p.evaluate('go',50),'warm')
     p.evaluate('go',2);done(p);act('q2 → q50',lambda:p.evaluate('go',50),'warm')
     act('Standard → Non-local',lambda:p.select_option('#mode','nonlocal'),'cold');p.select_option('#mode','standard');done(p);act('Standard → Non-local',lambda:p.select_option('#mode','nonlocal'),'warm')
     act('FM → B9',lambda:p.select_option('#model','cmp_B9'),'cold');p.select_option('#model','cmp_FM');done(p);act('FM → B9',lambda:p.select_option('#model','cmp_B9'),'warm')
     act('B9 → A4',lambda:p.select_option('#model','cmp_A4'),'cold');act('A4 → d64',lambda:p.select_option('#model','ofat_d_64'),'cold')
     # Sorting preserves scene and requires no image re-render/fetch.
     for order in ['asc','desc','original']:
      t=p.evaluate('performance.now()');p.select_option('#order',order);r=p.evaluate('({ms:inspection.orderUpdateMs,q:queryIndex+1,serial})');r.update(edition=edition,slow=slow,repeat=repeat+1,order=order);out.setdefault('sorting',[]).append(r)
     c.close();save()
   # Isolate memory from prior CDP network/CPU-throttle contexts.
   b.close();b=w.chromium.launch(headless=True,args=['--enable-precise-memory-info'])
   # Memory after full 20/50/100 navigation; reopen one Detail every 10 switches.
   c=b.new_context(viewport={'width':1600,'height':1000});p=c.new_page();p.on('pageerror',lambda e:out['errors'].append(str(e)));cdp=c.new_cdp_session(p);p.goto(f'http://127.0.0.1:{port}/');done(p)
   for n in range(101):
    if n:
     if n%5==0:p.select_option('#model',['cmp_FM','cmp_A4','cmp_B9','cmp_DS','ofat_d_64','ofat_d_256'][(n//5)%6]);done(p)
     p.evaluate('go',1+(n*137)%9000);done(p)
     if n%10==0:p.locator('.detail-host').first.evaluate('d=>d.open=true');p.wait_for_function('document.querySelector(".detail-host").dataset.loaded==="true"')
    if n in [0,20,50,100]:
     cdp.send('HeapProfiler.collectGarbage');r=p.evaluate('''()=>{const stores={summary:summaryCache,detail:detailCache,band:bandCache,vector:vectorCache,orders:orderCache,lc:lcCache};if(typeof mainImageCache!=='undefined')Object.assign(stores,{main:mainImageCache,thumb:thumbImageCache,layers:layerCache,source:sourceSummaryCache});return {caches:Object.fromEntries(Object.entries(stores).map(([k,c])=>[k,{entries:c.map.size,bytes:c.bytes,budget:c.budget,limit:c.limit,pending:c.pending.size}]))}}''');r.update(edition=edition,switches=n,heap=cdp.send('Runtime.getHeapUsage')['usedSize']);out['memory'].append(r);save();print('MEM',edition,n,r['heap'],flush=True)
   # Same-scene model switch must reuse query image without a new request.
   if edition=='after':
    t=p.evaluate('performance.now()');sid=p.evaluate('rowFor(queryIndex+1).scene_id');p.select_option('#model','cmp_FM' if p.input_value('#model')!='cmp_FM' else 'cmp_B9');done(p);reqs=p.evaluate('t=>performance.getEntriesByType("resource").filter(r=>r.startTime>=t).map(r=>r.name)',t);assert not any('/main/'+sid+'.' in x for x in reqs);out['query_composite_reused_on_model_switch']=True
   c.close()
  b.close()
 assert not out['errors'],out['errors'];out['status']='PASS';save()
if __name__=='__main__':main()
