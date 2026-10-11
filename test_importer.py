import unittest
from unittest.mock import patch
from product_importer import parse,target,extract
from core import Store,Rejected
class ImportTests(unittest.TestCase):
 def test_structured_product(self):
  p=parse('<script type="application/ld+json">{"@graph":[{"@type":"Product","name":"Camera","offers":{"price":"300.00","priceCurrency":"USD"},"image":"/image.jpg"}]}</script>','https://example.com/product')
  self.assertEqual(p['price'],'300.00');self.assertEqual(p['currency'],'USD');self.assertFalse(p['reservable']);self.assertEqual(p['photo_url'],'https://example.com/image.jpg')
 def test_review_before_publish(self):
  s=Store(seed=False);d=s.save_import({'title':'Reference','reservable':False});self.assertEqual(s.imports(),[]);s.publish_import(d['draft_id']);self.assertEqual(len(s.imports()),1)
  with self.assertRaises(Rejected):s.reserve('buyer',d['draft_id'],'300')
 def test_private_network_denied(self):
  with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaises(ValueError):target('https://example.com/product')
  for url in ['http://example.com','https://user:password@example.com','https://example.com:8080']:
   with self.assertRaises(ValueError):target(url)
 def test_robots_denial(self):
  with patch('product_importer.target',return_value=(__import__('urllib.parse',fromlist=['urlsplit']).urlsplit('https://example.com/item'),'93.184.216.34')),patch('product_importer.fetch',return_value=(200,None,'text/plain','User-agent: *\nDisallow: /')):
   with self.assertRaises(ValueError):extract('https://example.com/item')
if __name__=='__main__':unittest.main()
