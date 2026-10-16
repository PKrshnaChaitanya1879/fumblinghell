# Endeavour — website

A static site: `index.html`, `styles.css`, `main.js`, `img/`, `fonts/`. No build step, no libraries.

## Look at it locally
Double-click `index.html`, or for the most accurate result run a tiny server in this folder:
`python -m http.server 8000` → open http://localhost:8000

## Put it online (free)
- **GitHub Pages:** make a repo, upload everything in this folder, then Settings → Pages → Deploy from branch → `main` / root.
- **Netlify Drop:** drag this whole folder onto app.netlify.com/drop.

## Add the Grok key art
Save the two Grok stills into `img/` with exactly these names:
- `img/keyart-voss.jpg` — Voss with the clawed shadow
- `img/keyart-iris.jpg` — Iris in her cut gown
Until they exist, the page shows in-game shots there and the caption switches automatically.

## Change text
Everything is plain text in `index.html`. Room descriptions for the deck plan are at the top of `main.js` (`rooms`).
