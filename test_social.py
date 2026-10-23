"""Social contracts over HTTP, using deterministic MCP only in tests."""
import base64, concurrent.futures, datetime as dt, json, struct, unittest, zlib
import secrets, urllib.request
import server, market, social
import test_market

HOST='market-host-identity-123456';GUEST='social-guest-identity-123456';OTHER='social-other-identity-123456'

def png(metadata=False):
    def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+(chunk(b'tEXt',b'PrivateLocation\0not-for-public') if metadata else b'')+chunk(b'IDAT',zlib.compress(b'\x00\xff\x80\x00'))+chunk(b'IEND',b'')

class SocialFlows(unittest.TestCase):
    setUpClass=classmethod(test_market.MarketFlows.setUpClass.__func__)
    tearDownClass=classmethod(test_market.MarketFlows.tearDownClass.__func__)
    req=test_market.MarketFlows.req
    quote=test_market.MarketFlows.quote
    create=test_market.MarketFlows.create

    def setUp(self):
        server.MCP=test_market.MarketMCP();server.STORES.clear()
        with server.connect() as db:
            market.db_init(db)
            for table in ('social_photos','social_reinvites','social_completions','social_profiles','invitations','market_quotes'):db.execute('DELETE FROM '+table)
        self.req('/api/market/stores?city=test&keyword=center&radiusKm=3')

    def post(self,id,action,body=None,actor=HOST):return self.req('/api/market/social/invitations/'+id+'/'+action,{} if body is None else body,actor)
    def confirmed(self):
        r=self.create();id=r['id'];total=r['options'][0]['meal']['total']
        for path,body,actor in [('claim',{'storeCode':'a','expectedTotal':total,'name':'Guest'},GUEST),('confirm',{'expectedTotal':total},HOST),('confirm',{'expectedTotal':total},GUEST)]:
            code,r=self.req('/api/market/invitations/'+id+'/'+path,body,actor);self.assertEqual(code,200,r)
        self.assertEqual(r['status'],'confirmed');return r
    def completed(self):
        r=self.confirmed()
        for a in (HOST,GUEST):code,r=self.post(r['id'],'complete',actor=a);self.assertEqual(code,200,r)
        self.assertEqual(r['status'],'completed');return r
    def upload(self,r,actor=HOST):
        return self.post(r['id'],'photo/upload',{'image':'data:image/png;base64,'+base64.b64encode(png(True)).decode(),'caption':'Our meal','agreePublic':True},actor)
    def board(self):return self.req('/api/market/social/leaderboard')[1]['entries']
    def gallery(self):return self.req('/api/market/social/gallery')[1]['entries']
    def test_completion_requires_confirmed_and_participant(self):
        r=self.create();self.assertEqual(self.post(r['id'],'complete')[0],400)
        r=self.confirmed();self.assertEqual(self.post(r['id'],'complete',actor=OTHER)[0],400)
        code,data=self.post(r['id'],'complete',{'role':'guest'},HOST);self.assertEqual(code,200,data);self.assertTrue(data['hostCompleted']);self.assertFalse(data.get('guestCompleted',False))
    def test_one_side_not_counted_and_final_retry_idempotent(self):
        r=self.confirmed();_,first=self.post(r['id'],'complete');self.assertEqual(first['status'],'confirmed')
        self.assertFalse(first.get('guestCompleted',False));self.assertEqual(first['social']['hostStats']['completedCount'],0)
        _,final=self.post(r['id'],'complete',actor=GUEST);self.assertEqual(final['social']['hostStats']['completedCount'],1)
        _,again=self.post(r['id'],'complete',actor=GUEST);self.assertEqual(again['social']['guestStats']['completedCount'],1)
    def test_completion_concurrent_only_one_record(self):
        r=self.confirmed()
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda a:self.post(r['id'],'complete',actor=a),[HOST,GUEST]*6))
        self.assertTrue(all(code==200 for code,_ in results),results)
        with server.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM social_completions').fetchone()[0],1)
    def test_partial_completion_freezes_cancellation_and_old_confirmation(self):
        r=self.confirmed();self.post(r['id'],'complete')
        for action,actor in [('cancel',HOST),('leave',GUEST),('confirm',GUEST)]:self.assertEqual(self.req('/api/market/invitations/'+r['id']+'/'+action,{'expectedTotal':r['options'][0]['meal']['total']},actor)[0],400)
    def test_completion_after_pickup_and_completed_not_in_pending(self):
        r=self.confirmed()
        with server.connect() as db:
            row,data=market.read(db,r['id']);data['expiresAt']=(server.now()-dt.timedelta(hours=1)).isoformat();db.execute('UPDATE invitations SET data=? WHERE id=?',(json.dumps(data),r['id']))
        self.post(r['id'],'complete');self.assertEqual(self.post(r['id'],'complete',actor=GUEST)[1]['status'],'completed')
        self.assertEqual(self.req('/api/market/invitations?storeCodes=a',actor=OTHER)[1]['invitations'],[])
    def test_ranking_opt_in_counts_and_same_pair_daily_cap(self):
        self.completed();self.completed();self.assertEqual(self.board(),[])
        code,data=self.req('/api/market/social/profile',{'name':'Public host','rankOptIn':True});self.assertEqual(code,200,data)
        self.assertEqual(data['me']['completedCount'],2);self.assertEqual(data['me']['rankedCount'],1)
        board=self.board();self.assertEqual(board[0]['completedCount'],1);self.assertNotIn(HOST,json.dumps(board))
        self.req('/api/market/social/profile',{'name':'Public host','rankOptIn':False});self.assertEqual(self.board(),[])
    def test_photo_only_after_completion_and_explicit_upload_consent(self):
        r=self.confirmed();self.assertEqual(self.upload(r)[0],400)
        r=self.completed();self.assertEqual(self.upload(r,OTHER)[0],400)
        self.assertEqual(self.post(r['id'],'photo/upload',{'image':'data:image/png;base64,'+base64.b64encode(png()).decode(),'agreePublic':False})[0],400)
    def test_photo_private_until_both_agree_and_revoke_blocks_bytes(self):
        r=self.completed();code,r=self.upload(r);self.assertEqual(code,200,r)
        ph=r['social']['photo'];self.assertFalse(ph['public']);self.assertEqual(self.gallery(),[])
        path='/api/market/social/photos/'+r['id']+'?v='+ph['version']
        self.assertEqual(self.req(path,actor=OTHER)[0],400)
        self.assertEqual(self.post(r['id'],'photo/agree',{'version':ph['version'],'role':'guest'},HOST)[1]['social']['photo']['guestAgreed'],False)
        code,r=self.post(r['id'],'photo/agree',{'version':ph['version']},GUEST);self.assertEqual(code,200,r);self.assertTrue(r['social']['photo']['public']);self.assertEqual(len(self.gallery()),1)
        self.post(r['id'],'photo/revoke',{'version':ph['version']},HOST);self.assertEqual(self.gallery(),[]);self.assertEqual(self.req(path,actor=OTHER)[0],400)
    def test_photo_replacement_resets_consent_and_rejects_old_version(self):
        r=self.completed();_,r=self.upload(r);old=r['social']['photo']['version']
        self.post(r['id'],'photo/agree',{'version':old},GUEST);self.assertEqual(len(self.gallery()),1)
        _,r=self.upload(r);self.assertNotEqual(r['social']['photo']['version'],old);self.assertEqual(self.gallery(),[])
        self.assertEqual(self.post(r['id'],'photo/agree',{'version':old},GUEST)[0],409)
    def test_large_photo_http_bytes_private_public_and_metadata(self):
        r=self.completed()
        def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
        pixels=b''.join(b'\0'+secrets.token_bytes(128*3) for _ in range(128))
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',128,128,8,2,0,0,0))+chunk(b'tEXt',b'PrivateLocation\0hidden')+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
        self.assertGreater(len(raw),20000)
        code,r=self.post(r['id'],'photo/upload',{'image':'data:image/png;base64,'+base64.b64encode(raw).decode(),'agreePublic':True});self.assertEqual(code,200,r)
        ph=r['social']['photo'];url=self.base+'/api/market/social/photos/'+r['id']+'?v='+ph['version']
        with urllib.request.urlopen(urllib.request.Request(url,headers={'X-Actor':GUEST})) as response:
            self.assertEqual(response.headers['Content-Type'],'image/png');self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff');self.assertEqual(response.headers['Cache-Control'],'no-store');self.assertNotIn(b'PrivateLocation',response.read())
        self.post(r['id'],'photo/agree',{'version':ph['version']},GUEST)
        with urllib.request.urlopen(url) as response:self.assertTrue(response.read().startswith(b'\x89PNG'))
    def test_png_metadata_removed_and_invalid_payload_rejected(self):
        cleaned=social.png_bytes('data:image/png;base64,'+base64.b64encode(png(True)).decode());self.assertNotIn(b'PrivateLocation',cleaned)
        for raw in (b'<svg/>',png()+b'trailing',png()[:-4]):
            with self.assertRaises(ValueError):social.png_bytes('data:image/png;base64,'+base64.b64encode(raw).decode())
    def test_png_decompression_bomb_rejected(self):
        def chunk(k,d):return struct.pack('>I',len(d))+k+d+struct.pack('>I',zlib.crc32(k+d)&0xffffffff)
        raw=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0'*1000000))+chunk(b'IEND',b'')
        with self.assertRaises(ValueError):social.png_bytes('data:image/png;base64,'+base64.b64encode(raw).decode())
    def request_again(self,r):
        return self.post(r['id'],'reinvite',{'pickup':(server.now()+dt.timedelta(days=2)).isoformat(timespec='minutes'),'note':'Again?'})
    def test_again_requires_completed_and_recipient_must_accept(self):
        r=self.confirmed();self.assertEqual(self.request_again(r)[0],400)
        r=self.completed();_,p=self.request_again(r)
        self.assertEqual(self.req('/api/market/social/reinvites/'+p['id'],{'action':'accept'})[0],400)
        self.assertEqual(self.req('/api/market/social/reinvites/'+p['id'],{'action':'accept'},OTHER)[0],400)
        _,accepted=self.req('/api/market/social/reinvites/'+p['id'],{'action':'accept'},GUEST);self.assertEqual(accepted['status'],'accepted')
        self.assertNotIn(HOST,json.dumps(accepted));self.assertNotIn(GUEST,json.dumps(accepted))
    def test_again_pending_unique_under_concurrency(self):
        r=self.completed()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:responses=list(pool.map(lambda _:self.request_again(r),range(8)))
        self.assertTrue(all(code==200 for code,_ in responses));self.assertEqual(len({p['id'] for _,p in responses}),1)
    def test_again_rejects_invalid_dates_and_handles_decline(self):
        r=self.completed()
        for pickup in ('yesterday',(server.now()-dt.timedelta(days=1)).isoformat(),(server.now()+dt.timedelta(days=8)).isoformat()):self.assertEqual(self.post(r['id'],'reinvite',{'pickup':pickup})[0],400)
        _,p=self.request_again(r);self.req('/api/market/social/reinvites/'+p['id'],{'action':'decline'},GUEST)
        self.assertEqual(self.req('/api/market/social/reinvites/'+p['id'],{'action':'accept'},GUEST)[0],400)
    def test_accepted_again_fresh_quote_private_single_use(self):
        r=self.completed();_,p=self.request_again(r);self.req('/api/market/social/reinvites/'+p['id'],{'action':'accept'},GUEST)
        _,q=self.req('/api/market/quote',{'storeCodes':['a'],'pickup':p['pickup'],'mealId':'bundle'})
        body={'quoteId':q['quoteId'],'storeCodes':['a'],'hostItems':['1-0'],'hostPay':1200,'name':'Host again','reinviteId':p['id']}
        code,new=self.req('/api/market/invitations',body);self.assertEqual(code,201,new);self.assertTrue(new['privatePair'])
        self.assertEqual(self.req('/api/market/invitations/'+new['id'],actor=OTHER)[0],400)
        self.assertEqual(self.req('/api/market/invitations?storeCodes=a',actor=OTHER)[1]['invitations'],[])
        self.assertEqual(len(self.req('/api/market/invitations?storeCodes=a',actor=GUEST)[1]['invitations']),1)
        self.assertEqual(self.req('/api/market/invitations/'+new['id']+'/claim',{'storeCode':'a','expectedTotal':1490},OTHER)[0],400)
        self.assertEqual(self.req('/api/market/invitations/'+new['id']+'/claim',{'storeCode':'a','expectedTotal':1490},GUEST)[0],200)
        _,q2=self.req('/api/market/quote',{'storeCodes':['a'],'pickup':p['pickup'],'mealId':'bundle'})
        self.assertEqual(self.req('/api/market/invitations',dict(body,quoteId=q2['quoteId']))[0],400)

if __name__=='__main__':unittest.main()
