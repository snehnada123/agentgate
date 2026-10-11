"""Explainable snapshot comparison; no guessed prices or exchange rates."""
from decimal import Decimal,InvalidOperation

def compare(products,budget,currency='USD',profile=None):
    from evidence import match_pair,preference_checks
    ceiling=Decimal(str(budget))
    if not ceiling.is_finite() or ceiling<=0:raise ValueError('Enter a positive finite budget.')
    currency=currency.upper();rows=[]
    for p in products:
        row={**p,'warnings':[],'budget_status':'unknown','within_budget':None}
        try:
            amount=Decimal(str(p.get('price')))
            if not amount.is_finite() or amount<0:raise InvalidOperation
        except (InvalidOperation,ValueError,TypeError):amount=None
        unit=str(p.get('currency') or '').upper()
        if amount is None:row['warnings'].append('Price missing or invalid; cannot compare.')
        elif not unit:row['warnings'].append('Currency missing; cannot compare.')
        elif unit!=currency:
            row['budget_status']='different_currency';row['warnings'].append('Different currency; no exchange rate has been applied.')
        else:
            row['within_budget']=amount<=ceiling;row['budget_status']='within_budget' if amount<=ceiling else 'over_budget'
        if p.get('comparison_eligible') is False:row['warnings'].append(p.get('match_note','Related product; excluded from lowest matching-product price.'))
        row['warnings'].append('Availability is not verified.')
        row['warnings'].append('Shipping, taxes and final checkout price are not included.')
        if not p.get('observed_at'):row['warnings'].append('Capture time unavailable; refresh the product page before deciding.')
        if 'fictional' in p.get('availability','').lower():row['warnings'].append('Practice data; not a real purchasable recommendation.')
        row['reason']=('Listed price fits your budget; verify the final total at the source.' if row['budget_status']=='within_budget' else 'Listed price exceeds your budget.' if row['budget_status']=='over_budget' else 'Insufficient compatible price evidence to judge your budget.')
        row['real_candidate']='fictional' not in p.get('availability','').lower()
        row['preference_checks']=preference_checks(p,profile or {})
        row['total_cost_status']=p.get('total_cost_status','unknown; shipping and taxes not verified')
        if p.get('price_kind') in ('from','multiple_offers'):
            row['within_budget']=None;row['budget_status']='variant_price_unknown'
            row['reason']='Source price is a floor or one of several offers; the selected variant total is unknown.'
            row['warnings'].append(row['reason'])
        if p.get('availability_code') in ('OutOfStock','SoldOut','Discontinued'):
            row['comparison_eligible']=False;row['warnings'].append('Source reports unavailable; excluded from lowest eligible price.')
        rows.append(row)
    eligible=[p for p in rows if p['within_budget'] is True and p['real_candidate'] and p.get('comparison_eligible',True)]
    eligible.sort(key=lambda p:Decimal(p['price']))
    pairs=[{'left':a.get('id',a.get('title')),'right':b.get('id',b.get('title')),**match_pair(a,b)} for i,a in enumerate(rows) for b in rows[i+1:]]
    return {'budget':str(ceiling),'currency':currency,'products':rows,'identity_checks':pairs,'lowest_listed_price_id':eligible[0].get('id') if eligible else None,'summary':str(len(eligible))+' eligible references have a listed price within budget. This compares price only, not quality or suitability.','recommendation':'Verify product variant, stock and final total at the original retailer before buying.'}
