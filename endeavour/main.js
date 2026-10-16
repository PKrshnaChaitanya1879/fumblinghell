// Endeavour — site behaviour. No libraries.
(() => {
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

  /* ---------- boot sequence (plays once per visit) ---------- */
  const boot = $("#boot");
  let seen = false;
  try { seen = sessionStorage.getItem("endeavour-booted") === "1"; } catch (e) { /* storage blocked: just play it */ }
  const finishBoot = () => {
    boot.classList.add("is-done");
    document.body.classList.remove("is-booting");
    try { sessionStorage.setItem("endeavour-booted", "1"); } catch (e) {}
  };
  if (seen || reduce) {
    finishBoot();
  } else {
    const lines = $$("#bootLines li");
    const fill = $("#bootFill");
    lines.forEach((li, i) => setTimeout(() => {
      li.classList.add("is-on");
      fill.style.width = ((i + 1) / lines.length * 100) + "%";
    }, 180 + i * 230));
    const t = setTimeout(finishBoot, 180 + lines.length * 230 + 650);
    $("#bootSkip").addEventListener("click", () => { clearTimeout(t); finishBoot(); });
  }

  /* ---------- mobile menu ---------- */
  const toggle = $("#navToggle"), menu = $("#mobileMenu");
  toggle.addEventListener("click", () => {
    const open = menu.hidden;
    menu.hidden = !open;
    toggle.setAttribute("aria-expanded", String(open));
    toggle.textContent = open ? "Close" : "Menu";
  });
  $$("#mobileMenu a").forEach(a => a.addEventListener("click", () => { menu.hidden = true; toggle.setAttribute("aria-expanded", "false"); toggle.textContent = "Menu"; }));

  /* ---------- hero HUD: running clock + cursor coordinates ---------- */
  const clock = $("#clock");
  let secs = 23 * 3600 + 41 * 60 + 7;
  const pad = n => String(n).padStart(2, "0");
  setInterval(() => {
    secs = (secs + 1) % 86400;
    clock.textContent = `${pad(Math.floor(secs / 3600))}:${pad(Math.floor(secs / 60) % 60)}:${pad(secs % 60)}`;
  }, 1000);
  const hero = $("#hero"), xy = $("#hudXY");
  hero.addEventListener("pointermove", e => {
    const r = hero.getBoundingClientRect();
    const x = Math.round((e.clientX - r.left) / r.width * 1920), y = Math.round((e.clientY - r.top) / r.height * 936);
    xy.textContent = `X:${String(x).padStart(4, "0")}PX  Y:${String(y).padStart(4, "0")}PX`;
  });

  /* ---------- deck plan ---------- */
  const rooms = {
    casino:      ["casino-hall.jpg",      "D7 · 01 · 29.7 × 19.8 M", "Casino hall",        "Emerald wallpaper, gold rails, chandeliers twice the height of a person. 125 props, all placed by script."],
    corridor:    ["private-corridor.jpg", "D7 · 02 · 3.0 × 16.0 M",  "Private corridor",   "Champagne wallpaper and a red runner. Guests aren't meant to come this way. The waiter does."],
    meeting:     ["hero-kill.jpg",        "D7 · 03 · 10.0 × 9.0 M",  "Meeting room 7-C",   "A board meeting with the door sealed. Vent 4B has a clear view of the table."],
    lounge:      ["starlight-lounge.jpg", "D7 · 04 · LOUNGE",        "Starlight lounge",   "Red velvet, a gold bar and a compass rose set into the floor. (Blender render of the set.)"],
    service:     ["service-passage.jpg",  "D7 · 05 · 3.8 × 13.5 M",  "Service passage",    "Crew lockers and laundry carts. The service hatch opens for crew during a lockdown."],
    cargo:       ["cargo-bay.jpg",        "D7 · 06 · 17.8 × 21.8 M", "Cargo bay 2",        "Freight crates stacked into a maze. The botanical crates at the back are warm to the touch."],
    lab:         ["veyra-wing.jpg",       "D7 · 07 · 11.8 × 15.8 M", "Veyra wing",         "Specimen tanks glowing pink, and crates that float when nobody touches them."],
    engineering: ["engineering.jpg",      "D7 · 08 · 15.8 × 13.8 M", "Engineering",        "Generators, pipe runs, and the console Mira knows by heart."],
    obs:         ["observation-deck.jpg", "D7 · 09 · 21.8 × 19.8 M", "Observation deck",   "The big window. Whatever the ship is flying towards, you can see it from here."]
  };
  const img = $("#roomImg"), coord = $("#roomCoord"), name = $("#roomName"), text = $("#roomText");
  const pick = g => {
    const d = rooms[g.dataset.room]; if (!d) return;
    $$(".room").forEach(r => r.classList.toggle("is-active", r === g));
    img.classList.add("is-swapping");
    const next = new Image(); next.src = "img/" + d[0];
    next.onload = () => { img.src = next.src; img.alt = d[2]; img.classList.remove("is-swapping"); };
    coord.textContent = d[1]; name.textContent = d[2]; text.textContent = d[3];
  };
  $$(".room").forEach(g => {
    g.addEventListener("click", () => pick(g));
    g.addEventListener("mouseenter", () => { if (window.matchMedia("(hover: hover)").matches) pick(g); });
    g.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(g); } });
  });
  pick($('.room[data-room="casino"]'));

  /* ---------- before / after ---------- */
  const cmp = $("#compare"), range = $(".compare__range", cmp);
  range.addEventListener("input", () => cmp.style.setProperty("--pos", range.value + "%"));

  /* ---------- key art: fall back to in-game shots until the Grok stills are added ---------- */
  const cap = $("#keyartCap");
  $$(".keyart img").forEach(im => {
    const fail = () => { if (im.dataset.fallback && !im.src.endsWith(im.dataset.fallback)) { im.src = im.dataset.fallback; cap.textContent = cap.dataset.fallback; } };
    im.addEventListener("error", fail);
    if (im.complete && im.naturalWidth === 0) fail();
  });

  /* ---------- reveal on scroll ---------- */
  const targets = $$(".section__head, .beat, .file, .deck, .powers li, .rules li, .pipe li, .stats div, .fails li, .manifesto__text, .part > *, .compare, .closing__copy");
  if (!reduce && "IntersectionObserver" in window) {
    targets.forEach(t => t.classList.add("reveal"));
    const io = new IntersectionObserver(es => es.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add("is-in"); io.unobserve(e.target); }
    }), { rootMargin: "0px 0px -8% 0px" });
    targets.forEach((t, i) => { t.style.transitionDelay = (i % 5) * 60 + "ms"; io.observe(t); });
  }
})();
