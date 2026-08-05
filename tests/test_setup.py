import unittest

import setup


class SetupTests(unittest.TestCase):
    def test_offline_and_cloud_only_dependencies_do_not_block_local_launch(self):
        results = {
            "python": True,
            "internet": False,
            "sounddevice": True,
            "numpy": True,
            "requests": False,
            "mss": None,
            "PIL": None,
            "pystray": None,
            "vbcable": False,
        }
        self.assertEqual(setup.blocking_checks(results), {})

    def test_missing_audio_dependency_blocks_launch(self):
        results = {
            "python": True,
            "internet": False,
            "sounddevice": False,
            "numpy": True,
        }
        self.assertEqual(set(setup.blocking_checks(results)), {"sounddevice"})


if __name__ == "__main__":
    unittest.main()
