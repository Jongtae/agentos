import unittest
from personal_agent.local_tools import LocalTools, weather_answer


WEATHER = {'tool': 'weather', 'location': {'name': 'Seongnam-si', 'admin1': 'Gyeonggi-do', 'country': 'South Korea'},
           'forecast': {'timezone': 'Asia/Seoul',
                        'current': {'time': '2026-09-26T10:00', 'temperature_2m': 21.0, 'apparent_temperature': 20.5,
                                    'precipitation': 0.0, 'wind_speed_10m': 5.2},
                        'current_units': {'temperature_2m': '°C', 'apparent_temperature': '°C',
                                          'precipitation': 'mm', 'wind_speed_10m': 'km/h'},
                        'daily': {'time': ['2026-09-26', '2026-09-27', '2026-09-28'],
                                  'temperature_2m_min': [15.0, 14.1, 13.0], 'temperature_2m_max': [24.0, 22.3, 21.0],
                                  'precipitation_probability_max': [10, 70, 20]},
                        'daily_units': {'temperature_2m_min': '°C', 'temperature_2m_max': '°C',
                                        'precipitation_probability_max': '%'}},
           'sources': ['https://api.open-meteo.com/v1/forecast?x', 'https://open-meteo.com/']}


class LocalToolTests(unittest.TestCase):
    def test_unknown_tool_rejected(self):
        with self.assertRaises(ValueError):LocalTools().execute({'tool':'shell','command':'bad'})

    def test_dead_duplicate_loops_are_removed(self):
        # #606 T7: the native loop in agent_runtime is the only tool loop.
        import personal_agent.local_tools as module
        for name in ('run_native_tools','weather_context','ASK_LOCATION','TOOL_DEFINITIONS','TOOL_ROUTING','needs_lookup'):
            self.assertFalse(hasattr(module,name),name)
        self.assertFalse(hasattr(LocalTools,'answer'))

    def test_weather_rendering_shows_dated_forecast_rows_with_timezone(self):
        # #606 T6: "tomorrow" is answered from a dated row, not the current reading.
        text = weather_answer(WEATHER)
        self.assertIn('기준 시각: 2026-09-26T10:00 (Asia/Seoul)', text)
        self.assertIn('예보 (Asia/Seoul 기준 날짜):', text)
        self.assertIn('- 2026-09-27: 최저 14.1 °C / 최고 22.3 °C, 강수 확률 70%', text)

    def test_weather_rendering_without_daily_rows_still_renders_current(self):
        forecast = {k: v for k, v in WEATHER['forecast'].items() if k not in ('daily', 'daily_units')}
        text = weather_answer({**WEATHER, 'forecast': forecast})
        self.assertIn('기온: 21.0 °C', text)
        self.assertNotIn('예보 (', text)


if __name__=='__main__':unittest.main()
