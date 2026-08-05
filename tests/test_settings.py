import unittest

import zoom_copilot as copilot


class SettingsTests(unittest.TestCase):
    def test_deprecated_fast_groq_model_is_migrated(self):
        settings = copilot._coerce_settings({
            "groq_model": "llama-3.1-8b-instant",
        })
        self.assertEqual(settings["groq_model"], "openai/gpt-oss-20b")

    def test_deprecated_large_groq_model_is_migrated(self):
        settings = copilot._coerce_settings({
            "groq_model": "llama-3.3-70b-versatile",
        })
        self.assertEqual(settings["groq_model"], "openai/gpt-oss-120b")

    def test_numeric_settings_are_clamped(self):
        settings = copilot._coerce_settings({
            "chunk_seconds": 999,
            "screen_interval": 1,
            "opacity": 0,
        })
        self.assertEqual(settings["chunk_seconds"], 30)
        self.assertEqual(settings["screen_interval"], 3)
        self.assertEqual(settings["opacity"], 0.3)


if __name__ == "__main__":
    unittest.main()
