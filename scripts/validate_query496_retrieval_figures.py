#!/usr/bin/env python3
"""Validate figure assembly without computing embeddings, similarities or ranks."""
from pathlib import Path
import argparse,json,hashlib,subprocess,re,xml.etree.ElementTree as ET

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('output',type=Path);ap.add_argument('--dissertation',type=Path,required=True);a=ap.parse_args();o=a.output;fig=a.dissertation/'template/materials/figures';d=read=json.loads((fig/'results-03-query496-assets/selection.json').read_text());p=json.loads((o/'provenance.json').read_text());checks=[]
 def check(name,ok):checks.append(dict(check=name,status='PASS' if ok else 'FAIL'));assert ok,name
 check('all_source_hashes_unchanged',all(sha(f)==h for f,h in p['source_sha256'].items()))
 check('same_query_in_both_modes',[r['scene_id'] for r in d if r['band']=='query']==['scn_0dea54258b31af6c02290e8b']*2)
 check('all_copied_images_byte_exact',all(sha(fig/'results-03-query496-assets'/(r['scene_id']+'.png'))==r['image_sha256'] for r in d))
 check('nonlocal_2km',all(r['distance_m']>=2000 for r in d if r['mode']=='nonlocal' and r['band']!='query'))
 for m in ['standard','nonlocal']:
  rows=[r for r in d if r['mode']==m];check(m+'_11_unique_panels',len(rows)==11 and len({r['scene_id'] for r in rows})==11)
  pdf=o/(m+'_final.pdf');text=subprocess.check_output(['pdftotext',str(pdf),'-'],text=True);flat=re.sub(r'\s+','',text)
  for r in rows:
   assert re.sub(r'\s+','',r['title']) in flat
   assert re.sub(r'\s+','',r['district_en']+', '+r['dong_en']) in flat
   if r['band']!='query':
    assert 'Globalrank'+str(r['rank']) in flat and 'cosine'+r['similarity_display'] in flat and re.sub(r'\s+','',r['distance_display']) in flat
  check(m+'_rendered_metadata',True)
  images=subprocess.check_output(['pdfimages','-list',str(pdf)],text=True).splitlines();check(m+'_11_images',sum(bool(re.search(r'^\s*1\s+\d+\s+image\s',line)) for line in images)==11)
  check(m+'_single_page',bool(re.search(r'Pages:\s+1\b',subprocess.check_output(['pdfinfo',str(pdf)],text=True))))
 ns={'x':'http://www.w3.org/1999/xhtml'};xml=ET.parse(o/'dissertation_bbox.html');pages=xml.findall('.//x:page',ns);figure_pages=[]
 for i,page in enumerate(pages):
  words=page.findall('x:word',ns);text=' '.join(w.text or '' for w in words)
  if 'Lower' in text and ('8999' in text or '8803' in text):
   footer=[w for w in words if float(w.attrib['yMax'])>float(page.attrib['height'])-25];body=[w for w in words if w not in footer]
   check('page_'+str(i+1)+'_body_bounds',max(float(w.attrib['yMax']) for w in body)<float(page.attrib['height'])-15*72/25.4)
   check('page_'+str(i+1)+'_caption', 'Qualitative retrieval example under' in text)
   figure_pages.append(i+1)
 check('two_integrated_figure_pages',len(figure_pages)==2)
 section=(a.dissertation/'template/sections/chapters/results/03-spatial-scene-retrieval.typ').read_text();check('section_order',section.index('=== Qualitative Retrieval Examples')<section.index('=== Overall Retrieval Behavior'))
 check('labels_once',section.count('<fig:qualitative-retrieval-standard>')==section.count('<fig:qualitative-retrieval-nonlocal>')==1)
 result={'status':'PASS WITH CONDITIONS','checks':checks,'figure_pdf_pages':figure_pages,'warnings':['Existing unavailable font families HYsinMyeongJo, Noto Serif KR, Batang; fallback used for existing document text.','Remote inspection URL unavailable; local viewer index verifies query 496.'],'scientific_artifact_changed':False,'ranking_or_embedding_regenerated':False}
 (o/'validation.json').write_text(json.dumps(result,indent=2));print('PASS',len(checks),'checks; PDF pages',figure_pages)
if __name__=='__main__':main()
