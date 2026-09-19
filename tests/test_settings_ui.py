import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class SettingsUiTests(unittest.TestCase):
    def test_direct_api_controls_are_primary_and_optional_choices_are_secondary(self):
        html = (ROOT / 'src/personal_agent/web/index.html').read_text(encoding='utf-8')
        self.assertIn('웹·파일 작업용 직접 API', html)
        self.assertIn('OpenAI Developer API', html)
        self.assertIn('id="advanced-model" open', html)
        self.assertIn('다른 연결 선택지 (선택)', html)

    def test_subscription_ui_exposes_active_engine_and_switch_action(self):
        script = (ROOT / 'src/personal_agent/web/app.js').read_text(encoding='utf-8')
        self.assertIn('Telegram용 구독 엔진', script)
        self.assertIn('현재 선택:', script)
        self.assertIn('으로 전환', script)


if __name__ == '__main__':
    unittest.main()
