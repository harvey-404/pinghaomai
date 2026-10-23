"""HTTP lifecycle tests with a deterministic read-only MCP fixture."""
import concurrent.futures, copy, datetime as dt, json, tempfile, threading, unittest
import urllib.request, urllib.error
from pathlib import Path
import server
from mcp_gateway import Gateway, LiveError

class FakeMCP:
    price=1490
    missing=False
    failed=False
    def begin(self):pass
    def call(self,name,args):
        if self.failed:raise LiveError('upstream unavailable')
        if name=='query-meals':return {'data':{'meals':{'bundle':{'name':'Test bundle'}}}}
        if name=='query-meal-detail':return {'data':{'name':'Test bundle','rounds':[{'id':str(i),'name':'food','quantity':1,'choices':[{'code':str(i),'name':'Food '+str(i),'quantity':1,'maxQuantity':1}]} for i in (1,2)]}}
        if name=='calculate-price':return {'data':{'price':self.price,'productList':[] if self.missing else [{'productCode':'bundle','productName':'Test bundle','quantity':1,'subtotal':self.price}]}}
        raise AssertionError(name)

class RoomFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();server.DB=Path(cls.tmp.name)/'test.sqlite3'
        cls.fake=FakeMCP();server.MCP=cls.fake
        server.STORES['test']={'id':'test','name':'Test store','businessStatus':True,'reservation':True}
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.base='http://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.tmp.cleanup()
    def setUp(self):self.fake.price=1490;self.fake.missing=False;self.fake.failed=False
    def req(self,path,data=None,actor='host-identity-123456789'):
        request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Actor':actor})
        try:
            with urllib.request.urlopen(request) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def quote(self):
        pickup=(server.now()+dt.timedelta(days=1)).isoformat(timespec='minutes')
        return self.req('/api/quote',{'storeCode':'test','pickup':pickup,'mealId':'bundle'})
    def create(self,**changes):
        status,q=self.quote();self.assertEqual(status,200,q)
        data={'quoteId':q['quoteId'],'hostItems':['1-0'],'hostPay':1200,'name':'Host'};data.update(changes)
        return self.req('/api/rooms',data)
    def test_concurrent_join_confirm_and_no_order(self):
        status,r=self.create();self.assertEqual(status,201,r);p='/api/rooms/'+r['id']
        self.assertNotIn('hostToken',r)
        body={'expectedTotal':1490}
        self.assertEqual(self.req(p+'/join',body)[0],400)
        guests=['guest-identity-00000001','guest-identity-00000002']
        with concurrent.futures.ThreadPoolExecutor() as pool:results=list(pool.map(lambda a:self.req(p+'/join',body,a),guests))
        self.assertEqual(sorted(s for s,_ in results),[200,400])
        guest=guests[next(i for i,x in enumerate(results) if x[0]==200)]
        self.assertEqual(self.req(p+'/confirm',body)[1]['status'],'matched')
        self.assertEqual(self.req(p+'/confirm',body,guest)[1]['status'],'confirmed')
        for action in ['order','simulate-order','complete','pay']:
            self.assertEqual(self.req(p+'/'+action,body)[0],400)
        _,r=self.req(p+'/leave',{},guest)
        self.assertEqual(r['status'],'waiting');self.assertFalse(r['hostConfirmed']);self.assertFalse(r['guestConfirmed'])
    def test_price_change_resets_confirmations(self):
        _,r=self.create();p='/api/rooms/'+r['id'];guest='guest-identity-change-123'
        self.req(p+'/join',{'expectedTotal':1490},guest);self.req(p+'/confirm',{'expectedTotal':1490})
        self.fake.price=1590
        code,result=self.req(p+'/confirm',{'expectedTotal':1490},guest)
        self.assertEqual(code,409);self.assertFalse(result['room']['hostConfirmed']);self.assertEqual(result['room']['meal']['total'],1590)
        self.assertEqual(self.req(p+'/confirm',{'expectedTotal':1590},guest)[0],200)
    def test_quote_authorization_validation_and_single_use(self):
        _,q=self.quote();body={'quoteId':q['quoteId'],'hostItems':['1-0'],'hostPay':1200}
        self.assertEqual(self.req('/api/rooms',body,'another-identity-123456')[0],400)
        self.assertEqual(self.req('/api/rooms',dict(body,hostItems=['1-0','2-0']))[0],400)
        self.assertEqual(self.req('/api/rooms',dict(body,hostPay=0))[0],400)
        self.assertEqual(self.req('/api/rooms',body)[0],201)
        self.assertEqual(self.req('/api/rooms',body)[0],400)
    def test_no_fallback_when_upstream_fails_or_omits_meal(self):
        self.fake.missing=True;self.assertEqual(self.quote()[0],502)
        self.fake.missing=False;self.fake.failed=True;self.assertEqual(self.quote()[0],502)
    def test_gateway_rejects_writes_before_loading_credentials(self):
        for name in ['create-order','pay','submit-order']:
            with self.assertRaises(LiveError):Gateway().call(name,{})

if __name__=='__main__':unittest.main()
