"""Keyless discovery from a retailer's permitted public search and product pages."""
import re
from html.parser import HTMLParser
from urllib.parse import urlencode,urlsplit,urljoin
from urllib.robotparser import RobotFileParser
from concurrent.futures import ThreadPoolExecutor
from product_importer import fetch,extract,UA,target

ORIGIN='https://www.adafruit.com'
HOSTS={'www.adafruit.com','store.arduino.cc','www.sparkfun.com'}

class RetailerHTML(HTMLParser):
    def __init__(self):
        super().__init__();self.results=[];self.active=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='li' and a.get('itemtype','').endswith('/Product'):self.active={}
        if self.active is None:return
        if tag=='a' and a.get('itemprop')=='name':
            self.active['title']=a.get('content') or a.get('data-name','')
            url=urljoin(ORIGIN,a.get('href',''))
            if urlsplit(url).hostname=='www.adafruit.com' and re.fullmatch(r'/product/\d+',urlsplit(url).path):self.active['source_url']=url
    def handle_endtag(self,tag):
        if tag=='li' and self.active is not None:
            if self.active.get('title') and self.active.get('source_url'):self.results.append(self.active)
            self.active=None

def read_search(url):
    for _ in range(4):
        parsed,_=target(url)
        if parsed.hostname not in HOSTS:raise ValueError('Unexpected retailer redirect.')
        status,_,_,rules=fetch('https://'+parsed.netloc+'/robots.txt')
        robot=RobotFileParser();robot.parse(rules.splitlines())
        if status!=200 or not robot.can_fetch(UA,url):raise ValueError('Retailer crawling policy does not permit this search.')
        status,location,kind,text=fetch(url)
        if status in (301,302,303,307,308) and location:url=urljoin(url,location);continue
        if status!=200 or 'html' not in kind:raise ValueError('Retailer search is temporarily unavailable.')
        return text
    raise ValueError('Too many retailer redirects.')

def search_terms(query):
    # Remove only explicit shopping filler/budget phrases; never invent a model name.
    query=re.sub(r'(?i)\b(?:under|below|up to|less than)\s*[$\u00a3\u20ac]?\s*\d+(?:\.\d+)?(?:\s*(?:usd|gbp|eur|dollars))?',' ',query)
    query=re.sub(r'(?i)^(?:please\s+)?(?:find|search for|show me|buy)\s+(?:me\s+)?(?:an?\s+)?','',query)
    return ' '.join(query.split())

def classify_match(title,terms):
    accessories={'cable','cooler','case','battery','adapter','heatsink','mount','enclosure','fan'}
    def words(text):return set(re.findall(r'[a-z0-9]+',re.sub(r'(\d+)\s+(gb|tb|mb)',r'\1\2',text.lower())))
    wanted=words(terms);found=words(title)
    if (found & accessories) and not (wanted & accessories):
        return {'match_kind':'related_accessory','comparison_eligible':False,'match_note':'Title indicates an accessory; excluded from the lowest matching-product price.'}
    if not wanted.issubset(found):
        return {'match_kind':'related_result','comparison_eligible':False,'match_note':'Title does not include every search term; verify the exact model or variant.'}
    return {'match_kind':'title_match','comparison_eligible':True,'match_note':'Search terms match the title. Verify variant and compatibility at the retailer.'}

def adafruit_search(query):
    terms=search_terms(query)
    url=ORIGIN+'/search?'+urlencode({'q':terms,'s':'b'})
    result={'query':query,'search_terms':terms,'products':[],'candidates':[],'search_url':url,'mode':'direct retailer search','coverage':'Adafruit electronics catalog; not the whole web','provider':'Adafruit public search','checkout':'Open original retailer; no orders or reservations are created.'}
    if len(terms)<2:
        result['status']='Include a product name, such as Raspberry Pi 5 or USB camera.';return result
    try:
        parser=RetailerHTML();parser.feed(read_search(url));seen=set();candidates=[]
        for item in parser.results:
            if item['source_url'] not in seen:seen.add(item['source_url']);candidates.append(item)
        tokens=set(re.findall(r'[a-z0-9]+',terms.lower()))
        def score(item):
            title=item['title'].lower();words=set(re.findall(r'[a-z0-9]+',title))
            return (len(tokens & words),terms.lower() in title,-len(title))
        candidates.sort(key=score,reverse=True)
        result['candidates']=candidates[:6]
        def read(item):
            try:
                product=extract(item['source_url']);product['discovery_source']=url;product['provider']='Adafruit';product.update(classify_match(product['title'],terms))
                return product
            except Exception:return None
        with ThreadPoolExecutor(max_workers=3) as pool:result['products']=[p for p in pool.map(read,candidates[:6]) if p]
        count=len(result['products']);result['status']=(str(count)+' product pages read from Adafruit. Prices are captured snapshots; check variant and final total at the source.' if count else 'No extractable matches in Adafruit. Try a different electronics query or preview a URL from another retailer.')
        result['failed_extractions']=len(candidates[:6])-count
    except Exception as e:
        result['status']=str(e) if isinstance(e,ValueError) else 'Retailer search could not be reached. Retry or preview a product URL.'
        result['mode']='source unavailable'
    return result

class MerchantHTML(HTMLParser):
    def __init__(self,origin):super().__init__();self.origin=origin;self.results=[];self.in_title=False;self.active=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='h2' and 'productitem--title' in a.get('class',''):self.in_title=True
        if tag=='a' and (self.in_title or 'product-item-link' in a.get('class','').split()):
            u=urlsplit(urljoin(self.origin,a.get('href','')))
            if u.hostname==urlsplit(self.origin).hostname:self.active={'source_url':u._replace(query='',fragment='').geturl(),'title':''}
    def handle_data(self,data):
        if self.active is not None:self.active['title']+=data
    def handle_endtag(self,tag):
        if tag=='h2':self.in_title=False
        if tag=='a' and self.active is not None:
            self.active['title']=' '.join(self.active['title'].split())
            if self.active['title']:self.results.append(self.active)
            self.active=None

def search(query):
    terms=search_terms(query)
    sources=[('Adafruit',ORIGIN+'/search?'+urlencode({'q':terms,'s':'b'})),('Arduino','https://store.arduino.cc/search?'+urlencode({'q':terms,'type':'product'})),('SparkFun','https://www.sparkfun.com/catalogsearch/result/?'+urlencode({'q':terms}))]
    def discover(source):
        name,url=source
        try:
            parser=RetailerHTML() if name=='Adafruit' else MerchantHTML('https://'+urlsplit(url).netloc)
            parser.feed(read_search(url));seen=set();items=[]
            for p in parser.results:
                if p['source_url'] not in seen:
                    seen.add(p['source_url']);items.append({**p,'provider':name,'discovery_source':url})
            tokens=set(re.findall(r'[a-z0-9]+',terms.lower()))
            items.sort(key=lambda p:(len(tokens & set(re.findall(r'[a-z0-9]+',p['title'].lower()))),-len(p['title'])),reverse=True)
            return {'name':name,'status':'ok' if items else 'no_matches','url':url,'candidates':items[:3]}
        except Exception:return {'name':name,'status':'unavailable','url':url,'candidates':[]}
    if len(terms)<2:return {'query':query,'products':[],'candidates':[],'sources':[],'status':'Enter a product name.','search_url':sources[0][1]}
    with ThreadPoolExecutor(max_workers=3) as pool:statuses=list(pool.map(discover,sources))
    candidates=[p for source in statuses for p in source['candidates']]
    def read(p):
        try:
            result=extract(p['source_url']);result.update({k:p[k] for k in ['provider','discovery_source']});result.update(classify_match(result['title'],terms));return result
        except Exception:return None
    with ThreadPoolExecutor(max_workers=4) as pool:products=[p for p in pool.map(read,candidates) if p]
    products.sort(key=lambda p:(not p.get('comparison_eligible'),p['provider'],p['title']))
    unavailable=all(source['status']=='unavailable' for source in statuses)
    return {'query':query,'search_terms':terms,'products':products,'candidates':candidates,'sources':[{k:v for k,v in source.items() if k!='candidates'} for source in statuses],'coverage':'Adafruit, Arduino and SparkFun public catalogs','mode':'source unavailable' if unavailable else 'multi-store search','search_url':sources[0][1],'status':'All three retailer searches are unavailable. Try a direct product URL or retry later.' if unavailable else str(len(products))+' product pages captured across '+str(len({p['provider'] for p in products}))+' stores. Review exact variants and final totals.','failed_extractions':len(candidates)-len(products)}
