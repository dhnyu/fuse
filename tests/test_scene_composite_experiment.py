"""Scientific-display invariants, without full-size source fixtures."""
import importlib.util
from pathlib import Path
import unittest
import numpy as np
from PIL import Image
spec=importlib.util.spec_from_file_location('composite',Path(__file__).resolve().parents[1]/'scripts/build_scene_composite_experiment.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class CompositeTest(unittest.TestCase):
 def test_flat_dem_does_not_manufacture_relief(self):
  h,g=m.hillshade(np.ones((17,17)),np.ones((17,17),bool),17)
  lc=Image.new('RGBA',(17,17),(51,160,44,255))
  for name in m.VARIANTS:
   self.assertTrue(np.array_equal(np.asarray(lc),np.asarray(m.composite_base(lc,h,g,name))))
 def test_northwest_illumination_orientation(self):
  # Upward elevations to SE imply a NW-facing normal, toward azimuth 315.
  y,x=np.mgrid[:17,:17];valid=np.ones((17,17),bool)
  lit,_=m.hillshade((x+y)*.05,valid,17);dark,_=m.hillshade(-(x+y)*.05,valid,17)
  self.assertGreater(lit.mean(),dark.mean())
 def test_nodata_is_neutral_not_a_hill(self):
  z=np.zeros((17,17));valid=np.ones_like(z,bool);valid[8,8]=False;z[8,8]=-32767
  h,g=m.hillshade(z,valid,17);self.assertFalse(g[8,8]);self.assertTrue(np.allclose(h,np.sqrt(.5)))
 def test_lc_nearest_grid_and_alpha(self):
  a=np.zeros((2,2,4),dtype='uint8');a[0,0]=[254,230,194,255];a[1,1]=[23,57,255,255]
  result=np.asarray(m.composite_base(Image.fromarray(a),np.ones((4,4)),np.ones((4,4),bool),'A'))
  self.assertTrue(np.array_equal(result,np.repeat(np.repeat(a,2,0),2,1)))
 def test_geometry_and_north_up_alignment(self):
  svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 500 500"><rect width="500" height="500"/><g transform="translate(0 500) scale(1 -1)"><path fill="#667085" d="M 0,0 L 0,500 L 500,500 z"/><polyline stroke="#e4a11b" points="0,0 500,500"/><circle fill="#c83e63" cx="250" cy="250" r="1"/></g></svg>'
  for style in m.STYLES:
   out,counts=m.vector_overlay(svg,style,m.image_uri(Image.new('RGBA',(2,2))))
   root=m.ET.fromstring(out);image=root[0];self.assertEqual([image.get(k) for k in ['x','y','width','height']],['0','0','500','500']);self.assertEqual(root[1].get('transform'),'translate(0 500) scale(1 -1)');self.assertEqual(counts,{'building':1,'road':1,'poi':1});self.assertIn('M 0,0 L 0,500 L 500,500 z',out)
if __name__=='__main__':unittest.main()
