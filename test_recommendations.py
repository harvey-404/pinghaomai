import copy, types, unittest
import recommendations as r

def food(id,name,reference=None):return {'id':id,'name':name,'referenceCents':reference,'choices':[]}
def quote(total=3000,guest='薯条',main_reference=2000,guest_reference=1000):
    return {'createdAt':'2026-10-23T12:00:00+08:00','options':[{'store':{'id':'a'},'meal':{
        'id':'meal','name':'汉堡套餐','total':total,'foods':[food('main','汉堡',main_reference),food('side',guest,guest_reference)],'selections':{}}}]}

class RecommendationTests(unittest.TestCase):
    def test_split_uses_complete_reference_prices(self):
        amount,basis=r.split_amount(quote()['options'][0]['meal'],['main'])
        self.assertEqual(amount,2000);self.assertIn('参考价',basis)

    def test_missing_one_reference_uses_same_weight_system_for_every_food(self):
        q=quote(3000,guest='可乐',guest_reference=None)
        amount,basis=r.split_amount(q['options'][0]['meal'],['main'])
        self.assertEqual(amount,2400);self.assertIn('主食4',basis)

    def test_common_host_amount_is_valid_at_every_store_and_score_is_worst(self):
        q=quote(2000);q['options'].append(copy.deepcopy(q['options'][0]));q['options'][1]['meal']['total']=4000
        plan=r.plan_for_quote(q,'汉堡',2)
        self.assertEqual(plan['hostPay'],1334)
        self.assertEqual(plan['guestPayMin'],666);self.assertEqual(plan['guestPayMax'],2666)
        worst=r.guest_score(q['options'][1]['meal']['foods'][1:],2666,2,2)['score']
        self.assertEqual(plan['guestScore'],worst)

    def test_no_matching_food_does_not_invent_an_allocation(self):
        with self.assertRaises(ValueError):r.plan_for_quote(quote(),'麦乐鸡',1)

    def test_price_penalty_and_score_range(self):
        foods=[food('side','薯条',1500),food('drink','可乐',1000)]
        low=r.guest_score(foods,800,1,3)['score'];high=r.guest_score(foods,3000,1,3)['score']
        self.assertGreater(low,high);self.assertTrue(0<=high<low<=100)

    def run_recommendations(self,qs):
        candidates=[{'mealId':id,'name':'汉堡套餐'+id,'referencePrices':[i+1]} for i,id in enumerate(qs)]
        core=types.SimpleNamespace(MCP=types.SimpleNamespace(begin=lambda:None),LiveError=RuntimeError,
            short_text=lambda value,*args:value,timestamp=lambda:'now')
        market=types.SimpleNamespace(host_suggestions=lambda *args:{'suggestions':candidates,'failures':[],'tasteOptions':[]},
            quote=lambda core,request,actor:copy.deepcopy(qs[request['mealId']]))
        return r.recommend(core,market,{'storeCodes':['a'],'pickup':'now','taste':'汉堡'},'actor')

    def test_only_three_and_money_is_strictly_first(self):
        qs={str(i):quote(total) for i,total in enumerate([3200,1200,2000,1600,2400])}
        result=self.run_recommendations(qs)
        self.assertEqual([x['plan']['hostPay'] for x in result['suggestions']],[800,1067,1334])
        self.assertEqual(result['verifiedCount'],4)

    def test_excludes_equal_more_expensive_and_unknown_reference(self):
        qs={'cheap':quote(2400),'equal':quote(3000),'expensive':quote(3600),
            'unknown':quote(1000,main_reference=None)}
        result=self.run_recommendations(qs)
        self.assertEqual([x['mealId'] for x in result['suggestions']],['cheap'])

    def test_no_saving_means_no_recommendations(self):
        result=self.run_recommendations({'equal':quote(3000),'expensive':quote(3600)})
        self.assertEqual(result['suggestions'],[])

    def test_guest_must_save_at_every_store(self):
        mixed=quote(2000)
        other=copy.deepcopy(mixed['options'][0]);other['store']['id']='b';other['meal']['total']=2400
        mixed['options'].append(other)
        result=self.run_recommendations({'mixed':mixed,'both':quote(2400),'missing':quote(1000,guest_reference=None)})
        self.assertEqual([x['mealId'] for x in result['suggestions']],['both'])
        plan=result['suggestions'][0]['plan']
        self.assertEqual(plan['hostSavingCents'],400)
        self.assertEqual(plan['guestSavingMin'],200)
        self.assertEqual(plan['guestSavingMax'],200)

    def test_guest_savings_follow_each_store_reference_and_price(self):
        q=quote(2000)
        other=copy.deepcopy(q['options'][0]);other['store']['id']='b'
        other['meal']['total']=2100;other['meal']['foods'][1]['referenceCents']=1200
        q['options'].append(other)
        plan=r.plan_for_quote(q,'汉堡',2)
        self.assertTrue(plan['bothSave'])
        self.assertEqual(plan['guestSavingMin'],313)
        self.assertEqual(plan['guestSavingMax'],413)

    def test_equal_host_cost_prefers_better_remaining_score(self):
        bad=quote(2400,guest='可乐',main_reference=2000,guest_reference=1000)
        good=quote(2400,guest='薯条',main_reference=2000,guest_reference=1000)
        result=self.run_recommendations({'bad':bad,'good':good})
        self.assertEqual(result['suggestions'][0]['mealId'],'good')

if __name__=='__main__':unittest.main()

