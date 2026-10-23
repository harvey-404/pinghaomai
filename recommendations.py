"""Read-only shortlist verification, cost-first plans and explainable guest scores."""
import json, math, re, time
from concurrent.futures import ThreadPoolExecutor

MAIN=r'汉堡|鸡腿堡|牛堡|鱼堡|麦香鸡|麦香鱼|巨无霸|麦满分|卷|饭'
DRINK=r'可乐|雪碧|咖啡|拿铁|饮料|牛奶|美式|红茶|豆浆'
POPULAR=r'麦辣鸡腿汉?堡|板烧鸡腿堡|薯条|麦乐鸡|麦辣鸡翅|巨无霸'

def weight(food):
    """Use menu reference prices when complete; otherwise use visible part weights."""
    return 4 if re.search(MAIN,food['name']) else 1 if re.search(DRINK,food['name']) else 2

def matcher(want):
    patterns={'麦辣鸡腿堡':r'麦辣鸡腿汉?堡','汉堡':MAIN,'炸鸡':r'炸鸡|鸡翅|鸡块|麦乐鸡|脆汁鸡',
              '小食':r'薯条|薯饼|小食|派','饮品':DRINK,'早餐':r'麦满分|早餐|粥|油条|煎蛋'}
    if want in patterns:return lambda name:bool(re.search(patterns[want],name))
    words=[x for x in re.split(r'[,，、\s]+',want) if x]
    return lambda name:all(x in name for x in words) if words else bool(re.search(MAIN,name))

def split_amount(meal,host_items):
    foods=meal['foods'];host=set(host_items)
    complete=all(type(f.get('referenceCents')) is int and f['referenceCents']>0 for f in foods)
    values=[f['referenceCents'] if complete else weight(f) for f in foods]
    amount=math.ceil(meal['total']*sum(v for f,v in zip(foods,values) if f['id'] in host)/sum(values))
    return min(meal['total']-1,max(1,amount)),('菜单单点参考价比例' if complete else '餐品权重：主食4、小食2、饮品1')

def guest_score(foods,pay,coverage,selected_count):
    """A rule score, deliberately not a probability of a stranger accepting."""
    reference=sum(f.get('referenceCents') or 0 for f in foods)
    complete=all(type(f.get('referenceCents')) is int and f['referenceCents']>0 for f in foods)
    # Price is 40/100. The other points express what the guest actually gets.
    if complete:
        ratio=pay/reference
        price=40 if ratio<=.5 else 32 if ratio<=.7 else 22 if ratio<=.9 else 10 if ratio<=1 else 0
        reason=f'搭子金额约为剩余餐品单点参考价的{round(ratio*100)}%（{price}/40）'
    else:
        price=32 if pay<=1000 else 24 if pay<=1500 else 14 if pay<=2000 else 5
        reason=f'搭子承担¥{pay/100:.2f}，缺少完整单点参考价（{price}/40）'
    popular=20 if any(re.search(POPULAR,f['name']) for f in foods) else 8
    has_main=any(re.search(MAIN,f['name']) for f in foods)
    has_drink=any(re.search(DRINK,f['name']) for f in foods)
    substantial=20 if has_main else 12 if any(not re.search(DRINK,f['name']) for f in foods) else 0
    complementary=10 if len(foods)>=2 and has_drink and len(foods)>sum(bool(re.search(DRINK,f['name'])) for f in foods) else 4
    stores=round(10*coverage/max(1,selected_count))
    reasons=[reason,f'经典餐品匹配 {popular}/20',f'主食或小食充实度 {substantial}/20',
             f'食物与饮品组合 {complementary}/10',f'门店覆盖 {stores}/10']
    return {'score':min(100,price+popular+substantial+complementary+stores),'reasons':reasons}

def plan_for_quote(q,want,selected_count):
    match=matcher(want);foods=q['options'][0]['meal']['foods']
    chosen=next((f for f in foods if match(f['name'])),None)
    if chosen is None and not want:chosen=foods[0]
    if chosen is None:raise ValueError('套餐中没有匹配你想吃的餐品。')
    host=[chosen['id']]
    amounts=[split_amount(o['meal'],host) for o in q['options']]
    host_pay=min(x[0] for x in amounts)
    guests=[f for f in foods if f['id'] not in host]
    scores=[];guest_pays=[]
    for option in q['options']:
        remaining=[f for f in option['meal']['foods'] if f['id'] not in host]
        pay=option['meal']['total']-host_pay;guest_pays.append(pay)
        scores.append(guest_score(remaining,pay,len(q['options']),selected_count))
    worst=min(scores,key=lambda x:x['score'])
    host_references=[next(f for f in option['meal']['foods'] if f['id']==chosen['id']).get('referenceCents') for option in q['options']]
    host_reference=min(host_references) if all(type(value) is int and value>0 for value in host_references) else None
    guest_savings=[]
    for option,pay in zip(q['options'],guest_pays):
        remaining=[f for f in option['meal']['foods'] if f['id'] not in host]
        if not remaining or not all(type(f.get('referenceCents')) is int and f['referenceCents']>0 for f in remaining):
            guest_savings=[];break
        guest_savings.append(sum(f['referenceCents'] for f in remaining)-pay)
    host_saving=host_reference-host_pay if host_reference is not None else None
    guest_saving_min=min(guest_savings) if guest_savings else None
    return {'hostItems':host,'hostFoods':[chosen['name']],'guestFoods':[f['name'] for f in guests],
            'hostPay':host_pay,'guestPayMin':min(guest_pays),'guestPayMax':max(guest_pays),
            'hostReferenceCents':host_reference,'hostSavingCents':host_saving,
            'guestSavingMin':guest_saving_min,'guestSavingMax':max(guest_savings) if guest_savings else None,
            'bothSave':host_saving is not None and host_saving>0 and guest_saving_min is not None and guest_saving_min>0,
            'guestScore':worst['score'],'scoreReasons':worst['reasons'],'scoreBasis':'取各发布门店中最低分，规则评分，不是拼成概率',
            'allocationBasis':'以最低建议承担额作为所有门店的统一金额；'+ '、'.join(dict.fromkeys(x[1] for x in amounts)),
            'totalMin':min(o['meal']['total'] for o in q['options']),'totalMax':max(o['meal']['total'] for o in q['options'])}

def recommend(core,market,body,actor):
    catalog=market.host_suggestions(core,body);want=core.short_text(body.get('taste',''),'想吃的食物',80)
    match=matcher(want);candidates=catalog['suggestions']
    # Reference prices choose what to verify; no unverified price is used in final ranking.
    def reference(c):return min(c.get('referencePrices') or [10000])
    direct=sorted((c for c in candidates if match(c['name'])),key=reference)
    flexible=sorted((c for c in candidates if re.search('随心配|任选|双人|分享',c['name']) and c not in direct),key=reference)
    shortlist=direct[:6]+flexible[:8-len(direct[:6])]
    if not want:shortlist=sorted(candidates,key=reference)[:8]
    failures=[]
    def one(candidate):
        try:
            core.MCP.begin()
            request={'storeCodes':body['storeCodes'],'pickup':body['pickup'],'mealId':candidate['mealId'],'useCard':False}
            q=market.quote(core,request,actor)
            foods=q['options'][0]['meal']['foods']
            if want and not any(match(f['name']) for f in foods):
                replacement=next(((f['id'],c['code']) for f in foods for c in f['choices'] if match(c['name'])),None)
                if replacement is None:raise ValueError('默认组成与可选替换中没有你想吃的餐品。')
                request['selections']={replacement[0]:replacement[1]};q=market.quote(core,request,actor)
            plan=plan_for_quote(q,want,len(body['storeCodes']))
            meal=q['options'][0]['meal']
            return {'mealId':candidate['mealId'],'name':meal['name'],'image':meal.get('image',''),
                    'storeCodes':[x['store']['id'] for x in q['options']],'quote':q,'plan':plan,
                    'selections':meal['selections'],'reasons':[f'真实试算{len(q["options"])}家门店','不含随单购卡方案']}
        except (ValueError,core.LiveError) as exc:return {'error':str(exc),'name':candidate['name']}
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(one,shortlist))
    valid=[]
    for result in results:
        if 'error' in result:failures.append(result)
        elif result['plan']['bothSave']:valid.append(result)
    valid.sort(key=lambda x:(x['plan']['hostPay'],-x['plan']['guestScore'],x['plan']['totalMin']))
    return {'suggestions':valid[:3],'verifiedCount':len(valid),'attemptedCount':len(shortlist),
            'failures':catalog['failures']+failures,'tasteOptions':catalog['tasteOptions'],
            'basis':f'本次核验{len(shortlist)}款候选，{len(valid)}款双方都比各自单点参考价便宜；只推荐每家发布门店双方参考价完整、且两个人都严格省钱的方案。先按拼成后你的建议承担额升序，再按剩余餐品吸引力评分降序。不是全菜单最低价；评分不是拼成概率。',
            'queriedAt':core.timestamp()}

def score_plan(core,market,body,actor):
    if not isinstance(body.get('quoteId'),str):raise ValueError('请提供有效报价。')
    with core.connect() as db:
        market.db_init(db)
        row=db.execute('SELECT owner,expires,data FROM market_quotes WHERE id=?',(body.get('quoteId'),)).fetchone()
    if not row or row[0]!=actor or row[1]<time.time():raise ValueError('报价已过期，请重新推荐。')
    q=json.loads(row[2]);host=body.get('hostItems');codes=body.get('storeCodes')
    known={x['store']['id'] for x in q['options']}
    if not isinstance(codes,list) or not codes or any(not isinstance(x,str) for x in codes) or len(set(codes))!=len(codes) or not set(codes)<=known:raise ValueError('请选择有效发布门店。')
    foods={f['id'] for f in q['options'][0]['meal']['foods']}
    if not isinstance(host,list) or any(not isinstance(x,str) for x in host) or not host or len(set(host))!=len(host) or not set(host)<foods:raise ValueError('请给两个人都保留至少一份食物。')
    result=[]
    for option in q['options']:
        if option['store']['id'] not in codes:continue
        core.valid_pay(body.get('hostPay'),option['meal']['total'])
        remaining=[f for f in option['meal']['foods'] if f['id'] not in host]
        result.append(guest_score(remaining,option['meal']['total']-body['hostPay'],len(codes),len(known)))
    worst=min(result,key=lambda x:x['score'])
    return {'guestScore':worst['score'],'scoreReasons':worst['reasons'],'scoreBasis':'按当前分配、承担金额和所选门店计算；取各店最低分，不是拼成概率。'}
