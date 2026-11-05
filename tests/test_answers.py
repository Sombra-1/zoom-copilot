import json
import unittest

from copilot_core.answer_renderer import answer_blocks
from copilot_core.answer_schema import ANSWER_JSON_SCHEMA, Answer, parse_answer


class AnswerTests(unittest.TestCase):
    def test_all_answer_types_validate(self):
        for kind in ANSWER_JSON_SCHEMA["properties"]["type"]["enum"]:
            answer = parse_answer(json.dumps({"type": kind, "summary": "Summary"}))
            self.assertTrue(answer.structured)
            self.assertEqual(answer.type, kind)

    def test_bad_shapes_fall_back_without_crashing(self):
        for raw in ("{broken", "null", "[]", '{"type":"unknown"}',
                    '{"type":"math","steps":[{}]}', '{"type":"math","code":42}',
                    '{"type":"math","steps":{}}', '{"type":"math","summary":null}'):
            with self.subTest(raw=raw):
                self.assertFalse(parse_answer(raw).structured)

    def test_fenced_json_and_unknown_fields(self):
        answer = parse_answer('```json\n{"type":"definition","summary":"Term","unexpected":"ignored"}\n```')
        self.assertEqual(answer.summary, "Term")
        self.assertFalse(hasattr(answer, "unexpected"))

    def test_bounds(self):
        answer = parse_answer(json.dumps({"type": "answer", "title": "x" * 500, "summary": "s" * 20000}))
        self.assertEqual(len(answer.title), 160)
        self.assertEqual(len(answer.summary), 16000)
        self.assertLessEqual(len(parse_answer("x" * 100000).content), 64000)

    def test_math_disclosure_keeps_final_and_hides_steps(self):
        answer = Answer(type="math", summary="x = 6", latex=r"\boxed{x=6}",
                        steps=(r"2x+5=17", r"2x=12", r"x=6"))
        compact, detailed = answer_blocks(answer), answer_blocks(answer, "detailed")
        self.assertIn(("math", r"\boxed{x=6}"), compact)
        self.assertNotIn(("math", r"2x=12"), compact)
        self.assertIn(("math", r"2x=12"), detailed)
        self.assertIn("$$", answer.markdown())

    def test_debugging_has_code_cause_and_fix(self):
        answer = Answer(type="debugging", summary="Null user", cause="user may be None",
                        fix="Guard access", language="python", code="if user is None:\n    return")
        blocks = answer_blocks(answer, "normal")
        self.assertIn(("heading", "Cause"), blocks)
        self.assertIn(("code:python", answer.code), blocks)
        self.assertIn("```python", answer.markdown())

    def test_presentation_stays_readable_in_compact_mode(self):
        blocks = answer_blocks(Answer(type="presentation", bullets=("First point", "Second point"),
                                      next_sentence="Next, consider the diagram."))
        self.assertEqual(sum(kind == "bullet" for kind, _ in blocks), 2)
        self.assertIn(("text", "Next, consider the diagram."), blocks)
