"""Two-person matching with live, read-only McDonald's MCP queries."""
import argparse, copy, datetime as dt, json, os, secrets, sqlite3, threading, sys
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from mcp_gateway import Gateway, LiveError, TZ, timestamp
import market

ROOT=Path(__file__).parent
DB=Path(os.environ.get('PHM_DB',str(ROOT/'live.sqlite3')))
LOCK=threading.RLock()
MCP=Gateway()
STORES={}
QUOTES={}
def now():return dt.datetime.now(TZ).replace(tzinfo=None)
@contextmanager
def connect():
    db=sqlite3.connect(DB)
    try:
        with db:
            db.execute('CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            yield db
    finally:db.close()
def save(db,r):db.execute('INSERT OR REPLACE INTO rooms VALUES (?,?)',(r['id'],json.dumps(r,ensure_ascii=False)))
def load(db,id):
    row=db.execute('SELECT data FROM rooms WHERE id=?',(id,)).fetchone()
    if not row:raise ValueError('房间不存在，请检查链接。')
    return json.loads(row[0])
def actor_role(r,actor):return 'host' if actor==r['hostToken'] else 'guest' if actor==r.get('guestToken') else 'visitor'
def view(r,actor):
    result={k:v for k,v in r.items() if k not in ('hostToken','guestToken')}
    result['role']=actor_role(r,actor);result['expired']=dt.datetime.fromisoformat(r['expiresAt'])<=now()
    return result
def short_text(value,label,limit,default=''):
    if not isinstance(value,str) or len(value)>limit:raise ValueError(label+'格式不正确。')
    return value.strip() or default
def context(store_code,pickup,store=None):
    store=store or STORES.get(store_code)
    if not store:raise ValueError('请先搜索并选择门店。')
    args={'storeCode':store_code,'orderType':1,'beType':1}
    if pickup=='now':
        if not store.get('businessStatus'):raise ValueError('门店当前暂停营业，请选择支持预约的门店和时间。')
    else:
        try:time=dt.datetime.fromisoformat(pickup)
        except (ValueError,TypeError):raise ValueError('请选择有效取餐时间。')
        if time.tzinfo is not None or time<=now() or time>now()+dt.timedelta(days=7):raise ValueError('请选择未来七天内的取餐时间。')
        if not store.get('reservation'):raise ValueError('这家门店当前不支持预约。')
        allowed=store.get('reservationTimeOptions',[])
        if allowed and time.date().isoformat() not in [x.get('date') for x in allowed]:raise ValueError('请选择官方返回的可预约日期。')
        args['reservationDate']=time.strftime('%Y-%m-%d %H:%M')
    return args
def get_menu(args):
    source=MCP.call('query-meals',args);data=source.get('data') or {};meals=data.get('meals') or {}
    if not isinstance(meals,dict):raise LiveError('门店菜单暂不可用，请重新查询。')
    return source,meals
def default_modification(choice):
    values=[]
    for group in choice.get('modification',{}).get('items',[]):
        for v in group.get('values',[]):
            selected=v.get('selectedQuantity',0)>0
            key=v.get('selectedKey') if selected else v.get('unselectedKey')
            if key is not None:values.append({'code':v['code'],'key':key,'quantity':v.get('selectedQuantity',1) if selected else 0})
    return {'values':values} if values else None
def build_meal(code,detail,menu,selections=None):
    meta=menu[code];round_list=[];foods=[];slots={};choices_in=selections or {}
    if not isinstance(choices_in,dict):raise ValueError('套餐替换格式不正确。')
    for group in detail.get('rounds',[]):
        quantity=group.get('quantity',group.get('minQuantity',0))
        if type(quantity)!=int or not 0<quantity<=30:raise ValueError('这个套餐的可选数量暂不支持双人拆分。')
        choices=group.get('choices',[]);bycode={v['code']:v for v in choices};defaults=[]
        for v in choices:defaults.extend([v['code']]*max(0,v.get('quantity',0)))
        if len(defaults)!=quantity:raise ValueError('该套餐缺少完整默认选项，暂不能发布。')
        grouped={}
        for index,default in enumerate(defaults):
            id=f'{group["id"]}-{index}';selected=choices_in.get(id,default)
            if selected not in bycode:raise ValueError('餐品替换已不可用，请重新选择套餐。')
            v=bycode[selected];slots[id]=selected;grouped[selected]=grouped.get(selected,0)+1
            try:reference=int(round(float(menu.get(selected,{}).get('currentPrice',0))*100))
            except (ValueError,TypeError,OverflowError):reference=0
            foods.append({'id':id,'code':selected,'name':v['name'],'image':menu.get(selected,{}).get('image') or meta.get('image',''),'referenceCents':reference if reference>0 else None,'referenceSource':menu.get(selected,{}).get('referenceSource'),'group':group['name'],'choices':[{'code':x['code'],'name':x['name'],'diffPrice':x.get('diffPrice','')} for x in choices]})
        combo=[]
        for selected,count in grouped.items():
            v=bycode[selected]
            if v.get('maxQuantity',-1)>=0 and count>v['maxQuantity']:raise ValueError('该餐品超出套餐可选数量。')
            member={'code':selected,'quantity':count};mod=default_modification(v)
            if mod:member['modification']=mod
            combo.append(member)
        round_list.append({'round':str(group['id']),'comboItemList':combo})
    if set(choices_in)-set(slots):raise ValueError('套餐结构已变化，请重新选择。')
    if not 2<=len(foods)<=30:raise ValueError('请选择至少含两份餐品的套餐。')
    return {'id':code,'name':detail.get('name',meta['name']),'image':meta.get('image',''),'foods':foods,'selections':slots,'product':{'productCode':code,'quantity':1,'roundList':round_list}}
def live_quote(store,pickup,code,selections=None,use_card=False,expected_foods=None):
    args=context(store['id'],pickup,store);source,menu=get_menu(args)
    if code not in menu:raise ValueError('这个套餐在所选门店或时段已不可用，请重新选择。')
    d=MCP.call('query-meal-detail',dict(args,code=code))
    from drink_reference import supplement
    supplement(sys.modules[__name__],args,menu,d.get('data') or {},selections)
    meal=build_meal(code,d.get('data') or {},menu,selections)
    if expected_foods is not None:
        before=[(f['id'],f['code'],f['name']) for f in expected_foods];after=[(f['id'],f['code'],f['name']) for f in meal['foods']]
        if before!=after:raise ValueError('套餐组成已变化，请取消房间后重新发起，避免分到不同餐品。')
    calc=dict(args,items=[meal['product']],needTableware=False)
    if use_card:
        offer=menu[code].get('withOrder')
        if not offer:raise ValueError('当前没有这个套餐的随单购卡方案，请取消购卡选项后重新核价。')
        card={k:v for k,v in offer.items() if k in ('cardId','cardType','membershipCode')}
        if offer.get('specId'):card['membershipSpecId']=offer['specId']
        calc['withOrder']=card
    raw=MCP.call('calculate-price',calc);data=raw.get('data') or {};lines=data.get('productList') or []
    ordered=[x for x in lines if x.get('productCode')==code]
    if sum(x.get('quantity',0) for x in ordered)!=1 or not isinstance(data.get('price'),int) or data['price']<=0:raise LiveError('官方试算未完整计入所选套餐，已停止发布，请换一份套餐。')
    extra=[{'name':x['productName'],'amount':x.get('subtotal',0),'quantity':x.get('quantity',1)} for x in lines if x.get('productCode')!=code]
    fees=[{'name':name,'amount':data.get(key,0)} for key,name in [('packingPrice','打包费'),('tablewarePrice','餐具费'),('deliveryPrice','配送费')] if data.get(key,0)]
    meal.update(total=data['price'],productTotal=sum(x.get('subtotal',0) for x in ordered),extras=extra,fees=fees,quotedAt=timestamp(),sourceTime=raw.get('datetime'),traceId=raw.get('traceId'),takeWays=data.get('takeWayList',[]),cardOffered=bool(menu[code].get('withOrder')),useCard=bool(use_card))
    return meal
def valid_pay(value,total):
    if type(value)!=int or not 0<value<total:raise ValueError('承担金额应大于0且小于最新总价，两个人都需承担金额。')
def refresh_room(r):
    if dt.datetime.fromisoformat(r['expiresAt'])<=now():raise ValueError('已超过约定取餐时间，不能继续加入或确认。')
    meal=live_quote(r['store'],r['requestPickup'],r['meal']['id'],r['meal']['selections'],r['meal']['useCard'],r['meal']['foods'])
    changed=meal['total']!=r['meal']['total'] or meal['extras']!=r['meal'].get('extras') or meal['fees']!=r['meal'].get('fees')
    r['meal']=meal
    if changed:
        r['hostConfirmed']=False;r['guestConfirmed']=False;r['status']='matched' if r.get('guestToken') else 'waiting'
    return changed

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):pass
    def send_json(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def actor(self):
        value=self.headers.get('X-Actor','');return value if 16<=len(value)<=128 and value.isascii() and value.isprintable() else ''
    def do_GET(self):
        parsed=urlparse(self.path);path=parsed.path;q=parse_qs(parsed.query)
        try:
            MCP.begin()
            if path=='/health':return self.send_json({'ok':True,'version':'0.3.1','ordersEnabled':False,'socialEnabled':True})
            if path.startswith('/api/market/social/photos/'):
                import social
                raw=social.image(sys.modules[__name__],path.split('/')[-1],q.get('v',[''])[0],self.actor())
                self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            if path=='/mcp':
                self.send_response(405);self.send_header('Allow','POST');self.end_headers();return
            if path.startswith('/api/market/'):
                return self.send_json(market.get_api(sys.modules[__name__],path,{k:v[0] for k,v in q.items()},self.actor()))
            if path=='/api/stores':
                city=short_text(q.get('city',['西安市'])[0],'城市',40);keyword=short_text(q.get('keyword',[''])[0],'门店关键词',80)
                if not city or not keyword:raise ValueError('请填写城市和地标或门店关键词。')
                result=MCP.call('query-nearby-stores',{'beType':1,'searchType':2,'city':city,'keyword':keyword});stores=[]
                for s in result.get('data') or []:
                    s=dict(s,id=s['storeCode'],name=s['storeName']);STORES[s['id']]=s;stores.append(s)
                return self.send_json({'stores':stores,'queriedAt':timestamp(),'traceId':result.get('traceId')})
            if path=='/api/meals':
                store=q.get('storeCode',[''])[0];pickup=q.get('pickup',[''])[0];source,meals=get_menu(context(store,pickup));categories={}
                for category in (source.get('data') or {}).get('categories',[]):
                    for m in category.get('meals',[]):categories.setdefault(m['code'],category['name'])
                rows=[dict(v,id=k,category=categories.get(k,'')) for k,v in meals.items()]
                rows.sort(key=lambda x:(not any(w in x['name'] for w in ['随心配','双人','组合','三件','套餐','分享','任选']),x['name']))
                return self.send_json({'meals':rows,'queriedAt':timestamp(),'sourceTime':source.get('datetime')})
            if path=='/api/rooms':
                with connect() as db:rooms=[view(json.loads(row[0]),self.actor()) for row in db.execute('SELECT data FROM rooms ORDER BY rowid DESC')]
                return self.send_json({'rooms':[r for r in rooms if r['role']!='visitor' or (r['status']=='waiting' and not r['expired'])]})
            if path.startswith('/api/rooms/'):
                with connect() as db:r=load(db,path.split('/')[-1])
                return self.send_json(view(r,self.actor()))
            files={'/':'index.html','/app.js':'app.js','/social.js':'social.js','/styles.css':'styles.css',**{f'/anime-pair-{i:02d}.webp':f'anime-pair-{i:02d}.webp' for i in range(1,7)}}
            if path not in files:return self.send_json({'error':'页面不存在'},404)
            file=ROOT/'public'/files[path];raw=file.read_bytes();self.send_response(200);self.send_header('Content-Type',{'html':'text/html; charset=utf-8','js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8','webp':'image/webp'}[file.suffix[1:]]);self.send_header('Cache-Control','public, max-age=86400' if file.suffix=='.webp' else 'no-cache');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        except LiveError as exc:self.send_json({'error':str(exc),'liveUnavailable':True},502)
        except (ValueError,KeyError,TypeError) as exc:self.send_json({'error':str(exc)},400)
        except Exception:self.send_json({'error':'查询服务暂时异常，请重试。'},500)
    def do_POST(self):
        origin=self.headers.get('Origin')
        allowed={f'http://{self.headers.get("Host")}',os.environ.get('PHM_PUBLIC_ORIGIN','http://127.0.0.1:8766')}
        if origin and origin not in allowed:return self.send_json({'error':'请求来源不匹配'},403)
        try:
            MCP.begin();size=int(self.headers.get('Content-Length','0'))
            max_size=2200000 if urlparse(self.path).path.startswith('/api/market/social/invitations/') and urlparse(self.path).path.endswith('/photo/upload') else 20000
            if not 0<size<=max_size:raise ValueError('请求长度不正确。')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError('请求格式不正确。')
            actor=self.actor()
            path=urlparse(self.path).path
            if path=='/mcp':
                result=market.rpc(sys.modules[__name__],body,actor)
                if result is None:self.send_response(202);self.end_headers();return
                return self.send_json(result)
            if not actor:raise ValueError('请刷新页面后重试。')
            if path.startswith('/api/market/'):
                return self.send_json(market.post_api(sys.modules[__name__],path,body,actor),201 if path=='/api/market/invitations' else 200)
            if path=='/api/quote':
                store=STORES.get(body.get('storeCode'))
                if not store:raise ValueError('请先搜索并选择门店。')
                if type(body.get('useCard',False))!=bool:raise ValueError('随单购选项不正确。')
                meal=live_quote(store,body.get('pickup'),body.get('mealId'),body.get('selections'),body.get('useCard',False));id=secrets.token_urlsafe(18)
                with LOCK:
                    QUOTES[id]={'actor':actor,'meal':meal,'store':store,'pickup':body['pickup'],'created':now()}
                    for key,value in list(QUOTES.items()):
                        if now()-value['created']>dt.timedelta(minutes=15):QUOTES.pop(key,None)
                return self.send_json({'quoteId':id,'meal':meal,'store':store,'pickup':body['pickup']})
            if path=='/api/rooms':
                with LOCK:q=copy.deepcopy(QUOTES.get(body.get('quoteId')))
                if not q or q['actor']!=actor or now()-q['created']>dt.timedelta(minutes=10):raise ValueError('报价已过期，请重新实时核价。')
                ids=body.get('hostItems',[]);allids={f['id'] for f in q['meal']['foods']}
                if not isinstance(ids,list) or not all(isinstance(x,str) for x in ids) or not ids or len(set(ids))!=len(ids) or not set(ids)<allids:raise ValueError('两个人都至少需要分到一份餐品。')
                name=short_text(body.get('name',''),'昵称',16,'麦麦搭子');note=short_text(body.get('note',''),'备注',100)
                meal=live_quote(q['store'],q['pickup'],q['meal']['id'],q['meal']['selections'],q['meal']['useCard'],q['meal']['foods'])
                if meal['total']!=q['meal']['total'] or meal['extras']!=q['meal']['extras'] or meal['fees']!=q['meal']['fees']:raise ValueError('价格或附加费用已变化，请重新核价并确认分摊后再发布。')
                valid_pay(body.get('hostPay'),meal['total']);pickup=(now()+dt.timedelta(minutes=15)).isoformat(timespec='minutes') if q['pickup']=='now' else q['pickup']
                r={'id':secrets.token_urlsafe(6),'store':q['store'],'meal':meal,'pickup':pickup,'requestPickup':q['pickup'],'expiresAt':pickup,'hostItems':ids,'hostPay':body['hostPay'],'hostName':name,'guestName':None,'note':note,'hostToken':actor,'guestToken':None,'hostConfirmed':False,'guestConfirmed':False,'status':'waiting','createdAt':timestamp()}
                with LOCK,connect() as db:
                    if body.get('quoteId') not in QUOTES:raise ValueError('这份报价已发布，请重新核价后再发起。')
                    save(db,r);QUOTES.pop(body.get('quoteId'),None)
                return self.send_json(view(r,actor),201)
            parts=path.strip('/').split('/')
            if len(parts)!=4 or parts[:2]!=['api','rooms']:return self.send_json({'error':'接口不存在'},404)
            with LOCK,connect() as db:
                r=load(db,parts[2]);action=parts[3];role=actor_role(r,actor)
                if action not in ('reprice','join','confirm','leave','cancel'):raise ValueError('当前版本没有下单或付款功能。')
                if action=='reprice':
                    if r['status']=='cancelled':raise ValueError('这份拼单已取消。')
                    if role=='visitor' and r['status']!='waiting':raise ValueError('当前拼单已满。')
                    changed=refresh_room(r);save(db,r);return self.send_json({'room':view(r,actor),'priceChanged':changed})
                elif action=='join':
                    if role=='host':raise ValueError('不能加入自己发起的拼单。')
                    if r['status']!='waiting' or r.get('guestToken'):raise ValueError('这个位置已经有人加入了。')
                    name=short_text(body.get('name',''),'昵称',16,'新搭子');changed=refresh_room(r)
                    if changed or body.get('expectedTotal')!=r['meal']['total']:
                        save(db,r);return self.send_json({'room':view(r,actor),'priceChanged':True,'error':'最新价格已更新，请确认新的分摊金额后再次加入。'},409)
                    valid_pay(r['hostPay'],r['meal']['total']);r.update(guestToken=actor,guestName=name,status='matched',hostConfirmed=False,guestConfirmed=False)
                elif action=='confirm':
                    if role not in ('host','guest') or r['status'] not in ('matched','confirmed'):raise ValueError('请在两人成团后分别确认。')
                    changed=refresh_room(r)
                    if changed or body.get('expectedTotal')!=r['meal']['total']:
                        save(db,r);return self.send_json({'room':view(r,actor),'priceChanged':True,'error':'价格发生变化，已清除双方确认，请重新确认。'},409)
                    valid_pay(r['hostPay'],r['meal']['total']);r[role+'Confirmed']=True
                    if r['hostConfirmed'] and r['guestConfirmed']:r['status']='confirmed'
                elif action=='leave':
                    if role!='guest' or r['status'] not in ('matched','confirmed'):raise ValueError('当前不能退出。')
                    r.update(guestToken=None,guestName=None,status='waiting',hostConfirmed=False,guestConfirmed=False)
                elif action=='cancel':
                    if role!='host' or r['status'] not in ('waiting','matched','confirmed'):raise ValueError('当前不能取消。')
                    r['status']='cancelled'
                save(db,r);return self.send_json(view(r,actor))
        except market.Conflict as exc:self.send_json({'error':str(exc),**({'room':exc.room} if exc.room else {})},409)
        except LiveError as exc:self.send_json({'error':str(exc),'liveUnavailable':True},502)
        except (ValueError,KeyError,TypeError) as exc:self.send_json({'error':str(exc)},400)
        except Exception:self.send_json({'error':'拼单服务暂时异常，请重试。'},500)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8766);parser.add_argument('--host',default='127.0.0.1');args=parser.parse_args()
    with connect():pass
    app=ThreadingHTTPServer((args.host,args.port),Handler);print(f'Pinghaomai live read-only: http://{args.host}:{args.port}',flush=True);app.serve_forever()
