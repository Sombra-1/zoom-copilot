"""Opt-in tests of the real offline KaTeX/browser rendering dependency."""
import io
import os
import unittest

from copilot_core.math_renderer import MathRenderer


@unittest.skipUnless(os.environ.get("COPILOT_RENDER_TESTS") == "1",
                     "Set COPILOT_RENDER_TESTS=1 with Playwright and Edge/Chromium installed")
class MathIntegrationTests(unittest.TestCase):
    def test_real_math_renderer_supports_required_notation(self):
        from PIL import Image
        renderer = MathRenderer()
        equations = [r"\frac{1}{2} + x^2 + \sqrt{x}", r"\int_0^2 (3x^2+2x)\,dx = \boxed{12}",
                     r"\frac{d}{dx}x^2=2x", r"\lim_{x\to0}\frac{\sin x}{x}=1",
                     r"\sum_{i=1}^{n}i", r"\begin{bmatrix}1&2\\3&4\end{bmatrix}",
                     r"\vec{v}=\alpha\hat{i}+\beta\hat{j}",
                     r"\begin{cases}x+y=2\\x-y=0\end{cases}",
                     r"\begin{aligned}2x+5&=17\\2x&=12\\x&=6\end{aligned}"]
        try:
            images = renderer.render(equations, 22, 500)
            self.assertEqual(len(images), len(equations))
            for equation, image in zip(equations, images):
                with self.subTest(equation=equation):
                    self.assertTrue(image)
                    self.assertGreater(Image.open(io.BytesIO(image)).height, 20)
            self.assertEqual(renderer.render(equations, 22, 500), images)
        finally:
            renderer.close()
