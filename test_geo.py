import io, json, unittest
from unittest.mock import patch
import geo

class GeoTests(unittest.TestCase):
    def setUp(self):
        geo._cache.clear(); geo._last = 0

    def test_validates_coordinates(self):
        for n in [True, '34', None, float('nan'), float('inf'), 91]:
            with self.assertRaises(ValueError):geo.locate({'latitude':n,'longitude':108})

    def test_coarse_coordinates_city_and_cache(self):
        payload={'features':[{'properties':{'geocoding':{'city':'西安市','street':'小寨东路','district':'雁塔区'}}}]}
        with patch('geo.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as call:
            result=geo.locate({'latitude':34.22412345,'longitude':108.94712345})
            self.assertEqual(result['city'],'西安市')
            self.assertEqual(result['keyword'],'小寨东路')
            self.assertIn('lat=34.224&lon=108.947',call.call_args.args[0].full_url)
            geo.locate({'latitude':34.22412345,'longitude':108.94712345})
            self.assertEqual(call.call_count,1)

    def test_service_failure_is_actionable(self):
        with patch('geo.urlopen',side_effect=OSError('secret request details')):
            with self.assertRaisesRegex(ValueError,'手动填写') as error:
                geo.locate({'latitude':34,'longitude':108})
            self.assertNotIn('secret',str(error.exception))

    def test_no_address_and_global_rate_limit(self):
        with patch('geo.urlopen',return_value=io.BytesIO(b'{"features":[]}')):
            with self.assertRaisesRegex(ValueError,'未能识别'):geo.locate({'latitude':34,'longitude':108})
        with self.assertRaisesRegex(ValueError,'频繁'):geo.locate({'latitude':35,'longitude':109})

if __name__=='__main__':unittest.main()
