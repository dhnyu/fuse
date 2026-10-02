#!/usr/bin/env python3
"""Lossless transport packing of our own Composite C PNGs; no scientific inputs."""
from pathlib import Path
import concurrent.futures,io,time,hashlib
import numpy as np
from PIL import Image
import build_retrieval_composite_c as b
x=b.ex

def pack(arg):
 src,dst=map(Path,arg);im=Image.open(src).convert('RGBA');im.save(dst,format='WEBP',lossless=True,method=4)
 with Image.open(dst) as decoded:assert np.array_equal(np.asarray(im),np.asarray(decoded.convert('RGBA')))
 return src.stem,x.sha(dst),dst.stat().st_size,hashlib.sha256(im.tobytes()).hexdigest()
def main():
 start=time.time();a=x.read(b.AUDIT/'assets.json');old=Path(a['root']);x.write(b.AUDIT/'png_assets.json',a)
 identity={**a['identity'],'lossless_parent':str(old),'lossless_parent_manifest_sha256':x.sha(old/'manifest.json'),'transport':'WebP lossless method4, RGBA exact, 500x500','packing_code_sha256':x.sha(__file__)};gid='s10composite_c_webp_'+hashlib.sha256(x.enc(identity)).hexdigest()[:24];root=b.BASE/'s10_composite_c'/gid;assert not root.exists();stage=root.with_name('.staging_'+gid);stage.mkdir();(stage/'main').mkdir()
 for name in ['meta','thumb','layers']:(stage/name).symlink_to(old/name)
 catalog=x.read(old/'catalog.json');catalog['generation_id']=gid;catalog['identity']=identity;rows=[dict(zip(catalog['columns'],r)) for r in catalog['rows']];byid={r['scene_id']:r for r in rows};sizes=[];matches={}
 with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
  for n,(sid,sha,size,pixel) in enumerate(pool.map(pack,[(str(old/'main'/(r['scene_id']+'.png')),str(stage/'main'/(r['scene_id']+'.webp'))) for r in rows],chunksize=8)):
   byid[sid]['main_sha256']=sha;sizes.append(size)
   if sid in a['visual_regression']:matches[sid]={'rgba_exact':True,'rgba_sha256':pixel,'experiment_png_sha256':a['visual_regression'][sid]['sha256']}
   if (n+1)%500==0:print(n+1,round(time.time()-start,1),flush=True)
 catalog['rows']=[[r[k] for k in catalog['columns']] for r in rows];x.write(stage/'catalog.json',catalog)
 receipt={**a,'identity':identity,'generation_id':gid,'root':str(root),'catalog_sha256':x.sha(stage/'catalog.json'),'main_format':'webp','visual_regression':matches,'packing_seconds':time.time()-start,'rgba_exact_count':9000,'parent_png_root':str(old),'sizes':{**a['sizes'],'main':{'count':9000,'median':float(np.median(sizes)),'p95':float(np.quantile(sizes,.95)),'max':max(sizes),'total':sum(sizes)}}};x.write(stage/'manifest.json',receipt);stage.rename(root);x.write(b.AUDIT/'assets.json',receipt);print(root,receipt['sizes']['main'],receipt['packing_seconds'],flush=True)
if __name__=='__main__':main()
