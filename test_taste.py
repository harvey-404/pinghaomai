import unittest
from market import taste_choices

class TasteChoices(unittest.TestCase):
    def menu(self,*names):return [('store-a',{str(i):{'name':name} for i,name in enumerate(names)})]

    def test_lunch_three_different_intents(self):
        menus=self.menu('麦辣鸡腿堡套餐','麦辣鸡翅','薯条','拿铁','麦满分')
        result=taste_choices(menus,'2026-10-24T12:00')
        self.assertEqual([x['id'] for x in result],['mcspicy','fries','chicken'])

    def test_researched_favorites_have_sources_and_cover_product_alias(self):
        menus=self.menu('麦辣鸡腿汉堡套餐','板烧鸡腿堡三件套','薯条','巨无霸','麦辣鸡翅')
        result=taste_choices(menus,'2026-10-24T12:00')
        self.assertEqual([x['id'] for x in result],['mcspicy','grilled','fries'])
        self.assertTrue(all(x['sourceUrl'].startswith('https://www.mcdonalds.com.cn/') for x in result))

    def test_breakfast_and_afternoon_have_different_order(self):
        menus=self.menu('麦满分','拿铁','薯饼','巨无霸','鸡块')
        self.assertEqual(taste_choices(menus,'2026-10-24T08:00')[0]['id'],'breakfast')
        self.assertEqual(taste_choices(menus,'2026-10-24T15:00')[0]['id'],'drink')

    def test_never_invents_unavailable_categories(self):
        result=taste_choices(self.menu('拿铁'),'2026-10-24T12:00')
        self.assertEqual([x['id'] for x in result],['drink'])
        self.assertEqual(taste_choices([],'2026-10-24T12:00'),[])

if __name__=='__main__':unittest.main()
