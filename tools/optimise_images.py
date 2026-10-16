#!/usr/bin/env python3
"""Turn the originals in photos/ into web-sized WebP files in assets/img/.

  python3 tools/optimise_images.py

What it does
  * Any photo called fuji-*.jpg/.png  -> assets/img/photography/<name>.webp
    (max 1800 px wide, under ~250 KB) and the gallery in index.html is rewritten.
  * Any photo called endeavour-*.jpg/.png (game screenshots) -> assets/img/endeavour/<name>.webp
    and the gallery on endeavour.html is rewritten.
  * Same idea for jarvis-* (jarvis.html), gesture-* (gesture-control.html) and
    bio-* (bio-opener.html). Each page's Screenshots section stays hidden until it has images.
  * Any other photo (e.g. rocket-motor.jpg) -> assets/img/<name>.webp
    The project cards look for rocket-motor.webp, openvsp-model.webp and
    cavity-flow.webp automatically.
Your originals in photos/ are never changed.
Needs:  pip install pillow
"""
import html
import json
import re
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SRC, IMG = ROOT / "photos", ROOT / "assets" / "img"
EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
LIMIT = 250 * 1024
ALT_FILE = ROOT / "tools" / "alt_text.json"  # plain descriptions, one per photo name


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


# Photo-name prefix -> (page to update, folder for the optimised copies, label for the alt-text fallback)
GALLERIES = {
    "fuji-": ("index.html", IMG / "photography", "gallery"),
    "endeavour-": ("endeavour.html", IMG / "endeavour", "gallery wide"),
    "jarvis-": ("jarvis.html", IMG / "jarvis", "gallery wide"),
    "gesture-": ("gesture-control.html", IMG / "gesture", "gallery wide"),
    "bio-": ("bio-opener.html", IMG / "bio", "gallery wide"),
}


def main():
    files = sorted(p for p in SRC.iterdir() if p.suffix.lower() in EXT) if SRC.exists() else []
    if not files:
        print("No photos in photos/ yet. Add some and run this again.")
        return
    ALT = json.loads(ALT_FILE.read_text(encoding="utf-8")) if ALT_FILE.exists() else {}
    IMG.mkdir(parents=True, exist_ok=True)
    tiles = {prefix: [] for prefix in GALLERIES}
    for p in files:
        prefix = next((k for k in GALLERIES if p.stem.lower().startswith(k)), None)
        if prefix:
            _, folder, _ = GALLERIES[prefix]
            folder.mkdir(parents=True, exist_ok=True)
            w, h = save(p, folder / (p.stem + ".webp"), 1800)
            alt = html.escape(ALT.get(p.stem) or p.stem.replace("-", " ").replace("_", " ").title())
            rel = (folder / (p.stem + ".webp")).relative_to(ROOT).as_posix()
            tiles[prefix].append(
                f'          <figure class="tile"><button type="button" aria-label="Open photo: {alt}">'
                f'<img src="{rel}" alt="{alt}" width="{w}" height="{h}" loading="lazy">'
                f"</button></figure>"
            )
        else:
            save(p, IMG / (p.stem + ".webp"), 1600)
    for prefix, items in tiles.items():
        if not items:
            continue
        page = ROOT / GALLERIES[prefix][0]
        text = page.read_text(encoding="utf-8")
        block = '<!-- GALLERY:START (rewritten by tools/optimise_images.py) -->\n        <div class="' + GALLERIES[prefix][2] + '" id="gallery">\n' \
                + "\n".join(items) + '\n        </div>\n        <!-- GALLERY:END -->'
        new = re.sub(r"<!-- GALLERY:START.*?<!-- GALLERY:END -->", lambda m: block, text, flags=re.S)
        # sub pages ship with the Screenshots section hidden; show it once there are images
        new = new.replace('id="screenshots" hidden>', 'id="screenshots">')
        page.write_text(new, encoding="utf-8")
        print(f"{page.name}: gallery updated with {len(items)} photo(s).")


if __name__ == "__main__":
    main()
