import os
import secrets
import re
from decimal import Decimal
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from core import Store, Rejected
import providers

ROOT=Path(__file__).parent
load_dotenv(ROOT/'.env')
CLOUD=bool(os.getenv('VERCEL') or os.getenv('RENDER') or os.getenv('DATABASE_URL'))
if CLOUD and not os.getenv('DATABASE_URL'):raise RuntimeError('DATABASE_URL is required for persistent cloud storage')
MARKETPLACE=os.getenv('MARKETPLACE_MODE')=='1' or CLOUD
store=Store(os.getenv('DATABASE_URL') if CLOUD else os.getenv('AGENTGATE_DB',str(ROOT/('marketplace.sqlite' if MARKETPLACE else 'agentgate.sqlite'))),seed=not MARKETPLACE)
KEY=os.getenv('AGENT_API_KEY','local-demo-key')
if os.getenv('SENTRY_DSN'):
    import sentry_sdk
    sentry_sdk.init(dsn=os.environ['SENTRY_DSN'],send_default_pii=False,max_request_body_size='never',traces_sample_rate=1.0,before_send=lambda event,hint: {k:v for k,v in event.items() if k not in ['request','user','breadcrumbs']},before_send_transaction=lambda event,hint: {k:v for k,v in event.items() if k not in ['request','user','breadcrumbs']})
app=FastAPI(title='AgentGate product research',description='Multi-store discovery, evidence-backed comparisons and private shopping memory.')

def authenticate(request:Request,x_agent_key:str=Header(default='')):
    import accounts
    bearer=request.headers.get('authorization','')
    supplied=bearer[7:] if bearer.lower().startswith('bearer ') else x_agent_key
    cookie=request.cookies.get('agentgate_session','')
    owner=accounts.identify(store,supplied) if supplied else None
    if not owner and cookie:
        owner=accounts.identify(store,cookie)
        if owner and request.method not in ('GET','HEAD','OPTIONS'):
            origin=request.headers.get('origin','')
            if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Cross-origin request rejected')
    if owner:return owner
    if not CLOUD and supplied and secrets.compare_digest(supplied,KEY):return 'demo-partner'
    raise HTTPException(401,'Sign in or provide a valid personal access token')

def agent(identity=Depends(authenticate)):
    try:store.allow(identity)
    except Rejected as e:raise HTTPException(e.code,e.message)
    return identity

class Negotiate(BaseModel):
    product_id:str=Field(max_length=50)
    offer_usd:str=Field(max_length=20)
    message:str=Field(default='',max_length=1000)
class Checkout(BaseModel):token:str=Field(min_length=20,max_length=200)
class BuyerGoal(BaseModel):
    goal:str=Field(min_length=3,max_length=1000)
    budget_usd:str=Field(pattern=r'^\d{1,6}(?:\.\d{1,2})?$')

@app.post('/api/agent/v1/shop')
async def shop(request:BuyerGoal,identity=Depends(agent)):
    budget=Decimal(request.budget_usd)
    if budget<=0 or budget>100000:raise HTTPException(400,'Enter a budget between $0.01 and $100,000.')
    # Explicit limits in the buyer's goal can only reduce the form budget.
    limits=re.findall(r'(?:under|below|up to|at most|budget(?: of)?|maximum(?: of)?)\s*\$?\s*(\d+(?:\.\d{1,2})?)',request.goal.lower())
    if limits:budget=min(budget,*(Decimal(v) for v in limits))
    try:intent=await providers.interpret(request.goal)
    except Exception:raise HTTPException(503,'Local AI is unavailable. Keep Ollama running, then try again. You can also use the manual offer form.')
    memory=store.memory(identity)
    product=intent.get('requested_product')
    if memory and re.search(r'\b(another|same|usual|preferred)\b',request.goal.lower()) and not re.search(r'\b(phone|laptop|camera|headphones|tablet)\b',request.goal.lower()):
        product=memory['product']
    if memory:budget=min(budget,Decimal(memory['budget'])/100)
    if not product:raise HTTPException(422,'Name a phone, laptop, camera, headphones or tablet in your shopping goal.')
    catalog=store.browse()
    matches=[p for p in catalog if (p['id']==product or p.get('category')==product) and p['available']>0]
    named=[p for p in matches if p['title'].lower() in request.goal.lower()]
    listing=min(named or matches,key=lambda p:p['price_cents'],default=None)
    if listing:product=listing['id']
    if not listing or listing['available']<1:raise HTTPException(409,'That item is unavailable. Try another item or wait for a reservation to expire.')
    amount=min(budget,Decimal(listing['price_cents'])/100)
    try:
        result=store.reserve(identity,product,str(amount))
        store.record(identity,'ai buyer','reserved')
        return {**result,'intent':intent,'item_title':listing['title'],'budget_cents':int(budget*100),'memory_used':bool(memory),'decision':{'pricing':'Seller policy satisfied','inventory':'Available stock reserved atomically','privacy':'Public catalog only','approval':'Human checkout required'},'steps':['AI interpreted your goal','Read the public catalog','Checked stock and your budget','Gateway checked seller pricing','Reserved the item; checkout needs your confirmation']}
    except Rejected as e:
        store.record(identity,'ai buyer','blocked')
        raise HTTPException(e.code,'Your budget does not meet this sellerâ€™s pricing policy. Increase it or choose another item.' if e.code==422 else e.message)

@app.post('/api/agent/v1/cancel')
def cancel(request:Checkout,identity=Depends(agent)):return store.cancel(identity,request.token)

@app.get('/')
def home():return FileResponse(ROOT/'index.html')
@app.get('/ui.css',include_in_schema=False)
def stylesheet():return FileResponse(ROOT/'ui.css',media_type='text/css')
@app.get('/ui.js',include_in_schema=False)
def javascript():return FileResponse(ROOT/'ui.js',media_type='text/javascript')
@app.get('/llms.txt',response_class=PlainTextResponse)
def llms():return 'AgentGate product research. Search Adafruit, Arduino and SparkFun public catalogs. Source prices and stock are captured snapshots. Compare currencies separately; unknown variants and final checkout totals remain unknown. Saved references and preferences belong to an authenticated user, or a shared local demo identity. No purchase is performed.'
@app.get('/api/agent/v1/browse')
def browse(identity=Depends(authenticate)):return {'simulation':not MARKETPLACE,'products':store.browse(),'external_products':store.imports(identity)}
@app.post('/api/agent/v1/negotiate')
async def negotiate(request:Negotiate,identity=Depends(agent)):
    try:
        # LLM is advisory only. An outage cannot bypass deterministic policy.
        try: intent=await providers.interpret(request.message)
        except Exception:intent={'mode':'AI unavailable; deterministic policy enforced'}
        result=store.reserve(identity,request.product_id,request.offer_usd)
        store.record(identity,'negotiate','accepted');return {**result,'intent':intent}
    except Rejected as e:
        store.record(identity,'negotiate','blocked');raise HTTPException(e.code,e.message)
@app.post('/api/agent/v1/checkout')
def checkout(request:Checkout,identity=Depends(agent)):
    try:
        result=store.checkout(identity,request.token);store.record(identity,'checkout','unpaid order');return result
    except Rejected as e:
        store.record(identity,'checkout','blocked');raise HTTPException(e.code,e.message)
@app.get('/api/admin/status')
def status(identity=Depends(authenticate)):return {'simulation':True,'telemetry':store.stats(),'providers':providers.status(),'identity':'Shared local demo credential, not proof of Meta identity'}
@app.post('/api/admin/reset')
def reset(identity=Depends(agent)):
    if MARKETPLACE:raise HTTPException(403,'Reset is disabled for seller inventory')
    return store.reset_demo()
@app.post('/api/admin/provider/{provider}')
async def provider(provider:str,identity=Depends(agent)):
    try:return await providers.run(provider,store.browse(),store.stats())
    except Exception:raise HTTPException(502,'Provider failed; inspect credentials, permissions and provider console')

class MemoryInput(BaseModel):
    product:str=Field(pattern=r'^(phone|laptop|camera|headphones|tablet)$')
    budget_usd:str=Field(pattern=r'^\d{1,6}(?:\.\d{1,2})?$')

@app.get('/api/agent/v1/memory')
def memory_read(identity=Depends(authenticate)):
    return {'memory':store.memory(identity),'scope':'Shared local demo identity; structured preferences, not semantic vector search'}

@app.post('/api/agent/v1/memory')
def memory_save(request:MemoryInput,identity=Depends(agent)):
    amount=Decimal(request.budget_usd)
    if amount<=0 or amount>100000:raise HTTPException(400,'Budget must be between $0.01 and $100,000.')
    return {'memory':store.save_memory(identity,request.product,int(amount*100))}

@app.delete('/api/agent/v1/memory')
def memory_delete(identity=Depends(agent)):
    return store.forget(identity)

SELLER_KEY=os.getenv('SELLER_API_KEY','')
if MARKETPLACE and not CLOUD and not SELLER_KEY:
    SELLER_KEY=secrets.token_urlsafe(40)
    with (ROOT/'.env').open('a',encoding='utf-8') as config:config.write('\nSELLER_API_KEY='+SELLER_KEY+'\n')
def seller(x_seller_key:str=Header(default='')):
    if not SELLER_KEY or not secrets.compare_digest(x_seller_key,SELLER_KEY):raise HTTPException(401,'Seller credential required')
    return 'local-seller'

class ListingInput(BaseModel):
    title:str=Field(min_length=1,max_length=120)
    category:str=Field(pattern=r'^(phone|laptop|camera|headphones|tablet)$')
    price_usd:str=Field(max_length=20)
    minimum_usd:str=Field(max_length=20)
    stock:int=Field(ge=0,le=10000,strict=True)
    description:str=Field(default='',max_length=2000)
    photo_url:str=Field(default='',max_length=200)
class StockInput(BaseModel):stock:int=Field(ge=0,le=10000,strict=True)

@app.get('/seller',include_in_schema=False)
def seller_page():return FileResponse(ROOT/'seller.html')
@app.get('/seller.js',include_in_schema=False)
def seller_js():return FileResponse(ROOT/'seller.js',media_type='text/javascript')
@app.get('/api/seller/status')
def seller_status(identity=Depends(seller)):return store.seller_status()
@app.post('/api/seller/listings')
def create_listing(request:ListingInput,identity=Depends(seller)):
    if request.photo_url and not re.fullmatch(r'/photos/[a-f0-9]{32}\.(png|jpg|webp)',request.photo_url):raise HTTPException(400,'Upload a product photo first')
    try:return store.create_listing(request.title,request.category,request.price_usd,request.minimum_usd,request.stock,request.description,request.photo_url)
    except Rejected as e:raise HTTPException(e.code,e.message)
@app.patch('/api/seller/listings/{product}/stock')
def update_stock(product:str,request:StockInput,identity=Depends(seller)):
    try:return store.set_stock(product,request.stock)
    except Rejected as e:raise HTTPException(e.code,e.message)

from fastapi import UploadFile, File
@app.post('/api/seller/photo')
async def upload_photo(file:UploadFile=File(...),identity=Depends(seller)):
    data=await file.read(5*1024*1024+1)
    if len(data)>5*1024*1024:raise HTTPException(400,'Photo must be under 5 MB')
    suffix='png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'jpg' if data.startswith(b'\xff\xd8\xff') else 'webp' if data[:4]==b'RIFF' and data[8:12]==b'WEBP' else None
    if not suffix:raise HTTPException(400,'Use PNG, JPEG or WebP')
    folder=ROOT/'photos';folder.mkdir(exist_ok=True)
    name=secrets.token_hex(16)+'.'+suffix;(folder/name).write_bytes(data)
    return {'photo_url':'/photos/'+name}
@app.get('/photos/{name}')
def photo(name:str):
    if not re.fullmatch(r'[a-f0-9]{32}\.(png|jpg|webp)',name) or not (ROOT/'photos'/name).exists():raise HTTPException(404)
    return FileResponse(ROOT/'photos'/name,headers={'X-Content-Type-Options':'nosniff'})

class ImportURL(BaseModel):url:str=Field(min_length=10,max_length=2000)
class ImportDraft(BaseModel):draft_id:str=Field(pattern=r'^[a-f0-9]{32}$')
@app.post('/api/seller/import/preview')
def import_preview(request:ImportURL,identity=Depends(seller)):
    from product_importer import extract
    try:return store.save_import(extract(request.url))
    except Exception as e:
        if isinstance(e,ValueError):raise HTTPException(422,str(e))
        raise HTTPException(502,'Could not reach this product page. Try another public URL or its official API.')
@app.post('/api/seller/import/save')
def import_save(request:ImportDraft,identity=Depends(seller)):
    try:return store.publish_import(request.draft_id,identity)
    except Rejected as e:raise HTTPException(e.code,e.message)
@app.get('/api/agent/v1/external-products')
def imported_products(identity=Depends(authenticate)):return {'products':store.imports(identity),'reservable':False}

@app.post('/api/agent/v1/import/preview')
def agent_import_preview(request:ImportURL,identity=Depends(agent)):
    from product_importer import extract
    try:return store.save_import(extract(request.url),identity)
    except ValueError as e:raise HTTPException(422,str(e))
    except Exception:raise HTTPException(502,'This page could not be extracted. Try its official feed or another public product URL.')
@app.post('/api/agent/v1/import/save')
def agent_import_save(request:ImportDraft,identity=Depends(agent)):
    try:return store.publish_import(request.draft_id,identity)
    except Rejected as e:raise HTTPException(e.code,e.message)

class WebSearchInput(BaseModel):
    query:str=Field(min_length=3,max_length=200)
    budget:str|None=Field(default=None,pattern=r'^\d{1,6}(\.\d{1,2})?$')
    currency:str=Field(default='USD',pattern=r'^[A-Za-z]{3}$')
@app.post('/api/agent/v1/search')
def web_product_search(request:WebSearchInput,identity=Depends(agent)):
    from web_search import search
    result=search(request.query.strip())
    result['preferences']=store.memory(identity)
    profile=store.profile(identity)
    result['profile']=profile
    for product in result['products']:
        draft=store.save_import(product,identity)
        product['draft_id']=draft['draft_id']
    budget=Decimal(request.budget) if request.budget is not None else None
    memory=result['preferences']
    if request.currency.upper()=='USD' and memory:
        ceiling=Decimal(memory['budget'])/100
        budget=min(budget,ceiling) if budget is not None else ceiling
    if profile.get('budget') and profile.get('currency')==request.currency.upper():
        ceiling=Decimal(profile['budget']);budget=min(budget,ceiling) if budget is not None else ceiling
    if budget is not None:
        from comparison import compare
        try:
            assessment=compare(result['products'],budget,request.currency,profile)
            result['products']=assessment['products']
            result['identity_checks']=assessment['identity_checks']
            result['budget_applied']={'amount':str(budget),'currency':request.currency.upper(),'saved_ceiling_applied':bool(memory and request.currency.upper()=='USD')}
        except ValueError as e:raise HTTPException(422,str(e))
    return result

@app.get('/research.js',include_in_schema=False)
def research_script():return FileResponse(ROOT/'research.js',media_type='text/javascript')

class ComparisonInput(BaseModel):
    budget:str=Field(pattern=r'^\d{1,6}(\.\d{1,2})?$')
    currency:str=Field(default='USD',pattern=r'^[A-Za-z]{3}$')
@app.post('/api/agent/v1/compare')
def compare_shortlist(request:ComparisonInput,identity=Depends(authenticate)):
    from comparison import compare
    budget=Decimal(request.budget);memory=store.memory(identity)
    if memory and request.currency.upper()=='USD':budget=min(budget,Decimal(memory['budget'])/100)
    profile=store.profile(identity)
    if profile.get('budget') and profile.get('currency')==request.currency.upper():budget=min(budget,Decimal(profile['budget']))
    try:
        result=compare(store.imports(identity),budget,request.currency,profile)
        result['memory_ceiling_applied']=bool(budget<Decimal(request.budget))
        return result
    except ValueError as e:raise HTTPException(422,str(e))

@app.exception_handler(Rejected)
async def rejected_handler(request:Request,error:Rejected):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':error.message},status_code=error.code)

class AccountInput(BaseModel):
    username:str=Field(pattern=r'^[a-zA-Z0-9_-]{3,32}$')
    password:str=Field(min_length=12,max_length=128)

@app.get('/api/account')
def account_status(request:Request):
    import accounts
    owner=accounts.identify(store,request.cookies.get('agentgate_session',''))
    username=None
    if owner:
        with store.lock:
            row=store.db.execute('SELECT username FROM accounts WHERE id=?',(owner,)).fetchone()
            username=row['username'] if row else None
    return {'signed_in':bool(owner),'username':username,'local_demo_available':not CLOUD}

def account_entry(data,request,response,register):
    import accounts
    origin=request.headers.get('origin','')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):raise HTTPException(403,'Cross-origin request rejected')
    accounts.throttle(store,'ip:'+(request.client.host if request.client else 'unknown'))
    accounts.throttle(store,'account:'+data.username.lower())
    owner=accounts.create(store,data.username,data.password) if register else accounts.login(store,data.username,data.password)
    token=accounts.issue(store,owner)
    response.set_cookie('agentgate_session',token,httponly=True,secure=CLOUD,samesite='strict',max_age=86400)
    return {'signed_in':True,'username':data.username.lower()}

@app.post('/api/account/register')
def register(data:AccountInput,request:Request,response:Response):return account_entry(data,request,response,True)
@app.post('/api/account/login')
def login(data:AccountInput,request:Request,response:Response):return account_entry(data,request,response,False)
@app.post('/api/account/logout')
def logout(request:Request,response:Response,identity=Depends(authenticate)):
    import accounts
    accounts.revoke(store,request.cookies.get('agentgate_session',''));response.delete_cookie('agentgate_session');return {'signed_out':True}
@app.post('/api/account/token')
def personal_token(identity=Depends(authenticate)):
    import accounts
    if identity=='demo-partner':raise HTTPException(403,'Sign in to create a personal token')
    return {'token':accounts.issue(store,identity,'api','MCP / API'),'expires_in_days':90,'message':'Shown once. Store privately. Never put it in a public URL.'}
@app.delete('/api/account/tokens')
def revoke_tokens(identity=Depends(authenticate)):
    with store.lock:store.db.execute("DELETE FROM access_tokens WHERE owner=? AND kind='api'",(identity,))
    return {'revoked':True}

class ProfileInput(BaseModel):
    brands:list[str]=Field(default_factory=list,max_length=10)
    intended_use:str=Field(default='',max_length=300)
    requirements:list[str]=Field(default_factory=list,max_length=15)
    condition:str=Field(default='any',pattern=r'^(any|new|used|refurbished)$')
    budget:str|None=Field(default=None,pattern=r'^\d{1,6}(\.\d{1,2})?$')
    currency:str=Field(default='USD',pattern=r'^[A-Z]{3}$')
@app.get('/api/agent/v1/profile')
def profile(identity=Depends(authenticate)):return {'profile':store.profile(identity)}
@app.post('/api/agent/v1/profile')
def save_profile(data:ProfileInput,identity=Depends(agent)):
    if any(len(x)>100 for x in data.brands+data.requirements):raise HTTPException(422,'Keep each preference under 100 characters')
    if data.budget is not None and Decimal(data.budget)<=0:raise HTTPException(422,'Budget must be positive')
    return {'profile':store.save_profile(identity,data.model_dump())}
@app.delete('/api/agent/v1/profile')
def forget_profile(identity=Depends(agent)):return {'profile':store.save_profile(identity,{})}
@app.delete('/api/agent/v1/references/{key}')
def remove_reference(key:str,identity=Depends(agent)):return store.remove_reference(key,identity)
@app.post('/api/agent/v1/references/{key}/restore')
def restore_reference(key:str,identity=Depends(agent)):return store.restore_reference(key,identity)
@app.post('/api/agent/v1/references/{key}/refresh')
def refresh_reference(key:str,identity=Depends(agent)):
    from product_importer import extract
    old=store.reference(key,identity)
    try:data=extract(old['source_url'])
    except Exception:raise HTTPException(502,'Could not refresh this source; the previous snapshot is preserved')
    for field in ('comparison_eligible','match_note','match_kind','provider','discovery_source'):
        if field in old:data[field]=old[field]
    return store.refresh_reference(key,identity,data)
@app.get('/api/agent/v1/report')
def export_report(identity=Depends(authenticate)):
    from datetime import datetime,timezone
    return {'title':'AgentGate evidence report','generated_at':datetime.now(timezone.utc).isoformat(),'profile':store.profile(identity),'references':store.imports(identity),'limitations':['Captured page evidence; verify current stock and total at checkout','No inferred currency conversion','Exact model identity may be unknown']}

if CLOUD:
    blocked=('/seller','/api/seller','/api/admin','/photos','/api/agent/v1/shop','/api/agent/v1/negotiate','/api/agent/v1/checkout','/api/agent/v1/cancel')
    app.router.routes=[r for r in app.router.routes if not any(getattr(r,'path','').startswith(prefix) for prefix in blocked)]
