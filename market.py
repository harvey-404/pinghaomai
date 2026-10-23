"""Multi-store invitations. One database row is one globally claimable invitation."""
import copy, datetime as dt, json, re, secrets, time
from concurrent.futures import ThreadPoolExecutor

class Conflict(ValueError):
    def __init__(self,message,room=None):super().__init__(message);self.room=room

def db_init(db):
    db.execute('CREATE TABLE IF NOT EXISTS invitations (id TEXT PRIMARY KEY,status TEXT NOT NULL,owner TEXT NOT NULL,guest TEXT,lease TEXT,lease_until REAL,data TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS invitation_status ON invitations(status)')
    db.execute('CREATE TABLE IF NOT EXISTS market_quotes (id TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,data TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS market_searches (id TEXT PRIMARY KEY,owner TEXT NOT NULL,expires REAL NOT NULL,data TEXT NOT NULL)')

def read(db,id):
    row=db.execute('SELECT * FROM invitations WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('拼单不存在。')
    return row,json.loads(row[6])

def recover(db):
    if db.execute("SELECT 1 FROM invitations WHERE status='checking' AND lease_until<? LIMIT 1",(time.time(),)).fetchone():
        db.execute("UPDATE invitations SET status='waiting',lease=NULL,lease_until=NULL WHERE status='checking' AND lease_until<?",(time.time(),))

def output(core,row,r,actor):
    r=copy.deepcopy(r);r['status']=row[1];r['role']='host' if row[2]==actor else 'guest' if row[3]==actor else 'visitor'
    r['expired']=dt.datetime.fromisoformat(r['expiresAt'])<=core.now()
    # Identity secrets and claim leases are never returned.
    return r

def radius(value):
    try:n=float(value)
    except (ValueError,TypeError):raise ValueError('范围应为0.2至20公里。')
    if not 0.2<=n<=20:raise ValueError('范围应为0.2至20公里。')
    return n

def search(core,args,actor=''):
    city=core.short_text(args.get('city','西安市'),'城市',40)
    keyword=core.short_text(args.get('keyword',''),'地标',80)
    if not city or not keyword:raise ValueError('请填写城市和搜索地标。')
    km=radius(args.get('radiusKm',3));result=core.MCP.call('query-nearby-stores',{'beType':1,'searchType':2,'city':city,'keyword':keyword})
    stores=[]
    for value in result.get('data') or []:
        s=dict(value,id=value['storeCode'],name=value['storeName'])
        # Distances come from official keyword search, not the visitor's GPS.
        distance=s.get('distance');s['distanceKnown']=type(distance) in (int,float) and distance>=0
        if not s['distanceKnown'] or distance>km*1000:continue
        core.STORES[s['id']]=s;stores.append(s)
    stores.sort(key=lambda x:x['distance'])
    id=secrets.token_urlsafe(18)
    with core.connect() as db:
        db_init(db);db.execute('DELETE FROM market_searches WHERE expires<?',(time.time(),));db.execute('INSERT INTO market_searches VALUES (?,?,?,?)',(id,actor,time.time()+3600,json.dumps({s['id']:s['distance'] for s in stores})))
    return {'searchId':id,'stores':stores,'city':city,'keyword':keyword,'radiusKm':km,'distanceBasis':'官方返回的地标搜索距离，非步行路线或GPS距离','queriedAt':core.timestamp(),'traceId':result.get('traceId')}

def keys(foods):return [(f['id'],f['code'],f['name']) for f in foods]
def terms(m):return (m['total'],m.get('extras',[]),m.get('fees',[]))

def quote(core,body,actor):
    ids=body.get('storeCodes',[])
    if not isinstance(ids,list) or not 1<=len(ids)<=5 or any(not isinstance(x,str) for x in ids) or len(set(ids))!=len(ids):raise ValueError('请选择1至5家不同的门店。')
    if type(body.get('useCard',False))!=bool:raise ValueError('购卡试算选项不正确。')
    stores=[core.STORES.get(x) for x in ids]
    if not all(stores):raise ValueError('请重新查询范围内门店后选择。')
    pickup=body.get('pickup');meal_id=body.get('mealId');selections=body.get('selections')
    def one(s):
        try:
            core.MCP.begin();m=core.live_quote(s,pickup,meal_id,selections,body.get('useCard',False))
            return {'store':s,'meal':m}
        except (ValueError,core.LiveError) as e:return {'storeCode':s['id'],'name':s['name'],'error':str(e)}
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(one,stores))
    options=[];failures=[];expected=None
    for r in results:
        if 'error' in r:failures.append(r);continue
        if expected is None:expected=keys(r['meal']['foods'])
        if keys(r['meal']['foods'])!=expected:
            failures.append({'storeCode':r['store']['id'],'name':r['store']['name'],'error':'套餐默认组成不同，请在这些门店分别重新选择。'});continue
        options.append(r)
    if not options:raise core.LiveError('所选门店均无法提供同一组合：'+'；'.join(x['name']+'：'+x['error'] for x in failures))
    id=secrets.token_urlsafe(18);data={'options':options,'failures':failures,'pickup':pickup,'createdAt':core.timestamp()}
    with core.connect() as db:
        db_init(db);db.execute('DELETE FROM market_quotes WHERE expires<?',(time.time(),));db.execute('INSERT INTO market_quotes VALUES (?,?,?,?)',(id,actor,time.time()+600,json.dumps(data,ensure_ascii=False)))
    return dict(data,quoteId=id)

def publish(core,body,actor):
    qid=body.get('quoteId')
    with core.connect() as db:
        db_init(db);row=db.execute('SELECT owner,expires,data FROM market_quotes WHERE id=?',(qid,)).fetchone()
    if not row or row[0]!=actor or row[1]<time.time():raise ValueError('多店报价已过期或已发布，请重新查询。')
    q=json.loads(row[2]);selected=body.get('storeCodes');allids={x['store']['id'] for x in q['options']}
    if not isinstance(selected,list) or not selected or any(not isinstance(x,str) for x in selected) or len(set(selected))!=len(selected) or not set(selected)<=allids:raise ValueError('请明确选择已核价成功的发布门店。')
    options=[x for x in q['options'] if x['store']['id'] in selected]
    allocation=body.get('hostItems',[]);foodids={x['id'] for x in options[0]['meal']['foods']}
    if not isinstance(allocation,list) or any(not isinstance(x,str) for x in allocation) or not allocation or len(set(allocation))!=len(allocation) or not set(allocation)<foodids:raise ValueError('两个人都至少需要分到一份餐品。')
    name=core.short_text(body.get('name',''),'昵称',16,'麦麦搭子');note=core.short_text(body.get('note',''),'留言',100)
    fresh=[]
    for option in options:
        m=option['meal'];core.valid_pay(body.get('hostPay'),m['total'])
        current=core.live_quote(option['store'],q['pickup'],m['id'],m['selections'],m['useCard'],m['foods'])
        if terms(current)!=terms(m):raise Conflict('门店价格或卡费变化，请重新核价并确认各店金额。')
        fresh.append({'store':option['store'],'meal':current})
    pickup=(core.now()+dt.timedelta(minutes=15)).isoformat(timespec='minutes') if q['pickup']=='now' else q['pickup']
    r={'id':secrets.token_urlsafe(9),'options':fresh,'selectedStore':None,'hostItems':allocation,'hostPay':body['hostPay'],'hostName':name,'guestName':None,'hostConfirmed':False,'guestConfirmed':False,'note':note,'pickup':pickup,'requestPickup':q['pickup'],'expiresAt':pickup,'createdAt':core.timestamp()}
    with core.connect() as db:
        db_init(db);db.execute('BEGIN IMMEDIATE')
        consumed=db.execute('DELETE FROM market_quotes WHERE id=? AND owner=? AND expires>?',(qid,actor,time.time())).rowcount
        if consumed!=1:raise Conflict('同一报价已经发布，请勿重复提交。')
        db.execute('INSERT INTO invitations VALUES (?,?,?,?,?,?,?)',(r['id'],'waiting',actor,None,None,None,json.dumps(r,ensure_ascii=False)))
        rr,data=read(db,r['id']);return output(core,rr,data,actor)

def get(core,id,actor):
    with core.connect() as db:
        db_init(db);recover(db);row,r=read(db,id);return output(core,row,r,actor)

def listing(core,args,actor):
    store_codes=args.get('storeCodes',[])
    if isinstance(store_codes,str):store_codes=[x for x in store_codes.split(',') if x]
    if not isinstance(store_codes,list) or any(not isinstance(x,str) for x in store_codes):raise ValueError('门店筛选格式不正确。')
    taste=core.short_text(args.get('taste',''),'想吃的食物',80)
    budget=args.get('budgetCents')
    if budget not in (None,''):
        try:budget=int(budget)
        except (TypeError,ValueError):raise ValueError('预算格式不正确。')
        if not 0<budget<=100000:raise ValueError('预算超出范围。')
    words=[x for x in re.split(r'[,，、\s]+',taste) if x];pending=[];mine=[]
    with core.connect() as db:
        db_init(db);recover(db)
        scope=None
        if args.get('searchId'):
            search_row=db.execute('SELECT data FROM market_searches WHERE id=? AND owner=? AND expires>?',(args['searchId'],actor,time.time())).fetchone()
            if not search_row:raise ValueError('门店范围查询已过期，请重新搜索地标。')
            scope=json.loads(search_row[0])
            if not set(store_codes)<=set(scope):raise ValueError('门店筛选超出本次查询范围。')
        for row in db.execute('SELECT * FROM invitations ORDER BY rowid DESC'):
            r=output(core,row,json.loads(row[6]),actor)
            if r['role']!='visitor':mine.append(r)
            if r['status']!='waiting' or r['expired'] or r['role']=='host':continue
            candidates=[]
            for o in r['options']:
                sid=o['store']['id']
                if not store_codes or sid not in store_codes:continue
                remainder=[f['name'] for f in o['meal']['foods'] if f['id'] not in r['hostItems']];amount=o['meal']['total']-r['hostPay']
                if amount<=0 or (budget and amount>budget):continue
                matches=[w for w in words if any(w in food for food in remainder)]
                if words and not matches:continue
                distance=scope.get(sid) if scope is not None else core.STORES.get(sid,{}).get('distance')
                candidates.append({'storeCode':sid,'storeName':o['store']['name'],'distance':distance,'guestPay':amount,'foods':remainder,'matches':matches})
            if not candidates:continue
            candidates.sort(key=lambda c:(-len(c['matches']),c['distance'] if isinstance(c['distance'],(int,float)) else 10**9,c['guestPay']))
            best=candidates[0];r['matches']=candidates;r['recommendation']={'storeCode':best['storeCode'],'reasons':(['符合你想吃的：'+'、'.join(best['matches'])] if best['matches'] else [])+['搭子承担 ¥%.2f'%(best['guestPay']/100)],'basis':'按口味匹配、搜索距离、承担金额排序，不是成交概率预测'};pending.append(r)
    pending.sort(key=lambda r:(-len(r['matches'][0]['matches']),r['matches'][0]['distance'] if isinstance(r['matches'][0]['distance'],(int,float)) else 10**9,r['matches'][0]['guestPay']))
    return {'invitations':pending,'mine':mine,'queriedAt':core.timestamp(),'note':'领取前会再次调用官方MCP核价；待拼单来自拼好麦数据库。'}

def claim(core,id,body,actor):
    sid=body.get('storeCode');lease=secrets.token_urlsafe(18)
    name=core.short_text(body.get('name',''),'昵称',16,'新搭子')
    with core.connect() as db:
        db_init(db);db.execute('BEGIN IMMEDIATE');recover(db);row,r=read(db,id)
        if row[2]==actor:raise ValueError('不能领取自己发起的拼单。')
        if row[1]=='matched' and row[3]==actor:return output(core,row,r,actor)
        if row[1]!='waiting':raise Conflict('这单已被领取或正在核价，所有门店只共享一个名额。')
        if dt.datetime.fromisoformat(r['expiresAt'])<=core.now():raise ValueError('已超过取餐时间。')
        option=next((x for x in r['options'] if x['store']['id']==sid),None)
        if not option:raise ValueError('请选择这份拼单覆盖的门店。')
        db.execute("UPDATE invitations SET status='checking',lease=?,lease_until=? WHERE id=? AND status='waiting'",(lease,time.time()+180,id))
    try:
        m=option['meal'];fresh=core.live_quote(option['store'],r['requestPickup'],m['id'],m['selections'],m['useCard'],m['foods'])
        if dt.datetime.fromisoformat(r['expiresAt'])<=core.now():raise ValueError('核价期间已超过取餐时间，领取已释放。')
        changed=terms(fresh)!=terms(m) or body.get('expectedTotal')!=fresh['total'];option['meal']=fresh
        core.valid_pay(r['hostPay'],fresh['total'])
        with core.connect() as db:
            db_init(db);db.execute('BEGIN IMMEDIATE');row,current=read(db,id)
            if row[1]!='checking' or row[4]!=lease:raise Conflict('领取占位已失效，请重新查看。')
            if changed:
                db.execute("UPDATE invitations SET status='waiting',lease=NULL,lease_until=NULL,data=? WHERE id=?",(json.dumps(r,ensure_ascii=False),id))
                result=output(core,('','waiting',row[2],None,None,None),r,actor)
            else:
                r.update(selectedStore=sid,guestName=name,hostConfirmed=False,guestConfirmed=False)
                db.execute("UPDATE invitations SET status='matched',guest=?,lease=NULL,lease_until=NULL,data=? WHERE id=? AND lease=?",(actor,json.dumps(r,ensure_ascii=False),id,lease))
                rr,data=read(db,id);result=output(core,rr,data,actor)
        if changed:raise Conflict('价格变化，已释放占位。请确认新金额后重新领取。',result)
        return result
    except Exception:
        with core.connect() as db:
            db_init(db);db.execute("UPDATE invitations SET status='waiting',lease=NULL,lease_until=NULL WHERE id=? AND lease=? AND status='checking'",(id,lease))
        raise

def action(core,id,action,body,actor):
    if action=='claim':return claim(core,id,body,actor)
    fresh=None
    if action=='confirm':
        snapshot=get(core,id,actor)
        if snapshot['role']=='visitor' or snapshot['status'] not in ('matched','confirmed') or snapshot['expired']:raise ValueError('只有未过期、已领取的拼单可以确认。')
        option=next(x for x in snapshot['options'] if x['store']['id']==snapshot['selectedStore']);m=option['meal']
        fresh=core.live_quote(option['store'],snapshot['requestPickup'],m['id'],m['selections'],m['useCard'],m['foods'])
    with core.connect() as db:
        db_init(db);db.execute('BEGIN IMMEDIATE');recover(db);row,r=read(db,id);v=output(core,row,r,actor);role=v['role'];status=row[1]
        if role=='visitor':raise ValueError('只有拼单双方可以操作。')
        if action=='cancel':
            if role!='host' or status not in ('waiting','matched','confirmed'):raise Conflict('当前不能取消，正在领取时请稍后重试。')
            status='cancelled'
        elif action=='leave':
            if role!='guest' or status not in ('matched','confirmed'):raise ValueError('当前不能退出。')
            # A claimed invitation stays closed across all stores, even after withdrawal.
            status='cancelled';r['closedReason']='搭子退出，邀请已关闭；需要发起人重新发布。'
        elif action=='confirm':
            if status not in ('matched','confirmed') or v['expired']:raise ValueError('只有未过期、已领取的拼单可以确认。')
            option=next(x for x in r['options'] if x['store']['id']==r['selectedStore']);m=option['meal']
            option['meal']=fresh
            changed=terms(m)!=terms(fresh) or body.get('expectedTotal')!=fresh['total']
            core.valid_pay(r['hostPay'],fresh['total'])
            if changed:r.update(hostConfirmed=False,guestConfirmed=False);status='matched'
            else:r[role+'Confirmed']=True;status='confirmed' if r['hostConfirmed'] and r['guestConfirmed'] else 'matched'
        else:raise ValueError('当前版本没有下单或付款功能。')
        db.execute('UPDATE invitations SET status=?,data=? WHERE id=?',(status,json.dumps(r,ensure_ascii=False),id));rr,data=read(db,id);result=output(core,rr,data,actor)
    if action=='confirm' and changed:raise Conflict('价格变化，双方需要重新确认。',result)
    return result

def taste_choices(menus,pickup):
    """Officially documented favorites first; live availability always filters them."""
    hour=(dt.datetime.now(dt.timezone(dt.timedelta(hours=8))) if pickup=='now' else dt.datetime.fromisoformat(pickup)).hour
    priority=(['breakfast','drink','burger','snack','chicken'] if 5<=hour<11 else
              ['drink','snack','burger','chicken','breakfast'] if 14<=hour<17 else
              ['burger','chicken','snack','drink','breakfast'])
    definitions={
        'burger':('想吃汉堡','汉堡','汉堡|鸡腿堡|牛堡|鱼堡|板烧|巨无霸'),
        'chicken':('想吃炸鸡','炸鸡','炸鸡|鸡翅|鸡块|麦乐鸡|麦辣鸡'),
        'snack':('来点小食','小食','薯条|薯饼|小食|派'),
        'drink':('喝点东西','饮品','可乐|咖啡|拿铁|奶茶|饮料|美式|牛奶'),
        'breakfast':('吃个早餐','早餐','麦满分|早餐|粥|油条|煎蛋')}
    favorites=[
        ('mcspicy','麦辣鸡腿堡','麦辣鸡腿汉?堡','经典辣口主食',
         'https://www.mcdonalds.com.cn/news/20210409SCFB','官方2021年文章：汉堡销售冠军'),
        ('grilled','板烧鸡腿堡','板烧鸡腿堡','不辣主食选择',
         'https://www.mcdonalds.com.cn/news/20241008-Premium-Grilled-Chicken-Sandwich-FARMERBOB','官方2024年文章：不辣汉堡品类销量冠军'),
        ('fries','薯条','薯条','只想吃点小食',
         'https://www.mcdonalds.com.cn/news/20240722-FRIES-Great-Hit-2','官方2024年文章：最受欢迎的当家产品之一')]
    options=[]
    for key,label,pattern,reason,url,source in favorites:
        covered=sum(any(re.search(pattern,m.get('name','')) for m in menu.values()) for _,menu in menus)
        if covered:options.append({'id':key,'label':label,'value':label,'pattern':pattern,
            'description':f'{reason} · {covered}家门店菜单有相关餐品','sourceUrl':url,'sourceTitle':source})
    # Breakfast or missing products fall back to time-based intents, without claiming popularity.
    for key in priority:
        if len(options)>=3:break
        if key=='burger' and any(x['id'] in ('mcspicy','grilled') for x in options):continue
        if key=='snack' and any(x['id']=='fries' for x in options):continue
        label,value,pattern=definitions[key]
        covered=sum(any(re.search(pattern,m.get('name','')) for m in menu.values()) for _,menu in menus)
        if covered:options.append({'id':key,'label':label,'value':value,'pattern':pattern,'description':f'{covered}家所选门店菜单有相关餐品'})
    return options[:3]

def host_suggestions(core,body):
    ids=body.get('storeCodes',[]);pickup=body.get('pickup');want=core.short_text(body.get('taste',''),'想吃的食物',80)
    if not isinstance(ids,list) or not 1<=len(ids)<=5 or len(set(ids))!=len(ids):raise ValueError('请先选择1至5家门店。')
    menus=[];failures=[]
    for sid in ids:
        try:
            store=core.STORES.get(sid)
            if not store:raise ValueError('请重新搜索门店。')
            _,menu=core.get_menu(core.context(sid,pickup,store));menus.append((sid,menu))
        except (ValueError,core.LiveError) as e:failures.append({'storeCode':sid,'error':str(e)})
    candidates={}
    for sid,menu in menus:
        for code,m in menu.items():
            if not re.search('随心配|双人|分享|套餐|件套|任选|组合',m.get('name','')):continue
            candidate=candidates.setdefault(code,{'mealId':code,'name':m['name'],'image':m.get('image',''),'storeCodes':[],'referencePrices':[],'reasons':[]})
            candidate['storeCodes'].append(sid)
            try:candidate['referencePrices'].append(float(m.get('currentPrice',10000)))
            except (ValueError,TypeError):pass
    # Cheap, flexible choices and broader availability are explanatory heuristics only.
    for c in candidates.values():
        c['score']=len(c['storeCodes'])*20+(20 if '随心配' in c['name'] else 0)+(10 if want and want in c['name'] else 0)-min(c['referencePrices'] or [10000])/10
        c['reasons']=[f'所选 {len(c["storeCodes"])} 家门店菜单有售']
        if '随心配' in c['name']:c['reasons'].append('主食、小食或饮料可互补选择')
        c['reasons'].append('点击后按实际餐品与卡费逐店核价')
    rows=sorted(candidates.values(),key=lambda x:-x['score'])
    return {'suggestions':rows[:40],'tasteOptions':taste_choices(menus,pickup),'failures':failures,'basis':'按门店覆盖和菜单参考价筛选；没有历史成交样本，不承诺拼成率。','queriedAt':core.timestamp()}

def get_api(core,path,args,actor):
    if path=='/api/market/stores':return search(core,args,actor)
    if path=='/api/market/invitations':return listing(core,args,actor)
    if path.startswith('/api/market/invitations/'):return get(core,path.split('/')[-1],actor)
    raise ValueError('接口不存在。')

def post_api(core,path,body,actor):
    if not actor:raise ValueError('请重新打开页面生成本机身份。')
    if path=='/api/market/location':
        from geo import locate
        return locate(body)
    if path=='/api/market/quote':return quote(core,body,actor)
    if path=='/api/market/suggestions':return host_suggestions(core,body)
    if path=='/api/market/recommendations':
        import recommendations, sys
        return recommendations.recommend(core,sys.modules[__name__],body,actor)
    if path=='/api/market/score-plan':
        import recommendations, sys
        return recommendations.score_plan(core,sys.modules[__name__],body,actor)
    if path=='/api/market/invitations':return publish(core,body,actor)
    parts=path.strip('/').split('/')
    if len(parts)==5 and parts[:3]==['api','market','invitations']:return action(core,parts[3],parts[4],body,actor)
    raise ValueError('接口不存在。')

SCHEMA={'type':'object','properties':{'city':{'type':'string'},'keyword':{'type':'string'},'radiusKm':{'type':'number','minimum':0.2,'maximum':20},'taste':{'type':'string'},'budgetCents':{'type':'integer'},'storeCodes':{'type':'array','items':{'type':'string'}}},'required':['city','keyword']}
TOOLS=[
 {'name':'find_nearby_pending','description':'按城市、搜索地标和公里范围获取真实门店及待拼单，按想吃的食物推荐。待拼单是拼好麦的邀请；只展示未领取且未过期的邀请。','inputSchema':SCHEMA,'annotations':{'readOnlyHint':True,'openWorldHint':True}},
 {'name':'get_invitation','description':'查看一份拼单各店报价、双方分配及领取状态。','inputSchema':{'type':'object','properties':{'id':{'type':'string'}},'required':['id']},'annotations':{'readOnlyHint':True}},
 {'name':'claim_invitation','description':'经用户明确同意后领取一个双人拼单位置，官方MCP实时核价；任一门店成功后整单锁定，不会下单或付款。调用需请求头X-Actor为持久的随机身份令牌（至少16位），不得使用麦当劳Token。','inputSchema':{'type':'object','properties':{'id':{'type':'string'},'storeCode':{'type':'string'},'name':{'type':'string'},'expectedTotal':{'type':'integer'}},'required':['id','storeCode','expectedTotal']},'annotations':{'readOnlyHint':False,'destructiveHint':False,'idempotentHint':True}}
]

def rpc(core,request,actor):
    if not isinstance(request,dict) or request.get('jsonrpc')!='2.0':return {'jsonrpc':'2.0','id':None,'error':{'code':-32600,'message':'Invalid request'}}
    id=request.get('id');method=request.get('method');params=request.get('params') or {}
    if id is None:return None
    result=None
    if method=='initialize':
        supported=('2025-03-26','2025-06-18','2025-11-25');version=params.get('protocolVersion')
        result={'protocolVersion':version if version in supported else supported[-1],'capabilities':{'tools':{}},'serverInfo':{'name':'pinghaomai','version':'0.2.0'},'instructions':'位置按地标搜索；必须先展示餐品、门店、取餐时间和分摊，用户同意后才领取。当前不会下单或付款。'}
    elif method=='ping':result={}
    elif method=='tools/list':result={'tools':TOOLS}
    elif method=='tools/call':
        try:
            name=params.get('name');args=params.get('arguments') or {}
            if name=='find_nearby_pending':
                found=search(core,args,actor);allowed=[s['id'] for s in found['stores']]
                chosen=args.get('storeCodes',allowed)
                if not isinstance(chosen,list) or not set(chosen)<=set(allowed):raise ValueError('筛选门店须在官方搜索范围内。')
                data=listing(core,dict(args,storeCodes=chosen,searchId=found['searchId']),actor);data.update(location=found)
            elif name=='get_invitation':data=get(core,args.get('id'),actor)
            elif name=='claim_invitation':
                if not actor:raise ValueError('领取前请配置持久的X-Actor身份。')
                data=claim(core,args.get('id'),args,actor)
            else:return {'jsonrpc':'2.0','id':id,'error':{'code':-32602,'message':'Unknown tool'}}
            result={'content':[{'type':'text','text':json.dumps(data,ensure_ascii=False)}],'structuredContent':data}
        except (ValueError,core.LiveError) as e:
            detail={'error':str(e)}
            if isinstance(e,Conflict) and e.room:detail['room']=e.room
            result={'isError':True,'content':[{'type':'text','text':json.dumps(detail,ensure_ascii=False)}]}
    else:return {'jsonrpc':'2.0','id':id,'error':{'code':-32601,'message':'Method not found'}}
    return {'jsonrpc':'2.0','id':id,'result':result}
