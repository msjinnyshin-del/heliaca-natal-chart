"""Real local-server/browser checks. Run separately from engine unit tests."""
import os
from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright, expect

BASE_URL = os.environ.get("NATAL_TEST_URL", "http://127.0.0.1:8765")
ARTIFACTS = Path(__file__).resolve().parent.parent / "artifacts"


class BrowserChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
        options = {"headless": True}
        if chrome.exists():
            options["executable_path"] = str(chrome)
        cls.browser = cls.playwright.chromium.launch(**options)
        ARTIFACTS.mkdir(exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1100}, accept_downloads=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.goto(BASE_URL)
        self.page.wait_for_load_state("networkidle")
        self.page.locator('#manual-location-toggle').check()
        for field, value in {'date':'1985-07-14','time':'21:45:00','place':'New York, New York, USA','latitude':'40.7128','longitude':'-74.006','timezone':'America/New_York'}.items():
            self.page.locator('#' + field).fill(value)
        self.calculate()
        expect(self.page.locator("#positions-body tr")).to_have_count(16)

    def calculate(self):
        self.page.locator("#calculate-button").click()

    def test_reference_values_and_no_js_errors(self):
        expect(self.page.locator("#positions-body")).to_contain_text("22°31′39″")
        expect(self.page.locator("#positions-body")).to_contain_text("17°56′56″")
        expect(self.page.locator("#chart-stage svg")).to_have_count(1)
        self.assertEqual(self.errors, [])
        self.page.locator("#tab-aspects").click()
        self.page.screenshot(path=str(ARTIFACTS / "desktop.png"), full_page=True)

    def test_mean_node_changes_result(self):
        self.page.locator('input[name="node_mode"][value="mean"]').check()
        self.calculate()
        expect(self.page.locator("#positions-body")).to_contain_text("14°49′08″")

    def test_edit_invalidates_download_then_new_date_recalculates(self):
        moon_before = self.page.locator("#positions-body tr").nth(1).inner_text()
        self.page.locator("#date").fill("1985-07-15")
        expect(self.page.locator("#download-svg")).to_be_disabled()
        self.calculate()
        expect(self.page.locator("#download-svg")).to_be_enabled()
        self.assertNotEqual(self.page.locator("#positions-body tr").nth(1).inner_text(), moon_before)

    def test_dst_fold_choice_can_finish_calculation(self):
        self.page.locator("#date").fill("2023-11-05")
        self.page.locator("#time").fill("01:30:00")
        self.calculate()
        expect(self.page.locator(".fold-choice")).to_have_count(2)
        self.page.locator(".fold-choice").first.click()
        expect(self.page.locator("#freshness-badge")).to_have_text("현재 입력 결과")
        expect(self.page.locator("#download-svg")).to_be_enabled()
        self.page.locator("#tab-evidence").click()
        expect(self.page.locator("#evidence-register")).to_contain_text("2023-11-05T05:30:00Z")

    def test_dst_gap_rejected_without_download(self):
        self.page.locator("#date").fill("2023-03-12")
        self.page.locator("#time").fill("02:30:00")
        self.calculate()
        expect(self.page.locator("#message")).to_contain_text("NONEXISTENT_LOCAL_TIME")
        expect(self.page.locator("#download-svg")).to_be_disabled()

    def test_fresh_start_has_no_personal_example_or_invented_noon(self):
        self.page.reload()
        self.assertEqual(self.page.locator("#place").input_value(), "")
        self.assertEqual(self.page.locator("#date").input_value(), "")
        self.assertEqual(self.page.locator("#time").input_value(), "")
        expect(self.page.locator('[data-preset]')).to_have_count(0)
        expect(self.page.locator("#download-svg")).to_be_disabled()

    def test_download_is_independent_styled_svg(self):
        displayed_stroke = self.page.locator('.wheel-house').first.evaluate('el => getComputedStyle(el).stroke')
        with self.page.expect_download() as download_info:
            self.page.locator("#download-svg").click()
        download = download_info.value
        self.assertEqual(download.suggested_filename, "natal-chart-1985-07-14.svg")
        target = ARTIFACTS / "reference-chart.svg"
        download.save_as(target)
        self.page.goto(target.as_uri())
        fill = self.page.locator(".wheel-orbit").first.evaluate("el => getComputedStyle(el).fill")
        stroke = self.page.locator(".wheel-house").first.evaluate("el => getComputedStyle(el).stroke")
        self.assertEqual(fill, "none")
        self.assertNotEqual(stroke, "none")
        self.assertEqual(stroke, displayed_stroke)
        self.assertIn('40.712', self.page.locator('svg').text_content())

    def test_mobile_layout_and_safe_optional_name(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.locator("#name").fill('<img src=x onerror="alert(1)">')
        expect(self.page.locator("#result-title img")).to_have_count(0)
        self.assertEqual(self.page.evaluate("document.documentElement.scrollWidth"), 390)
        self.assertEqual(self.errors, [])
        self.page.locator("#name").fill("")
        self.page.screenshot(path=str(ARTIFACTS / "mobile.png"), full_page=True)

    def test_markdown_copy_contains_current_chart_and_never_posts_to_chatgpt(self):
        # Isolate the OS clipboard boundary; exercise the real click + serializer.
        self.page.evaluate("""Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:async text => { window.copiedMarkdown = text; }}})""")
        requests = []
        self.page.on('request', lambda request: requests.append(request.url))
        self.page.locator('#copy-markdown').click()
        expect(self.page.locator('#message')).to_contain_text('복사했습니다')
        copied = self.page.evaluate('window.copiedMarkdown')
        self.assertIn('게 22°31′39″', copied)
        self.assertIn('쌍둥이 17°56′56″', copied)
        self.assertIn('재계산하거나 임의로 보정하지', copied)
        self.assertFalse(any('chatgpt.com' in url for url in requests))

    def test_markdown_copy_is_disabled_when_input_changes_or_calculation_fails(self):
        expect(self.page.locator('#copy-markdown')).to_be_enabled()
        self.page.locator('#date').fill('2023-03-12')
        expect(self.page.locator('#copy-markdown')).to_be_disabled()
        expect(self.page.locator('#preview-markdown')).to_be_disabled()
        self.page.locator('#time').fill('02:30:00')
        self.calculate()
        expect(self.page.locator('#message')).to_contain_text('NONEXISTENT_LOCAL_TIME')
        expect(self.page.locator('#copy-markdown')).to_be_disabled()

    def test_denied_clipboard_opens_selectable_markdown_and_download(self):
        self.page.evaluate("""Object.defineProperty(navigator, 'clipboard', {configurable:true, value:{writeText:async () => { throw new DOMException('denied','NotAllowedError'); }}})""")
        self.page.locator('#copy-markdown').click()
        expect(self.page.locator('#markdown-dialog')).to_be_visible()
        self.assertIn('04°52′28″', self.page.locator('#markdown-content').input_value())
        expect(self.page.locator('#message')).not_to_contain_text('복사했습니다')
        self.page.locator('#markdown-select-all').click()
        selection = self.page.locator('#markdown-content').evaluate('(el) => [el.selectionStart, el.selectionEnd, el.value.length]')
        self.assertEqual(selection, [0, selection[2], selection[2]])
        with self.page.expect_download() as event:
            self.page.locator('#download-markdown').click()
        target = ARTIFACTS / 'interpretation.md'
        event.value.save_as(target)
        self.assertIn('1985-07-15T01:45:00Z', target.read_text())
        self.assertEqual(event.value.suggested_filename, 'natal-interpretation-1985-07-14.md')
        self.assertEqual(self.page.locator('#open-chatgpt').get_attribute('href'), 'https://chatgpt.com/')

    def test_markdown_preview_uses_new_calculation_after_edit(self):
        self.page.locator('#date').fill('1985-07-15')
        self.calculate()
        expect(self.page.locator('#preview-markdown')).to_be_enabled()
        self.page.locator('#preview-markdown').click()
        text = self.page.locator('#markdown-content').input_value()
        self.assertIn('1985-07-16T01:45:00Z', text)
        self.assertNotIn('쌍둥이 17°56′56″', text)
        self.page.keyboard.press('Escape')
        expect(self.page.locator('#markdown-dialog')).not_to_be_visible()


if __name__ == "__main__":
    unittest.main(verbosity=2)
