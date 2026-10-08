#!/usr/bin/env python3
"""Crop the owner-supplied Telegram screenshots into the README AI-switch figure (#1193).

Usage: build.py <source-screenshot-dir> docs/assets/readme/ai-switch
"""
import hashlib, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SRC = Path(sys.argv[1]); OUT = Path(sys.argv[2])
# (source file, [crop boxes]) per panel, in conversation order.
PANELS = [
    ("461b29dc-image.png", [(0, 222, 706, 1220)]),                      # 10:01 switch to Claude Code + question
    ("183d5629-image.png", [(0, 458, 706, 560), (0, 1020, 706, 1332)]), # 10:02-10:06 sign-in resume + cart answer (sign-in link omitted)
    ("d5f26819-image.png", [(0, 390, 706, 1220)]),                      # 10:07 switch to Codex + remove
]
M, GAP, SEG_GAP, R, CIRCLE = 24, 36, 18, 28, 60
panels = []
for name, boxes in PANELS:
    im = Image.open(SRC / name).convert("RGB")
    parts = [im.crop(b) for b in boxes]
    h = sum(p.height for p in parts) + SEG_GAP * (len(parts) - 1)
    p = Image.new("RGBA", (706, h), (0, 0, 0, 0)); y = 0
    for part in parts:
        mask = Image.new("L", part.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, part.width - 1, part.height - 1), R, fill=255)
        p.paste(part, (0, y), mask); y += part.height + SEG_GAP
    panels.append(p)
W = 2 * M + sum(p.width for p in panels) + GAP * (len(panels) - 1)
H = 2 * M + CIRCLE + 20 + max(p.height for p in panels)
canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(canvas)
font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 36)
x = M
for i, p in enumerate(panels, 1):
    cx = x + p.width // 2
    d.ellipse((cx - CIRCLE // 2, M, cx + CIRCLE // 2, M + CIRCLE), fill=(37, 99, 235, 255))
    d.text((cx, M + CIRCLE // 2), str(i), font=font, fill="white", anchor="mm")
    canvas.alpha_composite(p, (x, M + CIRCLE + 20)); x += p.width + GAP
scale = 0.8
canvas = canvas.resize((round(W * scale), round(H * scale)), Image.LANCZOS)
canvas.save(OUT / "ai-switch-conversation.png", optimize=True)
manifest = {
    "issue": 1193,
    "evidence_class": "owner-supplied Telegram screenshots of one real session (2026-10-08, 10:01-10:08 PM); not release-specific end-to-end validation",
    "output": "ai-switch-conversation.png",
    "output_sha256": hashlib.sha256((OUT / "ai-switch-conversation.png").read_bytes()).hexdigest(),
    "scale": scale,
    "panels": [
        {"source_sha256": hashlib.sha256((SRC / n).read_bytes()).hexdigest(), "source_size": [706, 1536], "crop_boxes": b}
        for n, b in PANELS
    ],
    "omitted": "phone status bar, chat header and input bar; in panel 2 the one-time sign-in link and its code (between the two crops)",
}
(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
print(canvas.size, (OUT / "ai-switch-conversation.png").stat().st_size)
