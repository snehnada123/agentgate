import unittest
from unittest.mock import patch
from web_search import RetailerHTML,search,search_terms,classify_match
HTML='<a href="/product/999">Unrelated nav</a><li itemtype="https://schema.org/Product"><a itemprop="name" content="Example Board" href="/product/123">Example Board</a></li><li itemtype="https://schema.org/Product"><a itemprop="name" content="Bad" href="https://localhost/product/1">Bad</a></li>'
class SearchTests(unittest.TestCase):
 def test_parse_ignores_navigation_and_other_hosts(self):
  p=RetailerHTML();p.feed(HTML);self.assertEqual(p.results,[{'title':'Example Board','source_url':'https://www.adafruit.com/product/123'}])
 def test_success_and_extraction_failures_are_explicit(self):
  with patch('web_search.read_search',return_value=HTML),patch('web_search.extract',return_value={'title':'Example Board','price':'20','currency':'USD'}):
   r=search('board');self.assertEqual(len(r['products']),1);self.assertIn('Adafruit',r['coverage'])
  with patch('web_search.read_search',return_value=HTML),patch('web_search.extract',side_effect=ValueError('blocked')):
   r=search('board');self.assertEqual(r['products'],[]);self.assertEqual(r['failed_extractions'],1)
 def test_blocked_search_never_fabricates_products(self):
  with patch('web_search.read_search',side_effect=ValueError('Source unavailable')):
   r=search('board');self.assertEqual(r['products'],[]);self.assertEqual(r['mode'],'source unavailable')
 def test_accessories_and_variant_mismatches_are_not_matching_products(self):
  self.assertFalse(classify_match('Raspberry Pi 5 Cable','Raspberry Pi 5')['comparison_eligible'])
  self.assertTrue(classify_match('Raspberry Pi 5 Cable','Raspberry Pi 5 cable')['comparison_eligible'])
  self.assertFalse(classify_match('Raspberry Pi 5 - 4 GB RAM','Raspberry Pi 5 8GB')['comparison_eligible'])
  self.assertTrue(classify_match('Raspberry Pi 5 - 8 GB RAM','Raspberry Pi 5 8GB')['comparison_eligible'])
 def test_query_keeps_model_and_removes_budget(self):
  self.assertEqual(search_terms('Find a Raspberry Pi 5 under $150'),'Raspberry Pi 5')
if __name__=='__main__':unittest.main()
