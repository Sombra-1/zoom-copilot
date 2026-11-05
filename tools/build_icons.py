"""Rebuild the editable diamond mark and Windows icon (requires Pillow)."""
from pathlib import Path
from PIL import Image, ImageDraw

folder = Path(__file__).resolve().parents[1] / "assets"
folder.mkdir(exist_ok=True)
svg = """<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 256 256">
  <defs><linearGradient id="blue" x1="0" y1="0" x2="1" y2="1">
    <stop stop-color="#697fea"/><stop offset="1" stop-color="#a99af7"/>
  </linearGradient></defs>
  <rect x="8" y="8" width="240" height="240" rx="57" fill="url(#blue)"/>
  <path d="M128 51 205 128 128 205 51 128Z" fill="none" stroke="#fff" stroke-width="13" stroke-linejoin="round"/>
  <path d="M128 91 138 118 165 128 138 138 128 165 118 138 91 128 118 118Z" fill="#fff"/>
</svg>
"""
(folder / "logo.svg").write_text(svg, encoding="utf-8")
scale, size = 4, 1024
image = Image.new("RGBA", (size, size))
pixels = image.load()
start, end = (105, 127, 234), (169, 154, 247)
for y in range(size):
    for x in range(size):
        fraction = (x + y) / (2 * (size - 1))
        pixels[x, y] = tuple(round(a + (b - a) * fraction) for a, b in zip(start, end)) + (255,)
mask = Image.new("L", image.size)
ImageDraw.Draw(mask).rounded_rectangle((8*scale, 8*scale, 248*scale, 248*scale), radius=57*scale, fill=255)
image.putalpha(mask)
draw = ImageDraw.Draw(image)
diamond = [(128, 51), (205, 128), (128, 205), (51, 128), (128, 51)]
draw.line([(x*scale, y*scale) for x, y in diamond], fill="white", width=13*scale, joint="curve")
radius = 6.5 * scale
for x, y in diamond[:-1]:
    draw.ellipse((x*scale-radius, y*scale-radius, x*scale+radius, y*scale+radius), fill="white")
spark = [(128, 91), (138, 118), (165, 128), (138, 138), (128, 165), (118, 138), (91, 128), (118, 118)]
draw.polygon([(x*scale, y*scale) for x, y in spark], fill="white")
image.resize((512, 512), Image.Resampling.LANCZOS).save(folder / "logo.png")
sizes = [(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)]
image.save(folder / "app.ico", sizes=sizes)
print("Created assets/logo.svg, logo.png, app.ico")
