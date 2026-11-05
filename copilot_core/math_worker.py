"""Internal offline renderer; model input is only an argument to KaTeX.render."""
import base64
import json
import os
import re
import sys
from pathlib import Path


def render(payload):
    from playwright.sync_api import sync_playwright
    vendor = Path(__file__).parent / "vendor" / "katex"
    css = (vendor / "katex.min.css").read_text(encoding="utf-8")
    def font(match):
        name = match.group(1).strip('"\'')
        path = vendor / name
        if path.suffix == ".woff2" and path.is_file():
            return "url(data:font/woff2;base64," + base64.b64encode(path.read_bytes()).decode() + ")"
        return "url(data:,)"
    css = re.sub(r"url\(([^)]+)\)", font, css)
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, channel="msedge" if os.name == "nt" else None,
                                               chromium_sandbox=True, timeout=12000)
        try:
            context = browser.new_context(offline=True, service_workers="block", viewport={"width": 1000, "height": 2000})
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_default_timeout(5000)
            page.set_content('<!doctype html><meta http-equiv="Content-Security-Policy" '
                             'content="default-src \'none\'; script-src \'unsafe-inline\'; '
                             'style-src \'unsafe-inline\'; font-src data:; img-src data:; connect-src \'none\'">'
                             '<style>body{margin:0;background:#191b20;color:#f1f2f6}'
                             '#equation{display:inline-block;padding:10px;text-align:left}'
                             '.katex-display{margin:0;text-align:left}</style><div id="equation"></div>')
            page.add_style_tag(content=css)
            page.add_script_tag(content=(vendor / "katex.min.js").read_text(encoding="utf-8"))
            font_size = max(12, min(36, int(payload.get("font", 18))))
            width = max(200, min(900, int(payload.get("width", 440))))
            for equation in payload.get("equations", [])[:60]:
                try:
                    ok = page.evaluate("""({text, size, width}) => {
                        const el = document.getElementById('equation');
                        el.style.fontSize = size + 'px';
                        try {
                            katex.render(text, el, {displayMode:true, throwOnError:true,
                                trust:false, maxExpand:500, maxSize:20, strict:'warn'});
                            const box = el.getBoundingClientRect();
                            if (box.width > width) el.style.fontSize = Math.max(10,size*width/box.width) + 'px';
                            return el.clientWidth <= 1000 && el.clientHeight <= 1800;
                        } catch (_) { el.textContent = ''; return false; }
                    }""", {"text": str(equation)[:4000], "size": font_size, "width": width})
                    if not ok:
                        results.append(None)
                        continue
                    page.evaluate("document.fonts.ready")
                    data = page.locator("#equation").screenshot(timeout=5000)
                    results.append(base64.b64encode(data).decode())
                except Exception:
                    results.append(None)
            context.close()
        finally:
            browser.close()
    return results


if __name__ == "__main__":
    try:
        payload = json.loads(sys.stdin.read(260000))
        sys.stdout.write(json.dumps(render(payload)))
    except Exception:
        sys.exit(1)
