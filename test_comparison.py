import unittest
from comparison import compare
class ComparisonTests(unittest.TestCase):
 def test_currency_missing_budget_and_practice(self):
  data=[{'id':'a','price':'99','currency':'USD'},{'id':'b','price':'201','currency':'USD'},{'id':'c','price':'10','currency':'GBP'},{'id':'d','price':None,'currency':'USD'},{'id':'e','price':'1','currency':'USD','availability':'fictional practice inventory'}]
  r=compare(data,'200');self.assertEqual(r['lowest_listed_price_id'],'a');self.assertEqual([p['budget_status'] for p in r['products']],['within_budget','over_budget','different_currency','unknown','within_budget'])
 def test_accessory_is_not_lowest_matching_product(self):
  r=compare([{'id':'board','price':'130','currency':'USD'},{'id':'cable','price':'3','currency':'USD','comparison_eligible':False}],'150')
  self.assertEqual(r['lowest_listed_price_id'],'board')
 def test_no_guessed_price(self):
  for price in ['NaN','Infinity','-1','invalid']:
   self.assertIsNone(compare([{'price':price,'currency':'USD'}],'100')['products'][0]['within_budget'])
 def test_invalid_budget(self):
  for value in ['NaN','0','-10']:
   with self.assertRaises(ValueError):compare([],value)
if __name__=='__main__':unittest.main()
