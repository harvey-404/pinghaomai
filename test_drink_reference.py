import copy, types, unittest
import drink_reference as r

class DrinkReferenceTests(unittest.TestCase):
    def run_lookup(self,variant='3050',subtotal=1000,existing=None):
        calls=[]
        def call(name,args):
            calls.append((name,args))
            if name=='query-meal-detail':return {'data':{'rounds':[{'id':1,'quantity':1,'choices':[{'code':variant,'name':'可乐中杯'}]}]}}
            return {'traceId':'trace','data':{'productList':[{'productCode':'parent','quantity':1,'subtotal':subtotal}]}}
        core=types.SimpleNamespace(MCP=types.SimpleNamespace(call=call),LiveError=RuntimeError,
                                   default_modification=lambda v:None,timestamp=lambda:'now')
        menu={'parent':{'name':'可乐','currentPrice':'9.5'}}
        if existing:menu['3050']=existing
        detail={'rounds':[{'id':2,'quantity':1,'choices':[{'code':'3050','name':'可乐中杯','quantity':1}]}]}
        r.supplement(core,{'storeCode':'store','reservationDate':'date'},menu,detail)
        return menu,calls

    def test_exact_variant_quote_instead_of_parent_small_price(self):
        menu,calls=self.run_lookup()
        self.assertEqual(menu['3050']['currentPrice'],'10')
        self.assertEqual(menu['3050']['referenceSource']['storeCode'],'store')
        self.assertEqual(calls[-1][1]['items'][0]['roundList'][0]['comboItemList'][0]['code'],'3050')

    def test_different_variant_or_invalid_price_remains_missing(self):
        for kwargs in ({'variant':'3000'},{'subtotal':0},{'subtotal':'1000'}):
            menu,_=self.run_lookup(**kwargs)
            self.assertNotIn('3050',menu)

    def test_existing_exact_price_skips_queries(self):
        menu,calls=self.run_lookup(existing={'currentPrice':'10'})
        self.assertEqual(calls,[])

if __name__=='__main__':unittest.main()
