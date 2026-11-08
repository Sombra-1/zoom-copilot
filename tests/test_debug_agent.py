import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copilot_core.debug_agent import DebugAgent, redact


class DebugAgentTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.root = Path(self.folder.name)
        self.path = self.root / "zoom_copilot.py"
        self.path.write_bytes(b"value = 1\n")
        self.agent = DebugAgent(self.root, enabled=True)

    def tearDown(self):
        self.folder.cleanup()

    def test_opt_in_and_path_boundaries(self):
        with self.assertRaises(PermissionError):
            DebugAgent(self.root)
        (self.root / ".copilot_settings.json").write_text('{"secret":"token"}')
        for path in (".copilot_settings.json", "../outside.py", "work/private.py"):
            with self.subTest(path=path), self.assertRaises((PermissionError, FileNotFoundError)):
                self.agent.source_path(path)

    def test_proposal_does_not_modify_source(self):
        proposal = self.agent.propose("zoom_copilot.py", "value = 2\n", "Fix")
        self.assertIn("-value = 1", proposal.diff)
        self.assertEqual(self.path.read_text(), "value = 1\n")
        with self.assertRaises(PermissionError):
            self.agent.approve(proposal)

    def test_approved_patch_runs_tests(self):
        proposal = self.agent.propose("zoom_copilot.py", "value = 2\n")
        (self.root / ".copilot_settings.json").write_text('{"secret":"token"}')
        def check_candidate(name, candidate):
            self.assertEqual(name, "tests")
            self.assertEqual(self.path.read_bytes(), b"value = 1\n")
            self.assertEqual((candidate / self.path.name).read_bytes(), b"value = 2\n")
            self.assertFalse((candidate / ".copilot_settings.json").exists())
            return 0, "Tests OK"
        with mock.patch.object(self.agent, "_check", side_effect=check_candidate):
            self.assertEqual(self.agent.approve(proposal, approved=True)[0], 0)
        self.assertEqual(self.path.read_text(), "value = 2\n")

    def test_failing_candidate_leaves_original_bytes_on_disk(self):
        tests = self.root / "tests"
        tests.mkdir()
        (tests / "__init__.py").touch()
        (tests / "test_value.py").write_text(
            "import unittest\nimport zoom_copilot\n\n"
            "class ValueTest(unittest.TestCase):\n"
            "    def test_value(self):\n"
            "        self.assertEqual(zoom_copilot.value, 1)\n", encoding="utf-8"
        )
        proposal = self.agent.propose("zoom_copilot.py", "value = 2\n")
        code, output = self.agent.approve(proposal, approved=True)
        self.assertNotEqual(code, 0)
        self.assertIn("2 != 1", output)
        self.assertEqual(self.path.read_bytes(), b"value = 1\n")

    def test_concurrent_edit_during_candidate_test_is_preserved(self):
        proposal = self.agent.propose("zoom_copilot.py", "value = 2\n")
        def concurrent_edit(_name, _candidate):
            self.path.write_bytes(b"value = 3\n")
            return 0, "Tests OK"
        with mock.patch.object(self.agent, "_check", side_effect=concurrent_edit):
            with self.assertRaisesRegex(RuntimeError, "changed since review"):
                self.agent.approve(proposal, approved=True)
        self.assertEqual(self.path.read_bytes(), b"value = 3\n")

    def test_stale_patch_and_invalid_python_are_rejected(self):
        proposal = self.agent.propose("zoom_copilot.py", "value = 2\n")
        self.path.write_text("value = 3\n")
        with self.assertRaisesRegex(RuntimeError, "changed since review"):
            self.agent.approve(proposal, approved=True)
        with self.assertRaises(SyntaxError):
            self.agent.propose("zoom_copilot.py", "def broken(")

    def test_model_cannot_select_shell_commands(self):
        with self.assertRaises(PermissionError):
            self.agent.check("powershell arbitrary-command")

    def test_exact_unique_fragment_required(self):
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        proposal = self.agent.propose_change("zoom_copilot.py", "value = 1", "value = 2", "Fix", digest)
        self.assertEqual(proposal.replacement, "value = 2\n")
        with self.assertRaises(ValueError):
            self.agent.propose_change("zoom_copilot.py", "absent", "value = 2", "Fix", digest)
        with self.assertRaises(RuntimeError):
            self.agent.propose_change("zoom_copilot.py", "value = 1", "value = 2", "Fix", "old-hash")

    def test_redaction_of_tokens_and_images(self):
        result = redact("Authorization: Bearer secret-token api_key=sk-abcdefghijklmnop "
                        "refresh_token=secret data:image/png;base64,QUJDRA==")
        self.assertNotIn("secret-token", result)
        self.assertNotIn("sk-", result)
        self.assertNotIn("QUJDRA", result)
