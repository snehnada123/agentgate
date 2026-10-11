import json
import hashlib
import secrets
import sqlite3
import time
from decimal import Decimal, InvalidOperation
from threading import Lock

CATALOG = [("phone", "Demo Smartphone", 49900, 40000, 2), ("laptop", "Demo Laptop", 89900, 75000, 1), ("camera", "Demo Camera", 35000, 30000, 3), ("headphones", "Demo Headphones", 9900, 8000, 5), ("tablet", "Demo Tablet", 25000, 22000, 2)]

class Rejected(Exception):
    def __init__(self, code, message): self.code, self.message = code, message

class Store:
    def __init__(self, database=":memory:", clock=time.time, seed=True):
        if database.startswith(('postgres://','postgresql://')):
            from db_adapter import Postgres
            self.db=Postgres(database)
        else:
            self.db = sqlite3.connect(database, check_same_thread=False, isolation_level=None)
            self.db.row_factory = sqlite3.Row
        self.lock = Lock(); self.clock = clock
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY,title TEXT,price INTEGER,floor INTEGER,stock INTEGER);
        CREATE TABLE IF NOT EXISTS reservations(token_hash TEXT PRIMARY KEY,agent TEXT,product TEXT,price INTEGER,expires REAL,used INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS listing_details(product TEXT PRIMARY KEY,category TEXT,description TEXT,photo TEXT,source TEXT);
        CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY,agent TEXT,product TEXT,title TEXT,price INTEGER,created REAL,status TEXT);
        CREATE TABLE IF NOT EXISTS import_owners(draft TEXT PRIMARY KEY,owner TEXT);
        CREATE TABLE IF NOT EXISTS external_products(id TEXT PRIMARY KEY,data TEXT,reviewed INTEGER DEFAULT 0,imported REAL);
        CREATE TABLE IF NOT EXISTS requests(agent TEXT,at REAL);
        CREATE TABLE IF NOT EXISTS memories(agent TEXT PRIMARY KEY,product TEXT,budget INTEGER,updated REAL);
        CREATE TABLE IF NOT EXISTS events(at REAL,agent TEXT,action TEXT,outcome TEXT);
        """)
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS profiles(owner TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE IF NOT EXISTS research_items(id TEXT PRIMARY KEY,owner TEXT NOT NULL,canonical TEXT NOT NULL,data TEXT NOT NULL,reviewed INTEGER DEFAULT 0,imported DOUBLE PRECISION,removed INTEGER DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS research_saved_url ON research_items(owner,canonical) WHERE reviewed=1 AND removed=0;
        CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created DOUBLE PRECISION);
        CREATE TABLE IF NOT EXISTS access_tokens(hash TEXT PRIMARY KEY,owner TEXT NOT NULL,kind TEXT,label TEXT,expires DOUBLE PRECISION);
        CREATE TABLE IF NOT EXISTS auth_attempts(bucket TEXT,at DOUBLE PRECISION);
        """)
        for row in self.db.execute('SELECT e.*,o.owner FROM external_products e LEFT JOIN import_owners o ON e.id=o.draft'):
            data=json.loads(row['data']);canonical=self.canonical_url(data.get('source_url',''))
            if not self.db.execute('SELECT id FROM research_items WHERE owner=? AND canonical=?',(row['owner'] or 'local-seller',canonical)).fetchone():
                self.db.execute('INSERT INTO research_items VALUES(?,?,?,?,?,?,0) ON CONFLICT(id) DO NOTHING',(row['id'],row['owner'] or 'local-seller',canonical,row['data'],row['reviewed'],row['imported']))
        if seed:self.db.executemany("INSERT OR IGNORE INTO products VALUES(?,?,?,?,?)", CATALOG)

    def allow(self, agent):
        with self.lock:
            now = self.clock()
            self.db.execute("DELETE FROM requests WHERE at<?", (now-60,))
            count = self.db.execute("SELECT count(*) FROM requests WHERE agent=?", (agent,)).fetchone()[0]
            if count >= 20: raise Rejected(429,"Agent request limit: 20 per rolling minute")
            self.db.execute("INSERT INTO requests VALUES(?,?)", (agent,now))

    def available(self, row):
        holds = self.db.execute("SELECT count(*) FROM reservations WHERE product=? AND used=0 AND expires>?", (row['id'],self.clock())).fetchone()[0]
        return max(0,row['stock']-holds)

    def public(self, row):
        details=self.db.execute('SELECT * FROM listing_details WHERE product=?',(row['id'],)).fetchone()
        return dict(id=row['id'],title=row['title'],price_cents=row['price'],currency='USD',available=self.available(row),category=details['category'] if details else row['id'],description=details['description'] if details else '',photo_url=details['photo'] if details else '',source=details['source'] if details else 'sample',simulation=not bool(details),payment_status='Payments not connected')

    def browse(self):
        with self.lock: return [self.public(r) for r in self.db.execute('SELECT * FROM products')]

    def reserve(self, agent, product, offer):
        try:
            amount=Decimal(str(offer))
            if not amount.is_finite() or amount <= 0 or amount > 100000 or amount.as_tuple().exponent < -2: raise InvalidOperation
            cents=int(amount*100)
        except (InvalidOperation,ValueError,TypeError): raise Rejected(400,'Offer must be a positive USD amount with at most two decimals')
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                row=self.db.execute('SELECT * FROM products WHERE id=?',(product,)).fetchone()
                if row is None: raise Rejected(404,'Unknown product')
                if cents < row['floor']: raise Rejected(422,'Offer does not meet seller policy')
                if self.available(row)<1: raise Rejected(409,'No stock available for reservation')
                token=secrets.token_urlsafe(32); expires=self.clock()+90
                self.db.execute('INSERT INTO reservations(token_hash,agent,product,price,expires) VALUES(?,?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),agent,product,cents,expires))
                self.db.execute('COMMIT')
                return dict(simulation=not bool(self.db.execute('SELECT 1 FROM listing_details WHERE product=?',(product,)).fetchone()),token=token,expires_at=expires,price_cents=cents,product_id=product,privacy='Private seller contact fields are never included in offers',checkout='Creates an unpaid order only; no payment processed')
            except Exception:
                self.db.execute('ROLLBACK'); raise

    def checkout(self,agent,token):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                digest=hashlib.sha256(token.encode()).hexdigest()
                row=self.db.execute('SELECT * FROM reservations WHERE token_hash=?',(digest,)).fetchone()
                if row is None or row['agent']!=agent or row['used'] or row['expires']<=self.clock(): raise Rejected(409,'Reservation invalid, expired, already used or owned by another agent')
                changed=self.db.execute('UPDATE products SET stock=stock-1 WHERE id=? AND stock>0',(row['product'],)).rowcount
                if changed != 1: raise Rejected(409,'Stock unavailable')
                self.db.execute('UPDATE reservations SET used=1 WHERE token_hash=?',(digest,))
                order_id=secrets.token_hex(8)
                item=self.db.execute('SELECT title FROM products WHERE id=?',(row['product'],)).fetchone()
                real=bool(self.db.execute('SELECT 1 FROM listing_details WHERE product=?',(row['product'],)).fetchone())
                self.db.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?)',(order_id,agent,row['product'],item['title'],row['price'],self.clock(),'unpaid'))
                self.db.execute('COMMIT')
                return dict(simulation=not real,order_id=order_id,product_id=row['product'],price_cents=row['price'],status='unpaid',payment='No payment collected. Seller must arrange payment and fulfillment separately.' if real else 'No money moved; demo order only')
            except Exception: self.db.execute('ROLLBACK'); raise

    def record(self,agent,action,outcome):
        with self.lock: self.db.execute('INSERT INTO events VALUES(?,?,?,?)',(self.clock(),agent,action,outcome))

    def cancel(self,agent,token):
        with self.lock:
            digest=hashlib.sha256(token.encode()).hexdigest()
            self.db.execute('UPDATE reservations SET expires=? WHERE token_hash=? AND agent=? AND used=0',(self.clock(),digest,agent))
        return {'simulation':True,'cancelled':True}

    def reset_demo(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute('DELETE FROM reservations')
                self.db.execute('DELETE FROM events')
                for product in CATALOG:self.db.execute('UPDATE products SET stock=? WHERE id=?',(product[4],product[0]))
                self.db.execute('COMMIT')
            except Exception:self.db.execute('ROLLBACK');raise
        return {'simulation':True,'reset':True}

    def stats(self):
        with self.lock:
            return dict(events=[dict(r) for r in self.db.execute('SELECT * FROM events ORDER BY at DESC LIMIT 30')],velocity=self.db.execute('SELECT count(*) FROM requests WHERE at>?',(self.clock()-60,)).fetchone()[0],limit=20)

    def memory(self,agent):
        with self.lock:
            row=self.db.execute('SELECT product,budget,updated FROM memories WHERE agent=?',(agent,)).fetchone()
            return dict(row) if row else None

    def save_memory(self,agent,product,budget):
        with self.lock:
            self.db.execute('INSERT INTO memories VALUES(?,?,?,?) ON CONFLICT(agent) DO UPDATE SET product=excluded.product,budget=excluded.budget,updated=excluded.updated',(agent,product,budget,self.clock()))
        return self.memory(agent)

    def forget(self,agent):
        with self.lock:self.db.execute('DELETE FROM memories WHERE agent=?',(agent,))
        return {'forgotten':True}

    def create_listing(self,title,category,price,floor,stock,description='',photo=''):
        def cents(value):
            try:
                x=Decimal(value)
                if not x.is_finite() or x<=0 or x>100000 or x.as_tuple().exponent < -2:raise InvalidOperation
                return int(x*100)
            except (InvalidOperation,ValueError):raise Rejected(400,'Prices require positive USD amounts with at most two decimals')
        price,floor=cents(price),cents(floor)
        if floor>price:raise Rejected(400,'Minimum offer cannot exceed the listing price')
        if not title.strip() or category not in ['phone','laptop','camera','headphones','tablet']:raise Rejected(400,'Enter a title and supported category')
        if type(stock) is not int or stock<0 or stock>10000:raise Rejected(400,'Stock must be between 0 and 10,000')
        product='listing_'+secrets.token_hex(8)
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                self.db.execute('INSERT INTO products VALUES(?,?,?,?,?)',(product,title.strip(),price,floor,stock))
                self.db.execute('INSERT INTO listing_details VALUES(?,?,?,?,?)',(product,category,description,photo,'seller-entered; not independently verified'))
                self.db.execute('COMMIT')
            except Exception:self.db.execute('ROLLBACK');raise
        return {'id':product,'created':True}

    def seller_status(self):
        with self.lock:
            return {'listings':[dict(r) for r in self.db.execute('SELECT p.*,d.category,d.description,d.photo FROM products p JOIN listing_details d ON p.id=d.product')],'orders':[dict(r) for r in self.db.execute('SELECT * FROM orders ORDER BY created DESC')]}

    def set_stock(self,product,stock):
        with self.lock:
            row=self.db.execute('SELECT * FROM products WHERE id=? AND id IN (SELECT product FROM listing_details)',(product,)).fetchone()
            if not row:raise Rejected(404,'Seller listing not found')
            held=row['stock']-self.available(row)
            if stock<held:raise Rejected(409,'Stock cannot be lower than active reservations')
            self.db.execute('UPDATE products SET stock=? WHERE id=?',(stock,product))
        return {'updated':True}

    @staticmethod
    def canonical_url(url):
        from urllib.parse import urlsplit,urlunsplit,parse_qsl,urlencode
        p=urlsplit(url)
        query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith(('utm_','_pos','_sid','_ss','gclid','fbclid'))))
        return urlunsplit((p.scheme.lower(),p.netloc.lower(),p.path.rstrip('/') or '/',query,''))

    def save_import(self,data,owner="local-seller"):
        key=secrets.token_hex(16)
        with self.lock:
            self.db.execute('INSERT INTO research_items VALUES(?,?,?,?,0,?,0)',(key,owner,self.canonical_url(data.get('source_url','')),json.dumps(data),self.clock()))
        return {'draft_id':key,'product':data}

    def publish_import(self,key,owner=None):
        with self.lock:
            row=self.db.execute('SELECT * FROM research_items WHERE id=? AND removed=0',(key,)).fetchone()
            if not row or (owner is not None and row['owner']!=owner):raise Rejected(404,'Import draft not found for this identity')
            existing=self.db.execute('SELECT id FROM research_items WHERE owner=? AND canonical=? AND reviewed=1 AND removed=0',(row['owner'],row['canonical'])).fetchone()
            if existing:
                self.db.execute('UPDATE research_items SET data=?,imported=? WHERE id=?',(row['data'],row['imported'],existing['id']))
                return {'saved':True,'id':existing['id'],'deduplicated':True,'reservable':False}
            self.db.execute('UPDATE research_items SET reviewed=1 WHERE id=?',(key,))
        return {'saved':True,'id':key,'reservable':False}

    def imports(self,owner=None):
        with self.lock:
            rows=self.db.execute('SELECT * FROM research_items WHERE reviewed=1 AND removed=0'+(' AND owner=?' if owner is not None else '')+' ORDER BY imported DESC',(owner,) if owner is not None else ())
            return [{'id':r['id'],**json.loads(r['data']),'imported_at':r['imported']} for r in rows]

    def reference(self,key,owner):
        with self.lock:
            r=self.db.execute('SELECT * FROM research_items WHERE id=? AND owner=? AND removed=0',(key,owner)).fetchone()
            if not r:raise Rejected(404,'Reference not found')
            return {'id':r['id'],**json.loads(r['data'])}

    def remove_reference(self,key,owner):
        with self.lock:
            if not self.db.execute('UPDATE research_items SET removed=1 WHERE id=? AND owner=? AND removed=0',(key,owner)).rowcount:raise Rejected(404,'Reference not found')
        return {'removed':True,'id':key,'recoverable':True}

    def restore_reference(self,key,owner):
        with self.lock:
            r=self.db.execute('SELECT * FROM research_items WHERE id=? AND owner=? AND removed=1',(key,owner)).fetchone()
            if not r:raise Rejected(404,'Removed reference not found')
            if self.db.execute('SELECT id FROM research_items WHERE owner=? AND canonical=? AND reviewed=1 AND removed=0',(owner,r['canonical'])).fetchone():raise Rejected(409,'This source is already in your shortlist')
            self.db.execute('UPDATE research_items SET removed=0 WHERE id=?',(key,))
        return {'restored':True}

    def refresh_reference(self,key,owner,data):
        with self.lock:
            old=self.db.execute('SELECT data FROM research_items WHERE id=? AND owner=? AND removed=0',(key,owner)).fetchone()
            if not old:raise Rejected(404,'Reference not found')
            previous=json.loads(old['data']);data={**data,'previous_price':previous.get('price'),'previous_observed_at':previous.get('observed_at')}
            self.db.execute('UPDATE research_items SET data=?,imported=? WHERE id=? AND owner=?',(json.dumps(data),self.clock(),key,owner))
        return {'id':key,**data}

    def profile(self,owner):
        with self.lock:
            r=self.db.execute('SELECT data FROM profiles WHERE owner=?',(owner,)).fetchone()
            return json.loads(r['data']) if r else {}

    def save_profile(self,owner,data):
        with self.lock:self.db.execute('INSERT INTO profiles VALUES(?,?) ON CONFLICT(owner) DO UPDATE SET data=excluded.data',(owner,json.dumps(data)))
        return data
