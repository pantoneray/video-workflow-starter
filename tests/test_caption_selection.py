import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from caption_selection import plan
VENDOR=Path(__file__).resolve().parents[1]/'tools/shorts-caption-templates'

def suggestion(templates,contrast):
 return {'recommended_templates':templates,'contrast':contrast,'review_required':['phone readability']}

class SelectionTests(unittest.TestCase):
 def test_dark_bright_and_highlight_selection(self):
  with patch('caption_selection.recommend',return_value=suggestion(['D','B'],None)):
   settings,r=plan('video',VENDOR)
   self.assertTrue(settings['id'].startswith('D'))
   self.assertEqual(r['selection'],'automatic_sample_recommendation')
   settings,r=plan('video',VENDOR,highlight='green')
   self.assertTrue(settings['id'].startswith('B'))
  with patch('caption_selection.recommend',return_value=suggestion(['B','C'],'box')) as assess:
   settings,r=plan('video',VENDOR,shift_up=100)
   self.assertTrue(settings['id'].startswith('B'));self.assertTrue(settings['captions']['box'])
   self.assertEqual(assess.call_args.kwargs['y'],settings['captions']['y_center'])
 def test_explicit_choice_not_silently_changed(self):
  with patch('caption_selection.recommend',return_value=suggestion(['B','C'],'box')):
   settings,r=plan('video',VENDOR,template='D')
   self.assertTrue(settings['id'].startswith('D'));self.assertEqual(r['selection'],'explicit_preserved')
   self.assertIsNone(r['applied_contrast']);self.assertTrue(r['explicit_style_differs_from_suggestion'])
   settings,r=plan('video',VENDOR,template='D',contrast='box')
   self.assertTrue(settings['captions']['box'])
 def test_assessment_failure_does_not_select_fallback(self):
  with patch('caption_selection.recommend',side_effect=ValueError('bad frame')):
   with self.assertRaises(ValueError):plan('video',VENDOR)

if __name__=='__main__':unittest.main()
