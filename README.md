# My portfolio website

This is the source of my personal academic portfolio. It is a plain website made of
normal files: no frameworks, nothing to install, nothing to "build". Whatever is in
this repo is what visitors see.

## What each file and folder does

| Path | What it is |
|---|---|
| `index.html` | The whole page: every piece of text, every section. |
| `assets/css/style.css` | How it looks: colours, fonts, spacing. |
| `assets/js/main.js` | The small bits of movement: fade-in on scroll, swapping in photos, the photo viewer. |
| `assets/img/` | Optimised images used by the site (favicon, share image, project photos). |
| `assets/img/photography/` | The optimised gallery photos. |
| `photos/` | **Your originals.** Drop photos here. They are never changed. |
| `cv/cv.md` | The text of your CV. Edit this one. |
| `cv/build_cv.py` | Turns `cv.md` into the one-page PDF. |
| `cv/P_Krishna_Chaitanya_CV.pdf` | The PDF that the "Download CV" button opens. |
| `endeavour.html` | The Endeavour game sub page (screenshots, what's in it). |
| `jarvis.html`, `gesture-control.html`, `bio-opener.html` | Sub pages for the other three AI-directed builds. |
| `tools/optimise_images.py` | Shrinks photos from `photos/` and fills the gallery. |
| `.nojekyll` | Tells GitHub Pages "just serve the files as they are". Leave it. |

## Writing card and web address

* The Writing section has two essay cards (time crystals, and the first-year comedy essay). To change one, change the address, title and one-line description in the Writing section of `index.html`.

Also check the web address `pkrshnachaitanya1879.github.io` (in `index.html` meta tags and in `cv/cv.md`).
It is right only if your repository is named exactly `pkrshnachaitanya1879.github.io`.

## How to change any piece of text

1. Open `index.html`.
2. Use search (Ctrl+F / Cmd+F) for a few words of the text you want to change.
3. Edit the words **between** the `<` `>` tags. Leave the tags themselves alone.
   For example, in `<p>Hello there</p>` you may change `Hello there`, but keep `<p>` and `</p>`.
4. Save, commit, push. The site updates in about a minute.

## How to add or replace photos

**Easy way (recommended)**

1. Put your photos in the `photos/` folder.
   * Gallery photos must start with `fuji-`, for example `fuji-01.jpg`.
   * Game screenshots for the Endeavour page must start with `endeavour-`, for example `endeavour-01.png`.
   * Screenshots for the other builds start with `jarvis-`, `gesture-` or `bio-`. Each of those pages shows its Screenshots section only once it has images.
   * Project photos: `rocket-motor.jpg`, `lab-uoh.jpg` (the Research card), `openvsp-model.jpg`, `cavity-flow.jpg`.
2. (Optional) add a plain description of each photo to `tools/alt_text.json`; it becomes the photo's alt text for screen readers.
3. Run: `python3 tools/optimise_images.py` (needs `pip install pillow` once).
4. Commit and push. The grey "photo goes here" boxes are replaced automatically,
   and the gallery is rewritten with your photos.

**By hand:** save an image as `assets/img/rocket-motor.webp` (or `openvsp-model.webp`,
`cavity-flow.webp`) and the matching project box fills itself in.

## How to edit the CV and rebuild the PDF

1. Edit `cv/cv.md` (it uses simple Markdown: `##` for headings, `-` for bullets, `**bold**`, `*italic*`).
2. Run: `python3 cv/build_cv.py` (needs `pip install reportlab` once).
3. The script shrinks spacing a little if needed so the CV stays on **one A4 page**.
   If it says it cannot fit, shorten some text.
4. Commit and push both `cv.md` and the new PDF.

The phone number is intentionally not in the CV or the site. Keep it that way.

## How GitHub Pages publishes the site

GitHub Pages is a free service that serves the files in a repo as a website.
Turn it on once: **Settings -> Pages -> Build and deployment -> Deploy from a branch ->
`main` / `(root)` -> Save.** After that, every push to `main` republishes the site
(allow a minute or two). Your address will be shown at the top of that Pages settings screen.
