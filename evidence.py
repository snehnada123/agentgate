"""Conservative identity and offer evidence, derived only from source fields."""
import re
from datetime import datetime,timezone

def normalize(value):return re.sub(r'[^a-z0-9]','',str(value or '').lower())
def identity(p):
    # Cross-store SKU values are not assumed to identify the same manufacturer variant.
    brand=normalize(p.get('brand'))
    for field in ('gtin14','gtin13','gtin12','gtin8','gtin'):
        value=re.sub(r'\D','',str(p.get(field,'')))
        if len(value) in (8,12,13,14):return ('gtin',value.zfill(14))
    if brand and p.get('mpn'):return ('mpn',brand,normalize(p['mpn']))
    return None

def variant(p):
    title=p.get('title','').lower()
    sizes=tuple(sorted(re.findall(r'\b(\d+)\s*(gb|tb|mb)\b',title)))
    explicit=p.get('model') or p.get('variant')
    rev=re.findall(r'\b(?:rev(?:ision)?\s*|r)([2345])\b',title)
    condition=p.get('condition') or 'unknown'
    return {'capacities':sizes,'revision':rev,'model':explicit,'condition':condition}

def match_pair(a,b):
    ia,ib=identity(a),identity(b);va,vb=variant(a),variant(b)
    for field in ('capacities','revision','model'):
        if va[field] and vb[field] and va[field]!=vb[field]:return {'status':'variant_mismatch','reason':'Source model, revision or capacity differs.'}
    if va['condition']!='unknown' and vb['condition']!='unknown' and va['condition']!=vb['condition']:return {'status':'condition_mismatch','reason':'Listed product conditions differ.'}
    if ia and ib:
        return {'status':'identifier_match' if ia==ib else 'identifier_mismatch','reason':'Same source-published manufacturer identifier; verify bundle contents.' if ia==ib else 'Source-published manufacturer identifiers differ.'}
    return {'status':'unverified','reason':'No shared manufacturer identifier; title similarity does not prove the same variant.'}

def preference_checks(p,profile):
    evidence=(p.get('title','')+' '+p.get('description','')).lower();checks=[]
    brands=profile.get('brands',[])
    if brands:checks.append({'requirement':'Preferred brand','status':'supported' if any(b.lower() in str(p.get('brand','')).lower() for b in brands) else 'unknown','detail':'Checked source brand field; no brand is inferred from retailer name.'})
    for term in profile.get('requirements',[]):checks.append({'requirement':term,'status':'mentioned' if term.lower() in evidence else 'unknown','detail':'Text mention only; verify the specification at the source.'})
    wanted=profile.get('condition','any')
    if wanted!='any':checks.append({'requirement':wanted+' condition','status':'supported' if p.get('condition')==wanted else 'unknown' if not p.get('condition') else 'mismatch','detail':'Based on source condition metadata.'})
    if profile.get('intended_use'):checks.append({'requirement':profile['intended_use'],'status':'needs_review','detail':'Intended use is remembered; suitability has not been verified.'})
    return checks
