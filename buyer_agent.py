"""A tool-using buyer for the local fictional marketplace; checkout stays manual."""
import argparse
import asyncio
import json
import os
from decimal import Decimal
import httpx
from dotenv import load_dotenv
from pathlib import Path
from providers import interpret

async def shop(goal, budget, base='http://localhost:4180'):
    amount=Decimal(str(budget))
    if not amount.is_finite() or amount<=0 or amount.as_tuple().exponent < -2:raise ValueError('Budget must be positive with at most two decimals')
    intent=await interpret(goal)
    product=intent.get('requested_product')
    if not product:
        if intent['mode']!='deterministic demo':raise ValueError('AI did not select a valid product')
        product=next((p for p in ['headphones','laptop','camera','tablet','phone'] if p in goal.lower()),None)
        if not product:raise ValueError('Scripted demo needs a product name in the goal')
    headers={'X-Agent-Key':os.getenv('AGENT_API_KEY','local-demo-key')}
    async with httpx.AsyncClient(base_url=base,headers=headers,timeout=150,trust_env=False) as client:
        browse=await client.get('/api/agent/v1/browse');browse.raise_for_status()
        catalog=browse.json()['products']
        listing=next((p for p in catalog if p['id']==product and p['available']>0),None)
        if not listing:raise ValueError('Requested product unavailable')
        # Public list price is the upper bound; never exceed buyer budget.
        offer=min(amount,Decimal(listing['price_cents'])/100)
        reserve=await client.post('/api/agent/v1/negotiate',json={'product_id':product,'offer_usd':str(offer.quantize(Decimal('.01'))),'message':goal})
        return {'agent':'AgentGate reference buyer','mode':intent['mode'],'simulation':True,'steps':['interpret goal','browse public catalog','check available stock','cap offer to budget','request demo reservation'],'gateway_status':reserve.status_code,'reservation':reserve.json(),'checkout':'Requires separate manual demo confirmation; no real payment'}

if __name__=='__main__':
    load_dotenv(Path(__file__).parent/'.env')
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--goal',default='Find a demo phone');parser.add_argument('--budget',default='400');args=parser.parse_args()
    print(json.dumps(asyncio.run(shop(args.goal,args.budget)),indent=2))
