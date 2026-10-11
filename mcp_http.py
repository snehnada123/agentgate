"""Authenticated HTTP transport for the existing AgentGate MCP tools."""
import os,secrets
from mcp.server.transport_security import TransportSecuritySettings
from mcp_server import mcp
from starlette.responses import JSONResponse

TOKEN=os.getenv('AGENTGATE_REMOTE_TOKEN','')
if len(TOKEN)<32:raise RuntimeError('Set a strong AGENTGATE_REMOTE_TOKEN in .env before starting HTTP MCP')
mcp.settings.stateless_http=True
mcp.settings.json_response=True
mcp.settings.transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,allowed_hosts=['127.0.0.1:*','localhost:*','soon-implications-site-employ.trycloudflare.com','soon-implications-site-employ.trycloudflare.com:*'],allowed_origins=['http://127.0.0.1:*','http://localhost:*','https://*.trycloudflare.com'])
inner=mcp.streamable_http_app()
class ProtectedMCP:
    async def __call__(self,scope,receive,send):
        if scope['type']=='http':
            headers=dict(scope.get('headers',[]))
            supplied=headers.get(b'x-agentgate-token',b'').decode('utf-8',errors='replace')
            path_auth=secrets.compare_digest(scope.get('path',''),'/connector/'+TOKEN+'/mcp')
            if not (secrets.compare_digest(supplied,TOKEN) or path_auth):
                await JSONResponse({'error':'AgentGate connector credential required'},status_code=401)(scope,receive,send)
                return
        if scope['type']=='http' and scope.get('path','').startswith('/connector/'):
            scope={**scope,'path':'/mcp','raw_path':b'/mcp'}
        await inner(scope,receive,send)
app=ProtectedMCP()
