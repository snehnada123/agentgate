import asyncio,json,os,socket,subprocess,sys,time,unittest
from pathlib import Path
import httpx
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parent
class MCPTests(unittest.TestCase):
    def test_stdio_protocol_and_policy(self):asyncio.run(self.exercise())
    async def exercise(self):
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        env={**os.environ,'AGENTGATE_DB':':memory:','AGENT_API_KEY':'mcp-test-key','MARKETPLACE_MODE':'0','AI_PROVIDER':'demo','SENTRY_DSN':'','GEMINI_API_KEY':'','AGENTGATE_URL':f'http://127.0.0.1:{port}'}
        server=subprocess.Popen([sys.executable,'-m','uvicorn','app:app','--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            async with httpx.AsyncClient(trust_env=False) as c:
                for attempt in range(100):
                    try:
                        if (await c.get(env['AGENTGATE_URL']+'/openapi.json')).status_code==200:break
                    except httpx.RequestError:pass
                    await asyncio.sleep(.1)
                else:self.fail('Isolated gateway did not start')
            params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_server.py')],env=env)
            async with stdio_client(params) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    names={t.name for t in (await session.list_tools()).tools}
                    self.assertEqual(len(names),12)
                    self.assertFalse(any(x in names for x in ('request_reservation','shop_with_memory','cancel_reservation','checkout')))
                    async def call(name,args={}):
                        r=await session.call_tool(name,args)
                        return r,json.loads(r.content[0].text) if not r.isError else None
                    r,d=await call('browse_catalog');self.assertFalse(r.isError);self.assertEqual(d['products'],[])
                    r,d=await call('save_preferences',{'brands':['Arduino'],'intended_use':'Learn circuits','requirements':['USB-C'],'budget':'100','currency':'USD','condition':'new'});self.assertFalse(r.isError)
                    r,d=await call('get_preferences');self.assertEqual(d['profile']['budget'],'100')
                    self.assertEqual(d['profile']['brands'],['Arduino'])
                    r,d=await call('export_evidence_report');self.assertFalse(r.isError);self.assertEqual(d['profile']['intended_use'],'Learn circuits')
                    r,_=await call('forget_preferences');self.assertFalse(r.isError)
                    r,d=await call('get_preferences');self.assertEqual(d['profile'],{})
                    resources=await session.list_resources();self.assertEqual(str(resources.resources[0].uri),'agentgate://rules')
                    self.assertIn('No MCP checkout tool',(await session.read_resource('agentgate://rules')).contents[0].text)
        finally:
            server.terminate()
            try:server.wait(timeout=10)
            except subprocess.TimeoutExpired:server.kill();server.wait()

if __name__=='__main__':unittest.main()
