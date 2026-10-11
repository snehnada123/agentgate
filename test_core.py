import unittest
from concurrent.futures import ThreadPoolExecutor
from core import Store, Rejected

class GatewayTests(unittest.TestCase):
    def setUp(self):self.now=1000;self.store=Store(clock=lambda:self.now)
    def tearDown(self):self.store.db.close()
    def test_public_field_allowlist(self):
        self.assertEqual(set(self.store.browse()[0]),{'id','title','price_cents','currency','available','simulation','category','description','photo_url','source','payment_status'})
        self.assertNotIn('floor',self.store.browse()[0])
    def test_floor_price_cannot_be_bypassed(self):
        with self.assertRaises(Rejected):self.store.reserve('a','phone','399.99')
        self.assertEqual(self.store.reserve('a','phone','400')['price_cents'],40000)
    def test_invalid_money_is_rejected(self):
        for amount in ['NaN','Infinity','-4','400.001','fake']:
            with self.assertRaises(Rejected):self.store.reserve('a','phone',amount)
    def test_single_use_and_bound_agent(self):
        r=self.store.reserve('a','phone','400')
        with self.assertRaises(Rejected):self.store.checkout('b',r['token'])
        self.assertEqual(self.store.checkout('a',r['token'])['payment'],'No money moved; demo order only')
        with self.assertRaises(Rejected):self.store.checkout('a',r['token'])
    def test_expired_hold_releases_stock(self):
        r=self.store.reserve('a','laptop','750');self.now+=91
        with self.assertRaises(Rejected):self.store.checkout('a',r['token'])
        self.assertEqual(next(p for p in self.store.browse() if p['id']=='laptop')['available'],1)
    def test_concurrent_buyers_cannot_oversell(self):
        def attempt(i):
            try:return self.store.reserve(str(i),'laptop','750')
            except Rejected:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(attempt,range(20)))
        self.assertEqual(sum(r is not None for r in results),1)
    def test_rolling_limit(self):
        for _ in range(20):self.store.allow('a')
        with self.assertRaises(Rejected):self.store.allow('a')
        self.now+=61;self.store.allow('a')
    def test_sql_injection_is_not_product(self):
        with self.assertRaises(Rejected):self.store.reserve('a',"phone' OR 1=1 --",'400')
        self.assertEqual(len(self.store.browse()),5)
    def test_demo_reset_restores_stock_and_invalidates_tokens(self):
        r=self.store.reserve('a','laptop','750')
        self.store.reset_demo()
        with self.assertRaises(Rejected):self.store.checkout('a',r['token'])
        self.assertEqual(next(p for p in self.store.browse() if p['id']=='laptop')['available'],1)

if __name__=='__main__':unittest.main()
