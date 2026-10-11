"""Opaque per-user sessions and revocable API tokens; raw secrets are never stored."""
import hashlib,secrets,hmac,time,json
from core import Rejected

def digest(token):return hashlib.sha256(token.encode()).hexdigest()
def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
def check_password(password,stored):return hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored)

def throttle(store,bucket):
    with store.lock:
        now=store.clock();store.db.execute('DELETE FROM auth_attempts WHERE at<?',(now-300,))
        if store.db.execute('SELECT COUNT(*) FROM auth_attempts WHERE bucket=?',(bucket,)).fetchone()[0]>=10:raise Rejected(429,'Too many account attempts. Try again in five minutes.')
        store.db.execute('INSERT INTO auth_attempts VALUES(?,?)',(bucket,now))

def create(store,username,password):
    name=username.strip().lower();key=secrets.token_hex(16);encoded=password_hash(password)
    with store.lock:
        if store.db.execute('SELECT id FROM accounts WHERE username=?',(name,)).fetchone():raise Rejected(409,'That username is unavailable')
        store.db.execute('INSERT INTO accounts VALUES(?,?,?,?)',(key,name,encoded,store.clock()))
    return key

def login(store,username,password):
    with store.lock:r=store.db.execute('SELECT * FROM accounts WHERE username=?',(username.strip().lower(),)).fetchone()
    encoded=r['password_hash'] if r else 'unavailable:'+('0'*64)
    valid=check_password(password,encoded)
    if not r or not valid:raise Rejected(401,'Username or password is incorrect')
    return r['id']

def issue(store,owner,kind='session',label='Browser'):
    raw=secrets.token_urlsafe(40);expires=store.clock()+(86400 if kind=='session' else 90*86400)
    with store.lock:store.db.execute('INSERT INTO access_tokens VALUES(?,?,?,?,?)',(digest(raw),owner,kind,label,expires))
    return raw

def identify(store,raw):
    if not raw:return None
    with store.lock:r=store.db.execute('SELECT owner FROM access_tokens WHERE hash=? AND expires>?',(digest(raw),store.clock())).fetchone()
    return r['owner'] if r else None

def revoke(store,raw):
    with store.lock:store.db.execute('DELETE FROM access_tokens WHERE hash=?',(digest(raw),))
