"""Browser integration; fake only the external search response, not the UI state."""
import json
from pathlib import Path
import unittest
from playwright.sync_api import sync_playwright, expect

BASE_URL = 'http://127.0.0.1:8765'
CITY = {'id':1835848,'name':'서울','admin1':'서울특별시','country':'대한민국','label':'서울, 서울특별시, 대한민국','latitude':37.566,'longitude':126.9784,'timezone':'Asia/Seoul','country_code':'KR','provider':'Open-Meteo / GeoNames'}


class PlaceBrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, executable_path='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={'width':1440,'height':1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.requests = []
        self.page.on('request', lambda request: self.requests.append(request))
        self.page.goto(BASE_URL)
        self.page.wait_for_load_state('networkidle')

    def stub_places(self, results=None, status=200):
        data = {'results': [CITY] if results is None else results, 'warnings':[]}
        if status != 200:
            data = {'error':{'code':'PLACE_SEARCH_UNAVAILABLE','message':'장소 검색을 사용할 수 없습니다.'}}
        self.page.route('**/api/places?*', lambda route: route.fulfill(status=status,content_type='application/json',body=json.dumps(data)))

    def select_city(self):
        self.page.locator('#place').fill('서울')
        self.page.locator('#place-search-button').click()
        expect(self.page.locator('#place-results [role=option]')).to_have_count(1)
        self.page.locator('#place').press('ArrowDown')
        self.page.locator('#place').press('Enter')

    def test_empty_start_brand_and_no_automatic_calculation(self):
        expect(self.page.locator('.brand-block')).to_have_accessible_name('Heliaca 처음으로')
        expect(self.page.locator('#copy-markdown')).to_be_disabled()
        self.assertFalse(any('/api/chart' in request.url for request in self.requests))
        self.assertEqual(self.page.locator('#latitude').input_value(), '')
        self.page.screenshot(path='artifacts/heliaca-desktop.png')

    def test_selection_resolves_zone_and_chart_preserves_provider_without_sending_birth_info_to_search(self):
        self.stub_places()
        self.page.locator('#date').fill('1990-01-01')
        self.page.locator('#time').fill('12:00:00')
        self.page.locator('#name').fill('Private name')
        self.select_city()
        self.assertEqual(self.page.locator('#timezone').input_value(),'Asia/Seoul')
        self.assertEqual(self.page.locator('#latitude').input_value(),'37.566')
        expect(self.page.locator('#latitude')).not_to_be_editable()
        with self.page.expect_response('**/api/chart') as response:
            self.page.locator('#calculate-button').click()
        data = response.value.json()
        self.assertEqual(data['normalized']['utc'],'1990-01-01T03:00:00Z')
        self.assertEqual(data['input']['location_source']['place_id'],1835848)
        for request in self.requests:
            if '/api/places?' in request.url:
                self.assertNotIn('1990',request.url)
                self.assertNotIn('Private',request.url)
                self.assertIsNone(request.post_data)
        self.page.locator('#place').fill('부산')
        self.assertEqual(self.page.locator('#latitude').input_value(),'')
        expect(self.page.locator('#copy-markdown')).to_be_disabled()

    def test_manual_override_warns_and_exiting_requires_reselection(self):
        self.stub_places()
        self.select_city()
        self.page.locator('#manual-location-toggle').check()
        self.page.locator('#latitude').fill('37.7')
        expect(self.page.locator('#place-warning')).to_contain_text('5′')
        self.page.locator('#manual-location-toggle').uncheck()
        self.assertEqual(self.page.locator('#timezone').input_value(),'')
        self.page.locator('#calculate-button').click()
        self.assertFalse(any('/api/chart' in request.url for request in self.requests))

    def test_error_and_empty_results_never_fill_zero_coordinates(self):
        self.stub_places(status=502)
        self.page.locator('#place').fill('Missing City')
        self.page.locator('#place-search-button').click()
        expect(self.page.locator('#place-status')).to_contain_text('사용할 수 없습니다')
        self.assertEqual(self.page.locator('#longitude').input_value(),'')
        self.page.unroute('**/api/places?*')
        self.stub_places([])
        self.page.locator('#place-search-button').click()
        expect(self.page.locator('#place-status')).to_contain_text('일치하는 도시가 없습니다')

    def test_mobile_search_and_markdown_dialog_fit_viewport(self):
        self.page.set_viewport_size({'width':390,'height':844})
        self.page.screenshot(path='artifacts/heliaca-mobile.png')
        self.stub_places()
        self.select_city()
        self.page.locator('#date').fill('1990-01-01')
        self.page.locator('#time').fill('12:00:00')
        self.page.locator('#calculate-button').click()
        expect(self.page.locator('#preview-markdown')).to_be_enabled()
        self.page.locator('#preview-markdown').click()
        box = self.page.locator('#markdown-dialog').bounding_box()
        self.assertGreaterEqual(box['x'],0)
        self.assertLessEqual(box['x'] + box['width'],390)
        self.assertEqual(self.page.evaluate('document.documentElement.scrollWidth'),390)
        self.page.screenshot(path='artifacts/heliaca-markdown.png')


if __name__ == '__main__':
    unittest.main(verbosity=2)
