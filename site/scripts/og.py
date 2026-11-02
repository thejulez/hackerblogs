"""Open Graph image (1200x630) with the current blog count: python3 scripts/og.py, run by pnpm data."""

import json

from PIL import Image, ImageDraw, ImageFont

n = len(json.load(open("src/data/blogs.json")))
W, H = 1200, 630
bg, fg, mut, acc = (251, 250, 247), (29, 28, 26), (107, 103, 96), (232, 89, 12)
im = Image.new("RGB", (W, H), bg)
d = ImageDraw.Draw(im)
F = "/System/Library/Fonts/HelveticaNeue.ttc"
bold = lambda s: ImageFont.truetype(F, s, index=1)
reg = lambda s: ImageFont.truetype(F, s, index=0)
# logo: rounded square with the rss mark
x, y, s = 80, 92, 64
d.rounded_rectangle([x, y, x + s, y + s], radius=15, fill=acc)
cx, cy = x + 18, y + s - 18
d.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill="white")
for r in (20, 34):
    d.arc([cx - r, cy - r, cx + r, cy + r], 270, 360, fill="white", width=7)
d.text((x + s + 22, y + 4), "Hacker Blogs", font=bold(50), fill=acc)
d.text((80, 215), "The blogs Hacker News", font=bold(76), fill=fg)
d.text((80, 305), "keeps linking to.", font=bold(76), fill=fg)
d.text((80, 430), f"{n:,} personal and company blogs, ranked by how many", font=reg(34), fill=mut)
d.text((80, 476), "people linked them. Every HN comment, every feed.", font=reg(34), fill=mut)
d.text((80, 548), "hackerblogs.org", font=bold(30), fill=fg)
d.rectangle([0, H - 14, W, H], fill=acc)
im.save("public/og.png", optimize=True)
