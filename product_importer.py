"""Public HTTPS extraction. DNS is validated and pinned per request; no local network access."""
import socket,ipaddress,http.client,ssl,json,re
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit,urljoin
from urllib.robotparser import RobotFileParser
from decimal import Decimal,InvalidOperation
UA='AgentGateProductImporter'
MAX=2*1024*1024

def target(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('Use a public HTTPS product URL without credentials or custom ports')
    addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
    ips={a[4][0] for a in addresses}
    if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):raise ValueError('Private and local network addresses are not allowed')
    return p,addresses[0][4][0]

class PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self,host,ip):super().__init__(host,timeout=12,context=ssl.create_default_context());self.ip=ip
    def connect(self):
        sock=socket.create_connection((self.ip,443),self.timeout)
        self.sock=self._context.wrap_socket(sock,server_hostname=self.host)

def fetch(url):
    p,ip=target(url);c=PinnedHTTPS(p.hostname,ip)
    try:
        c.request('GET',p.path or '/' if not p.query else (p.path or '/')+'?'+p.query,headers={'User-Agent':UA,'Accept':'text/html,text/plain,application/json','Accept-Encoding':'identity'})
        r=c.getresponse();data=r.read(MAX+1)
        if len(data)>MAX:raise ValueError('Page exceeds the 2 MB import limit')
        return r.status,r.getheader('Location'),r.getheader('Content-Type',''),data.decode('utf-8',errors='replace')
    finally:c.close()

class ProductHTML(HTMLParser):
    def __init__(self):super().__init__();self.scripts=[];self.meta={};self.script=False;self.buffer='';self.heading=False;self.name='';self.price=False;self.price_text=''
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='script' and a.get('type','').lower()=='application/ld+json':self.script=True;self.buffer=''
        if tag=='meta':self.meta[a.get('property',a.get('name',a.get('itemprop','')))]=a.get('content','')
        if tag=='h1':self.heading=True
        if 'price_color' in a.get('class','').split():self.price=True
    def handle_endtag(self,tag):
        if tag=='script' and self.script:self.scripts.append(self.buffer);self.script=False
        if tag=='h1':self.heading=False
        if tag=='p':self.price=False
    def handle_data(self,data):
        if self.script:self.buffer+=data
        if self.heading:self.name+=data
        if self.price:self.price_text+=data

def nodes(value):
    if isinstance(value,dict):
        yield value
        for k,v in value.items():
            if k=='@graph':yield from nodes(v)
    elif isinstance(value,list):
        for item in value:yield from nodes(item)

def parse(html,url):
    p=ProductHTML();p.feed(html);product=None
    for script in p.scripts:
        try:
            for node in nodes(json.loads(script)):
                types=node.get('@type',[]);types=[types] if isinstance(types,str) else types
                if 'Product' in types:product=node;break
        except (ValueError,TypeError):continue
        if product:break
    d=product or {};offer=d.get('offers',{});offer=offer[0] if isinstance(offer,list) and offer else offer;offer=offer if isinstance(offer,dict) else {}
    title=d.get('name') or p.meta.get('og:title') or p.name.strip()
    if not isinstance(title,str) or not title.strip():raise ValueError('No product title found. This site may require an official API or browser rendering.')
    amount=offer.get('price',offer.get('lowPrice',p.meta.get('product:price:amount')));currency=offer.get('priceCurrency',p.meta.get('product:price:currency',''))
    if amount is None and p.price_text:
        match=re.search(r'([\d]+(?:\.[\d]{1,2})?)',p.price_text)
        amount=match.group(1) if match else None
        if chr(163) in p.price_text:currency='GBP'
    try:
        price=Decimal(str(amount));amount=str(price) if price.is_finite() and price>=0 else None
    except InvalidOperation:amount=None
    description=d.get('description') or p.meta.get('og:description') or p.meta.get('description','')
    image=d.get('image') or p.meta.get('og:image','');image=image[0] if isinstance(image,list) and image else image;image=image.get('url','') if isinstance(image,dict) else image
    photo=urljoin(url,image) if isinstance(image,str) and image else ''
    if photo and urlsplit(photo).scheme!='https':photo=''
    result={'title':title.strip()[:200],'description':str(description)[:1000],'price':amount,'currency':str(currency)[:8],'photo_url':photo,'source_url':url,'extraction':'JSON-LD' if product else 'Page metadata','availability':'Practice-site sample; fictional inventory' if urlsplit(url).hostname=='books.toscrape.com' else 'Unverified; visit original store','reservable':False}
    for field in ('brand','mpn','sku','gtin','gtin8','gtin12','gtin13','gtin14','model'):
        value=d.get(field)
        if isinstance(value,dict):value=value.get('name')
        if isinstance(value,(str,int)):result[field]=str(value)[:200]
    condition=str(offer.get('itemCondition',d.get('itemCondition',''))).rsplit('/',1)[-1]
    if condition in ('NewCondition','UsedCondition','RefurbishedCondition'):result['condition']=condition.replace('Condition','').lower()
    stock=str(offer.get('availability','')).rsplit('/',1)[-1]
    if stock in ('InStock','OutOfStock','SoldOut','PreOrder','BackOrder','LimitedAvailability','Discontinued'):
        result['availability_code']=stock
        if urlsplit(url).hostname!='books.toscrape.com':result['availability']='Source reports '+stock+' at capture; verify before purchase'
    result['price_kind']='from' if 'lowPrice' in offer else 'multiple_offers' if isinstance(d.get('offers'),list) and len(d['offers'])>1 else 'listed'
    result['shipping_evidence']=offer.get('shippingDetails') if isinstance(offer.get('shippingDetails'),(dict,list)) else None
    result['tax_included']=offer.get('priceSpecification',{}).get('valueAddedTaxIncluded') if isinstance(offer.get('priceSpecification'),dict) else None
    result['total_cost_status']='unknown; delivery destination and final checkout total not verified'
    return result

def extract(url):
    for _ in range(4):
        p,_=target(url);robots_url='https://'+p.netloc+'/robots.txt'
        status,_,_,text=fetch(robots_url)
        if status==200:
            robot=RobotFileParser();robot.parse(text.splitlines())
            if not robot.can_fetch(UA,url):raise ValueError('This site disallows this import in robots.txt. Use its official API or product feed.')
        elif status not in (404,410):raise ValueError('Could not verify site crawling policy. Use an official product feed.')
        status,location,kind,text=fetch(url)
        if status in (301,302,303,307,308) and location:url=urljoin(url,location);continue
        if status!=200:raise ValueError('Store declined or failed the request. No access controls were bypassed.')
        if 'html' not in kind:raise ValueError('Expected a public HTML product page')
        result=parse(text,url);result['observed_at']=datetime.now(timezone.utc).isoformat();return result
    raise ValueError('Too many redirects')
