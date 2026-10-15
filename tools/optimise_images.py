#!/usr/bin/env python3
"""Turn the originals in photos/ into web-sized WebP files in assets/img/.

  python3 tools/optimise_images.py

What it does
  * Any photo called fuji-*.jpg/.png  -> assets/img/photography/<name>.webp
    (max 1800 px wide, under ~250 KB) and the gallery in index.html is rewritten.
  * Any other photo (e.g. rocket-motor.jpg) -> assets/img/<name>.webp
    The project cards look for rocket-motor.webp, openvsp-model.webp and
    cavity-flow.webp automatically.
Your originals in photos/ are never changed.
Needs:  pip install pillow
"""
import html
import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC, IMG = ROOT / "photos", ROOT / "assets" / "img"
GALLERY = IMG / "photography"
EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
LIMIT = 250 * 1024


def save(path: Path, out: Path, max_w: int):
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    while True:
        for q in (82, 76, 70, 64, 58, 50):
            im.save(out, "WEBP", quality=q, method=6)
            if out.stat().st_size <= LIMIT:
                break
        # still too big? shrink the picture a little and try again (never below 1000 px wide)
        if out.stat().st_size <= LIMIT or im.width <= 1000:
            break
        im = im.resize((round(im.width * 0.85), round(im.height * 0.85)), Image.LANCZOS)
    print(f"  {path.name} -> {out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB, {im.width}x{im.height})")
    return im.size


def main():
    files = sorted(p for p in SRC.iterdir() if p.suffix.lower() in EXT) if SRC.exists() else []
    if not files:
        print("No photos in photos/ yet. Add some and run this again.")
        return
    IMG.mkdir(parents=True, exist_ok=True)
    GALLERY.mkdir(parents=True, exist_ok=True)
    tiles = []
    for p in files:
        if p.stem.lower().startswith("fuji-"):
            w, h = save(p, GALLERY / (p.stem + ".webp"), 1800)
            alt = html.escape(p.stem.replace("-", " ").replace("_", " ").title())
            tiles.append(
                f'          <figure class="tile"><button type="button" aria-label="Open photo: {alt}">'
                f'<img src="assets/img/photography/{p.stem}.webp" alt="{alt}" width="{w}" height="{h}" loading="lazy">'
                f"</button></figure>"
            )
        else:
            save(p, IMG / (p.stem + ".webp"), 1600)
    if tiles:
        page = ROOT / "index.html"
        text = page.read_text(encoding="utf-8")
        block = '<!-- GALLERY:START (rewritten by tools/optimise_images.py) -->\n        <div class="gallery" id="gallery">\n' \
                + "\n".join(tiles) + '\n        </div>\n        <!-- GALLERY:END -->'
        new = re.sub(r"<!-- GALLERY:START.*?<!-- GALLERY:END -->", lambda m: block, text, flags=re.S)
        page.write_text(new, encoding="utf-8")
        print(f"Gallery updated with {len(tiles)} photo(s).")


if __name__ == "__main__":
    main()
