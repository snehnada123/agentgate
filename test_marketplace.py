import unittest
from core import Store,Rejected
class MarketplaceTests(unittest.TestCase):
 def test_seller_listing_privacy_order_and_stock(self):
  s=Store(seed=False);self.assertEqual(s.browse(),[])
  p=s.create_listing('Owner camera','camera','350','300',1,'A seller description')['id']
  item=s.browse()[0];self.assertFalse(item['simulation']);self.assertNotIn('floor',item);self.assertEqual(item['category'],'camera')
  with self.assertRaises(Rejected):s.reserve('buyer',p,'299')
  r=s.reserve('buyer',p,'300')
  with self.assertRaises(Rejected):s.set_stock(p,0)
  with self.assertRaises(Rejected):s.reserve('other',p,'350')
  order=s.checkout('buyer',r['token']);self.assertEqual(order['status'],'unpaid');self.assertFalse(order['simulation']);self.assertEqual(s.browse()[0]['available'],0)
  self.assertEqual(len(s.seller_status()['orders']),1)
  with self.assertRaises(Rejected):s.checkout('buyer',r['token'])
 def test_invalid_seller_prices(self):
  s=Store(seed=False)
  for price,floor in [('1','2'),('NaN','1'),('10','1.001')]:
   with self.assertRaises(Rejected):s.create_listing('Item','camera',price,floor,1)
if __name__=='__main__':unittest.main()
