"""Draw the preview's static isometric signal at high resolution."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SIZE = (420, 216)
SCALE = 3
ROOT = Path(__file__).resolve().parents[1]


def xy(points):
    return [(round(x * SCALE), round(y * SCALE)) for x, y in points]


def face(image, points, top, bottom):
    """Mask a vertical material gradient to one visible face."""
    points = xy(points)
    mask = Image.new("L", image.size)
    ImageDraw.Draw(mask).polygon(points, fill=255)
    bounds = mask.getbbox()
    if not bounds:
        return
    height = bounds[3] - bounds[1]
    surface = Image.new("RGBA", (1, height))
    surface.putdata([tuple(round(a + (b - a) * y / max(1, height - 1)) for a, b in zip(top, bottom)) + (255,)
                     for y in range(height)])
    image.paste(surface.resize((bounds[2] - bounds[0], height)), bounds[:2], mask.crop(bounds))


def main():
    dimensions = tuple(side * SCALE for side in SIZE)
    art = Image.new("RGBA", dimensions)
    glow = Image.new("RGBA", dimensions)
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(xy([(62, 63), (393, 197)]), fill=(79, 105, 240, 115))
    glow_draw.ellipse(xy([(210, 41), (375, 123)]), fill=(89, 214, 237, 74))
    art.alpha_composite(glow.filter(ImageFilter.GaussianBlur(24 * SCALE)))
    grid = ImageDraw.Draw(art)
    for y in (138, 149, 160, 171, 182):
        grid.line(xy([(55, y + 12), (376, y - 17)]), fill=(107, 139, 237, 67), width=SCALE)
    for x in range(70, 365, 34):
        grid.line(xy([(x, 177), (x + 45, 122)]), fill=(107, 139, 237, 62), width=SCALE)
    heights = (20, 39, 64, 91, 118, 79, 104, 57, 30)
    for index, height in enumerate(heights):
        x = 74 + index * 29
        y = 174 - index * 4
        top = y - height
        front = [(x, top), (x + 18, top + 5), (x + 18, y + 5), (x, y)]
        side = [(x + 18, top + 5), (x + 30, top - 2), (x + 30, y - 2), (x + 18, y + 5)]
        roof = [(x, top), (x + 12, top - 7), (x + 30, top - 2), (x + 18, top + 5)]
        face(art, front, (157, 187, 255), (72, 79, 198))
        face(art, side, (105, 131, 242), (36, 48, 130))
        face(art, roof, (214, 245, 255), (145, 181, 255))
        pen = ImageDraw.Draw(art)
        pen.line(xy([front[0], front[1], front[2]]), fill=(185, 208, 255, 205), width=SCALE)
        pen.line(xy([roof[0], roof[1], roof[2]]), fill=(229, 250, 255, 205), width=SCALE)
    dots = ImageDraw.Draw(art)
    for x, y, size in ((72, 57, 2), (340, 49, 2), (370, 94, 2), (170, 41, 1), (313, 31, 1)):
        dots.ellipse(xy([(x - size, y - size), (x + size, y + size)]), fill=(174, 216, 255, 208))
    art.resize(SIZE, Image.Resampling.LANCZOS).save(ROOT / "assets" / "signal-depth.png", optimize=True)


if __name__ == "__main__":
    main()
