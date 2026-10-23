"""Resolve drink variant codes through same-store single-item MCP details and quotes."""
import re
from decimal import Decimal, InvalidOperation

DRINK=re.compile(r'可乐|雪碧|咖啡|拿铁|饮料|牛奶|美式|红茶|豆浆|果汁|怡泉')

def priced(meta):
    try:return Decimal(str(meta.get('currentPrice',0)))>0
    except (InvalidOperation,TypeError):return False

def supplement(core,args,menu,detail,selections=None):
    selections=selections or {}
    wanted={}
    for group in detail.get('rounds',[]):
        defaults=[c['code'] for c in group.get('choices',[]) for _ in range(max(0,c.get('quantity',0)))]
        bycode={c['code']:c for c in group.get('choices',[])}
        for index,default in enumerate(defaults):
            code=selections.get(f'{group["id"]}-{index}',default)
            choice=bycode.get(code)
            if choice and DRINK.search(choice['name']) and not priced(menu.get(code,{})):wanted[code]=choice
    parents=list(menu.items())
    for code,choice in wanted.items():
        for parent,meta in parents:
            name=meta.get('name','')
            if not name or name not in choice['name'] or not DRINK.search(name) or re.search(r'套餐|件套|双人|分享|随心配|组合',name):continue
            try:
                response=core.MCP.call('query-meal-detail',dict(args,code=parent))
                rounds=(response.get('data') or {}).get('rounds',[])
                if len(rounds)!=1 or rounds[0].get('quantity')!=1:continue
                group=rounds[0]
                variant=next((v for v in group.get('choices',[]) if v.get('code')==code and v.get('name')==choice['name']),None)
                if variant is None:continue
                member={'code':code,'quantity':1}
                modification=core.default_modification(variant)
                if modification:member['modification']=modification
                product={'productCode':parent,'quantity':1,'roundList':[{'round':str(group['id']),'comboItemList':[member]}]}
                raw=core.MCP.call('calculate-price',dict(args,items=[product],needTableware=False))
                data=raw.get('data') or {};lines=data.get('productList') or []
                if len(lines)!=1 or lines[0].get('productCode')!=parent or lines[0].get('quantity')!=1:continue
                price=lines[0].get('subtotal')
                if type(price) is not int or price<=0:continue
                menu[code]={**menu.get(code,{}),'name':choice['name'],'currentPrice':str(Decimal(price)/100),
                            'image':meta.get('image',''),'referenceSource':{'kind':'single-item-mcp-quote','parentCode':parent,
                            'variantCode':code,'storeCode':args['storeCode'],'reservationDate':args.get('reservationDate'),
                            'traceId':raw.get('traceId'),'queriedAt':core.timestamp()}}
                break
            except core.LiveError:
                # Missing references stay missing; never substitute another size or guessed price.
                continue
