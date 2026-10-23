"""Official MCP HTTP client. Server credentials are never included in responses."""
import json, os, urllib.request
from pathlib import Path

def credential():
    path=os.environ.get('MCD_TOKEN_FILE')
    if path:return Path(path).read_text(encoding='utf-8').strip()
    if os.environ.get('MCD_TOKEN'):return os.environ['MCD_TOKEN']
    raise FileNotFoundError('Set MCD_TOKEN_FILE or MCD_TOKEN on the server')

class Client:
    def __init__(self):
        token=credential()
        if not token:raise ValueError('Missing credential')
        self.headers={'Authorization':'Bearer '+token,'Accept':'application/json, text/event-stream','Content-Type':'application/json'};self.id=0
    def send(self,method,params=None,notification=False):
        body={'jsonrpc':'2.0','method':method}
        if not notification:self.id+=1;body['id']=self.id
        if params is not None:body['params']=params
        req=urllib.request.Request('https://mcp.mcd.cn',data=json.dumps(body).encode(),headers=self.headers)
        with urllib.request.urlopen(req,timeout=35) as response:
            if response.headers.get('Mcp-Session-Id'):self.headers['Mcp-Session-Id']=response.headers['Mcp-Session-Id']
            if notification:return None
            if 'text/event-stream' in response.headers.get('Content-Type',''):
                for line in response:
                    if line.startswith(b'data:'):
                        result=json.loads(line[5:])
                        if result.get('id')==body['id']:return result
                raise ValueError('No matching MCP response')
            return json.load(response)
    def initialize(self):
        r=self.send('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'pinghaomai-read-only','version':'0.2.0'}})
        if 'error' in r:raise ValueError('MCP initialization failed')
        self.headers['MCP-Protocol-Version']=r['result']['protocolVersion'];self.send('notifications/initialized',notification=True)
