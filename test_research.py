import unittest
from core import Store,Rejected
import accounts
from comparison import compare
from evidence import match_pair
from product_importer import parse

class ResearchFlowTests(unittest.TestCase):
 def test_accounts_are_isolated_and_token_revocation_works(self):
  s=Store(seed=False)
  a=accounts.create(s,'alice','long-test-password-1');b=accounts.create(s,'bob','long-test-password-2')
  self.assertEqual(accounts.login(s,'alice','long-test-password-1'),a)
  with self.assertRaises(Rejected):accounts.login(s,'alice','wrong-password-123')
  token=accounts.issue(s,a,'api');self.assertEqual(accounts.identify(s,token),a)
  accounts.revoke(s,token);self.assertIsNone(accounts.identify(s,token))
  draft=s.save_import({'title':'Uno','source_url':'https://store.arduino.cc/products/uno?utm_source=x','price':'29.30','currency':'EUR'},a)
  s.publish_import(draft['draft_id'],a)
  self.assertEqual(len(s.imports(a)),1);self.assertEqual(s.imports(b),[])
  with self.assertRaises(Rejected):s.reference(draft['draft_id'],b)
 def test_dedupe_remove_restore_refresh(self):
  s=Store(seed=False);url='https://example.com/product/uno'
  one=s.save_import({'title':'Uno','source_url':url,'price':'20'},'alice')['draft_id'];s.publish_import(one,'alice')
  two=s.save_import({'title':'Uno','source_url':url+'?utm_campaign=test','price':'21'},'alice')['draft_id']
  saved=s.publish_import(two,'alice');self.assertTrue(saved['deduplicated']);self.assertEqual(saved['id'],one)
  s.remove_reference(one,'alice');self.assertEqual(s.imports('alice'),[])
  s.restore_reference(one,'alice');self.assertEqual(len(s.imports('alice')),1)
  s.refresh_reference(one,'alice',{'title':'Uno','source_url':url,'price':'22','observed_at':'2026-10-11T12:00:00Z'})
  self.assertEqual(s.imports('alice')[0]['previous_price'],'21')
 def test_variant_identity_and_budget_evidence(self):
  a={'title':'Arduino Uno Rev3','brand':'Arduino','mpn':'A000066','price':'29.30','currency':'EUR','condition':'new','source_url':'https://store.arduino.cc/products/uno'}
  b={**a,'title':'Arduino Uno Rev3 second listing','source_url':'https://example.com/uno'}
  self.assertEqual(match_pair(a,b)['status'],'identifier_match')
  b['mpn']='DIFFERENT';self.assertEqual(match_pair(a,b)['status'],'identifier_mismatch')
  c={**a,'price_kind':'from'};r=compare([c],30,'EUR',{'brands':['Arduino'],'requirements':['USB-C']})
  self.assertEqual(r['products'][0]['budget_status'],'variant_price_unknown')
  self.assertIsNone(r['lowest_listed_price_id'])
  self.assertEqual(r['products'][0]['preference_checks'][1]['status'],'unknown')
 def test_source_stock_is_snapshot(self):
  html='''<script type="application/ld+json">{"@type":"Product","name":"Arduino Uno Rev3","brand":{"name":"Arduino"},"mpn":"A000066","offers":{"@type":"Offer","price":"29.30","priceCurrency":"EUR","availability":"https://schema.org/InStock"}}</script>'''
  p=parse(html,'https://store.arduino.cc/products/uno')
  self.assertEqual(p['brand'],'Arduino');self.assertEqual(p['availability_code'],'InStock')
  self.assertIn('at capture',p['availability']);self.assertEqual(p['total_cost_status'].split(';')[0],'unknown')
if __name__=='__main__':unittest.main()
