"""Multi-store HTTP + MCP contract tests; official MCP is replaced only in these tests."""
import concurrent.futures, datetime as dt, json, tempfile, threading, time, unittest
import urllib.request, urllib.error
from pathlib import Path
import server, market
from test_flows import FakeMCP

class MarketMCP(FakeMCP):
    def __init__(self):self.price=1490;self.missing=False;self.failed=False;self.calls=[];self.started=None;self.release=None;self.bad_store=None
    def call(self,name,args):
        self.calls.append((name,args.copy()))
        if name=='query-nearby-stores':return {'data':[dict(id=x,storeCode=x,storeName='Store '+x,name='Store '+x,address='Address '+x,distance=d,businessStatus=True,reservation=True,reservationTimeOptions=[]) for x,d in [('a',200),('b',800),('c',2100),('unknown',None)]]}
        if self.bad_store==args.get('storeCode'):raise server.LiveError('Store unavailable')
        if self.started and name=='calculate-price':self.started.set();self.release.wait(5)
        result=super().call(name,args)
        if name=='calculate-price' and args.get('storeCode')=='b':
            result['data']['price']+=100;result['data']['productList'][0]['subtotal']+=100
        return result

class MarketFlows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();server.DB=Path(cls.temp.name)/'market.sqlite3'
        cls.http=server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler);cls.base='http://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):cls.http.shutdown();cls.http.server_close();cls.temp.cleanup()
    def setUp(self):
        server.MCP=MarketMCP();server.STORES.clear()
        with server.connect() as db:
            market.db_init(db);db.execute('DELETE FROM invitations');db.execute('DELETE FROM market_quotes')
        self.req('/api/market/stores?city=test&keyword=center&radiusKm=3')
    def req(self,path,data=None,actor='market-host-identity-123456'):
        request=urllib.request.Request(self.base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json','X-Actor':actor})
        try:
            with urllib.request.urlopen(request,timeout=15) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def quote(self):
        return self.req('/api/market/quote',{'storeCodes':['a','b','c'],'pickup':(server.now()+dt.timedelta(days=1)).isoformat(timespec='minutes'),'mealId':'bundle'})
    def test_score_plan_uses_current_split_and_is_owner_scoped(self):
        code,q=self.quote();self.assertEqual(code,200)
        body={'quoteId':q['quoteId'],'storeCodes':['a','b'],'hostItems':['1-0'],'hostPay':100}
        code,low=self.req('/api/market/score-plan',body);self.assertEqual(code,200,low)
        code,high=self.req('/api/market/score-plan',dict(body,hostPay=1200));self.assertEqual(code,200,high)
        self.assertGreater(high['guestScore'],low['guestScore'])
        self.assertEqual(self.req('/api/market/score-plan',body,actor='other-market-identity-123456')[0],400)
        self.assertEqual(self.req('/api/market/score-plan',dict(body,hostItems=['1-0','2-0']))[0],400)
        self.assertEqual(self.req('/api/market/score-plan',dict(body,storeCodes=['unknown']))[0],400)
    def create(self):
        code,q=self.quote();self.assertEqual(code,200,q)
        code,r=self.req('/api/market/invitations',{'quoteId':q['quoteId'],'storeCodes':[o['store']['id'] for o in q['options']],'hostItems':['1-0'],'hostPay':1200,'name':'Host'});self.assertEqual(code,201,r);return r
    def rpc(self,name,args,actor='mcp-guest-identity-123456'):
        return self.req('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},actor)[1]['result']
    def test_radius_filters_unknown_and_outside(self):
        _,data=self.req('/api/market/stores?city=test&keyword=center&radiusKm=1')
        self.assertEqual([s['id'] for s in data['stores']],['a','b']);self.assertIn('地标',data['distanceBasis'])
    def test_multistore_concurrent_claim_exactly_one_winner(self):
        r=self.create();p='/api/market/invitations/'+r['id'];guests=['market-guest-'+str(i).zfill(16) for i in range(12)]
        def claim(i):
            sid=['a','b','c'][i%3];return self.req(p+'/claim',{'storeCode':sid,'expectedTotal':1590 if sid=='b' else 1490},guests[i])
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(claim,range(12)))
        winners=[i for i,(status,_) in enumerate(results) if status==200];self.assertEqual(len(winners),1,results)
        winner=winners[0];room=results[winner][1];self.assertEqual(room['status'],'matched');self.assertEqual(len(room['options']),3)
        for sid in ['a','b','c']:
            _,data=self.req('/api/market/invitations?storeCodes='+sid,actor='observer-identity-12345');self.assertEqual(data['invitations'],[])
        # Duplicate retry by winner returns same room; identities never escape.
        code,again=claim(winner);self.assertEqual(code,200);self.assertEqual(again['id'],r['id']);self.assertNotIn('owner',again)
        _,left=self.req(p+'/leave',{},guests[winner]);self.assertEqual(left['status'],'cancelled')
        self.assertEqual(claim((winner+1)%12)[0],409)
    def test_inflight_lock_visible_and_failure_releases(self):
        r=self.create();p='/api/market/invitations/'+r['id'];m=server.MCP;m.started=threading.Event();m.release=threading.Event()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future=pool.submit(self.req,p+'/claim',{'storeCode':'a','expectedTotal':1490},'first-guest-identity-1234')
            self.assertTrue(m.started.wait(2))
            self.assertEqual(self.req(p)[1]['status'],'checking')
            self.assertEqual(self.req(p+'/claim',{'storeCode':'b','expectedTotal':1590},'second-guest-identity-1234')[0],409)
            m.failed=True;m.release.set();self.assertEqual(future.result()[0],502)
        self.assertEqual(self.req(p)[1]['status'],'waiting')
        m.failed=False;m.started=None
        self.assertEqual(self.req(p+'/claim',{'storeCode':'b','expectedTotal':1590},'second-guest-identity-1234')[0],200)
    def test_price_change_releases_claim_and_resets_confirm(self):
        r=self.create();p='/api/market/invitations/'+r['id'];guest='price-guest-identity-12345'
        server.MCP.price=1690
        code,result=self.req(p+'/claim',{'storeCode':'a','expectedTotal':1490},guest)
        self.assertEqual(code,409);self.assertEqual(result['room']['status'],'waiting')
        self.assertEqual(self.req(p+'/claim',{'storeCode':'a','expectedTotal':1690},guest)[0],200)
        self.assertEqual(self.req(p+'/confirm',{'expectedTotal':1690})[0],200)
        server.MCP.price=1790
        code,result=self.req(p+'/confirm',{'expectedTotal':1690},guest)
        self.assertEqual(code,409);self.assertFalse(result['room']['hostConfirmed']);self.assertFalse(result['room']['guestConfirmed'])
        self.assertEqual(result['room']['status'],'matched')
    def test_mcp_discover_filter_and_claim_share_same_lock(self):
        r=self.create()
        result=self.rpc('find_nearby_pending',{'city':'test','keyword':'center','radiusKm':1,'taste':'Food 2','budgetCents':350})
        data=result['structuredContent'];self.assertEqual(len(data['invitations']),1)
        self.assertEqual([m['storeCode'] for m in data['invitations'][0]['matches']],['a']) # b costs 390
        result=self.rpc('claim_invitation',{'id':r['id'],'storeCode':'a','expectedTotal':1490,'name':'AI guest'})
        self.assertEqual(result['structuredContent']['status'],'matched')
        self.assertEqual(self.req('/api/market/invitations/'+r['id']+'/claim',{'storeCode':'b','expectedTotal':1590},'web-guest-identity-12345')[0],409)
        result=self.rpc('find_nearby_pending',{'city':'test','keyword':'center','radiusKm':3});self.assertEqual(result['structuredContent']['invitations'],[])
    def test_quote_single_use_and_failed_store_not_silently_published(self):
        server.MCP.bad_store='c';_,q=self.quote();self.assertEqual(len(q['failures']),1)
        body={'quoteId':q['quoteId'],'storeCodes':['a','b','c'],'hostItems':['1-0'],'hostPay':1200}
        self.assertEqual(self.req('/api/market/invitations',body)[0],400)
        body['storeCodes']=['a','b'];self.assertEqual(self.req('/api/market/invitations',body)[0],201)
        self.assertEqual(self.req('/api/market/invitations',body)[0],400)
    def test_expired_lease_and_expired_invitation(self):
        r=self.create();p='/api/market/invitations/'+r['id']
        with server.connect() as db:db.execute("UPDATE invitations SET status='checking',lease='stale',lease_until=? WHERE id=?",(time.time()-1,r['id']))
        self.assertEqual(self.req(p)[1]['status'],'waiting')
        with server.connect() as db:
            row,data=market.read(db,r['id']);data['expiresAt']=(server.now()-dt.timedelta(minutes=1)).isoformat();db.execute('UPDATE invitations SET data=? WHERE id=?',(json.dumps(data),r['id']))
        self.assertEqual(self.req(p+'/claim',{'storeCode':'a','expectedTotal':1490},'expired-guest-identity-12345')[0],400)
    def test_no_self_claim_and_no_payment_tool(self):
        r=self.create();p='/api/market/invitations/'+r['id']
        self.assertEqual(self.req(p+'/claim',{'storeCode':'a','expectedTotal':1490})[0],400)
        _,tools=self.req('/mcp',{'jsonrpc':'2.0','id':1,'method':'tools/list'})
        self.assertEqual({t['name'] for t in tools['result']['tools']},{'find_nearby_pending','get_invitation','claim_invitation'})
        self.assertEqual(self.req(p+'/pay',{})[0],400)
        result=self.rpc('claim_invitation',{'id':r['id'],'storeCode':'a','expectedTotal':1490},'')
        self.assertTrue(result['isError'])
    def test_separate_invitations_have_independent_locks(self):
        first=self.create();second=self.create();guest='independent-guest-identity-12345'
        self.assertEqual(self.req('/api/market/invitations/'+first['id']+'/claim',{'storeCode':'a','expectedTotal':1490},guest)[0],200)
        _,visible=self.req('/api/market/invitations?storeCodes=a,b,c',actor='independent-observer-12345')
        self.assertIn(second['id'],[r['id'] for r in visible['invitations']]);self.assertNotIn(first['id'],[r['id'] for r in visible['invitations']])
        self.assertEqual(self.req('/api/market/invitations/'+second['id']+'/claim',{'storeCode':'b','expectedTotal':1590},'independent-second-guest-12345')[0],200)
    def test_search_scope_isolated_from_another_search(self):
        _,area=self.req('/api/market/stores?city=test&keyword=center&radiusKm=1',actor='scope-observer-identity-12345')
        room=self.create();server.STORES['a']['distance']=9999
        _,data=self.req('/api/market/invitations?storeCodes=a&searchId='+area['searchId'],actor='scope-observer-identity-12345')
        self.assertEqual(data['invitations'][0]['matches'][0]['distance'],200)
        self.assertEqual(self.req('/api/market/invitations?storeCodes=c&searchId='+area['searchId'],actor='scope-observer-identity-12345')[0],400)

if __name__=='__main__':unittest.main()
