"""Opt-in live MCP check: creates a TEST invitation and always closes it; never orders."""
import datetime as dt, json, os, secrets, urllib.request, urllib.parse

BASE=os.environ.get('PHM_CHECK_URL','http://127.0.0.1:8766/').rstrip('/')+'/'
host=secrets.token_urlsafe(24);guest=secrets.token_urlsafe(24);observer=secrets.token_urlsafe(24)

def req(path,body=None,actor=host):
    request=urllib.request.Request(BASE+path,data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type':'application/json','X-Actor':actor})
    with urllib.request.urlopen(request,timeout=180) as response:return json.load(response)

def rpc(name,args):
    response=req('mcp',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':name,'arguments':args}},guest)['result']
    if response.get('isError'):raise RuntimeError('MCP operation failed; inspect the local response privately')
    return response['structuredContent']

def main():
    room=None
    try:
        area=req('api/market/stores?'+urllib.parse.urlencode({'city':'西安市','keyword':'钟楼','radiusKm':3}))
        stores=[s for s in area['stores'] if s.get('reservation')][:3]
        if len(stores)<2:raise RuntimeError('Need at least two available reservation stores for this smoke check')
        date=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()+dt.timedelta(days=1)
        body={'storeCodes':[s['id'] for s in stores],'pickup':date.isoformat()+'T12:00','taste':'麦辣鸡腿堡'}
        result=req('api/market/recommendations',body)
        if not result['suggestions']:raise RuntimeError('No verified two-sided saving offer now; do not invent a fixture result')
        offer=result['suggestions'][0];plan=offer['plan'];assert plan['bothSave']
        room=req('api/market/invitations',{'quoteId':offer['quote']['quoteId'],'storeCodes':offer['storeCodes'],
                 'hostItems':plan['hostItems'],'hostPay':plan['hostPay'],'name':'测试发起人','note':'自动验证，结束后关闭，不下单付款'})
        found=rpc('find_nearby_pending',{'city':'西安市','keyword':'钟楼','radiusKm':3,'taste':'薯条','budgetCents':5000})
        assert room['id'] in [r['id'] for r in found['invitations']]
        selected=room['options'][-1]
        args={'id':room['id'],'storeCode':selected['store']['id'],'expectedTotal':selected['meal']['total'],'name':'测试搭子'}
        matched=rpc('claim_invitation',args);assert matched['status']=='matched'
        for option in room['options']:
            listing=req('api/market/invitations?'+urllib.parse.urlencode({'storeCodes':option['store']['id']}),actor=observer)
            assert room['id'] not in [r['id'] for r in listing['invitations']]
        for actor in (host,guest):
            confirmed=req('api/market/invitations/'+room['id']+'/confirm',args,actor)
        assert confirmed['status']=='confirmed'
        summary={'status':'passed','verifiedStores':len(room['options']),'hostPayCents':plan['hostPay'],
                 'hostSavingCents':plan['hostSavingCents'],'guestSavingMinCents':plan['guestSavingMin'],
                 'mcpFound':True,'mcpClaimed':True,'allStoreListingsRemoved':True,'bothConfirmed':True,'ordersCreated':False}
    finally:
        if room:
            closed=req('api/market/invitations/'+room['id']+'/cancel',{})
            assert closed['status']=='cancelled'
    summary['testInvitationClosed']=True
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
