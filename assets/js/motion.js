/* Motion layer: kinetic type, flow-field canvas, counters, marquee,
   mask wipes, scroll-drawn timeline, tilt, magnetic buttons, cursor.
   Everything here is decoration: the page works fully without it,
   and nothing runs for visitors who ask for reduced motion. */
(function () {
  'use strict';
  var root = document.documentElement;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var finePointer = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  var hasIO = 'IntersectionObserver' in window;

  function cssVar(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
  function whenVisible(els, cb, threshold) {
    els = Array.prototype.slice.call(els);
    if (!hasIO) { els.forEach(cb); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { cb(e.target); io.unobserve(e.target); } });
    }, { threshold: threshold || 0.25 });
    els.forEach(function (el) { io.observe(el); });
  }
  function easeOutExpo(t) { return t === 1 ? 1 : 1 - Math.pow(2, -10 * t); }

  /* ---------- Flow-field canvas (hero) ---------- */
  function flowField(host) {
    var canvas = document.createElement('canvas');
    canvas.className = 'flow';
    canvas.setAttribute('aria-hidden', 'true');
    host.insertBefore(canvas, host.firstChild);
    var ctx = canvas.getContext('2d');
    if (!ctx) { return; }
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var W = 0, H = 0, parts = [], colour = '', running = false, visible = true, t = 0;
    var mouse = { x: -9999, y: -9999 };

    function readColour() { colour = cssVar('--text') || '#161614'; }
    function resize() {
      var r = host.getBoundingClientRect();
      W = Math.max(1, Math.round(r.width)); H = Math.max(1, Math.round(r.height));
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      var count = Math.min(finePointer ? 1300 : 300, Math.round(W * H / 1100));
      parts = [];
      for (var i = 0; i < count; i++) { parts.push(spawn({})); }
    }
    function spawn(p) {
      p.x = Math.random() * W; p.y = Math.random() * H;
      p.age = 0; p.life = 80 + Math.random() * 160;
      return p;
    }
    function angle(x, y) {
      var f = 0.0024;
      return (Math.sin(x * f + t) + Math.cos(y * f * 1.3 - t * 0.7) + Math.sin((x + y) * f * 0.6 + t * 0.4)) * Math.PI * 0.62;
    }
    function step() {
      t += 0.0035;
      ctx.globalCompositeOperation = 'destination-out';
      ctx.fillStyle = 'rgba(0,0,0,0.045)';
      ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over';
      ctx.strokeStyle = colour; ctx.globalAlpha = 0.26; ctx.lineWidth = 0.9;
      ctx.beginPath();
      for (var i = 0; i < parts.length; i++) {
        var p = parts[i];
        var a = angle(p.x, p.y);
        var vx = Math.cos(a) * 1.15, vy = Math.sin(a) * 1.15;
        var dx = p.x - mouse.x, dy = p.y - mouse.y, d2 = dx * dx + dy * dy, R = 170;
        if (d2 < R * R) {
          var d = Math.sqrt(d2) || 1, k = (1 - d / R) * 3.2;
          vx += (-dy / d) * k + (dx / d) * k * 0.25;
          vy += (dx / d) * k + (dy / d) * k * 0.25;
        }
        ctx.moveTo(p.x, p.y);
        p.x += vx; p.y += vy; p.age++;
        ctx.lineTo(p.x, p.y);
        if (p.age > p.life || p.x < -5 || p.x > W + 5 || p.y < -5 || p.y > H + 5) { spawn(p); }
      }
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    function loop() {
      if (!running) { return; }
      step();
      window.requestAnimationFrame(loop);
    }
    function start() { if (!running && visible && !document.hidden) { running = true; window.requestAnimationFrame(loop); } }
    function stop() { running = false; }

    readColour(); resize();
    if (reduce) { for (var n = 0; n < 140; n++) { step(); } return; } // one still frame

    window.addEventListener('resize', function () { resize(); });
    new MutationObserver(readColour).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
    if (window.matchMedia) {
      var mq = window.matchMedia('(prefers-color-scheme: dark)');
      if (mq.addEventListener) { mq.addEventListener('change', readColour); }
    }
    host.addEventListener('pointermove', function (e) {
      var r = canvas.getBoundingClientRect(); mouse.x = e.clientX - r.left; mouse.y = e.clientY - r.top;
    });
    host.addEventListener('pointerleave', function () { mouse.x = mouse.y = -9999; });
    document.addEventListener('visibilitychange', function () { if (document.hidden) { stop(); } else { start(); } });
    if (hasIO) {
      new IntersectionObserver(function (es) {
        visible = es[0].isIntersecting; if (visible) { start(); } else { stop(); }
      }).observe(host);
    }
    start();
  }

  /* ---------- Kinetic type: split into letters ---------- */
  function splitLetters(el) {
    var label = (el.innerText || el.textContent).replace(/\s+/g, ' ').trim();
    var i = 0, frag = document.createDocumentFragment();
    Array.prototype.slice.call(el.childNodes).forEach(function (node) {
      if (node.nodeType !== 3) { frag.appendChild(node.cloneNode(true)); return; }
      node.textContent.split(/(\s+)/).forEach(function (chunk) {
        if (!chunk) { return; }
        if (/^\s+$/.test(chunk)) { frag.appendChild(document.createTextNode(' ')); return; }
        var w = document.createElement('span'); w.className = 'w';
        Array.prototype.forEach.call(chunk, function (ch) {
          var s = document.createElement('span'); s.className = 'ch'; s.textContent = ch;
          s.style.setProperty('--i', i++); w.appendChild(s);
        });
        frag.appendChild(w);
      });
    });
    el.textContent = '';
    var inner = document.createElement('span'); inner.setAttribute('aria-hidden', 'true'); inner.appendChild(frag);
    el.appendChild(inner);
    el.setAttribute('aria-label', label);
    el.classList.add('split');
  }
  function splitWords(el) {
    var label = el.textContent.replace(/\s+/g, ' ').trim();
    el.innerHTML = '';
    var inner = document.createElement('span'); inner.setAttribute('aria-hidden', 'true');
    label.split(' ').forEach(function (word, i) {
      var s = document.createElement('span'); s.className = 'lw'; s.textContent = word;
      s.style.setProperty('--i', i); inner.appendChild(s); inner.appendChild(document.createTextNode(' '));
    });
    el.appendChild(inner);
    el.setAttribute('aria-label', label);
    el.classList.add('words');
  }

  /* ---------- Decode / scramble for mono labels ---------- */
  var GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&/<>+=';
  function scramble(el) {
    var final = el.textContent, frames = 22, f = 0;
    if (!final.trim() || final.length > 40) { return; }
    el.setAttribute('aria-label', final);
    function tick() {
      var out = '', reveal = (f / frames) * final.length;
      for (var i = 0; i < final.length; i++) {
        var c = final[i];
        out += (i < reveal || c === ' ' || c === '·') ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0];
      }
      el.textContent = out;
      if (f++ < frames) { window.requestAnimationFrame(tick); } else { el.textContent = final; el.removeAttribute('aria-label'); }
    }
    tick();
  }

  /* ---------- Counters ---------- */
  function countUp(el) {
    var txt = el.textContent, m = txt.match(/^([^\d]*)(\d+(?:\.\d+)?)(.*)$/);
    if (!m) { return; }
    var pre = m[1], target = parseFloat(m[2]), post = m[3], dec = (m[2].split('.')[1] || '').length;
    var t0 = null, dur = 1600;
    el.setAttribute('aria-label', txt);
    function frame(ts) {
      if (t0 === null) { t0 = ts; }
      var k = Math.min((ts - t0) / dur, 1);
      el.textContent = pre + (target * easeOutExpo(k)).toFixed(dec) + post;
      if (k < 1) { window.requestAnimationFrame(frame); } else { el.textContent = txt; el.removeAttribute('aria-label'); }
    }
    window.requestAnimationFrame(frame);
  }

  /* ---------- Marquee with scroll velocity ---------- */
  function marquee(el) {
    var track = el.querySelector('.track');
    if (!track) { return; }
    track.innerHTML += track.innerHTML; // seamless loop
    var x = 0, vel = 0, lastY = window.scrollY, half = 0;
    function measure() { half = track.scrollWidth / 2; }
    measure(); window.addEventListener('resize', measure);
    window.addEventListener('scroll', function () {
      var y = window.scrollY; vel += (y - lastY) * 0.06; lastY = y;
    }, { passive: true });
    (function loop() {
      vel *= 0.92;
      x -= 0.6 + Math.abs(vel);
      if (half && -x >= half) { x += half; }
      var skew = Math.max(-12, Math.min(12, vel * 0.9));
      track.style.transform = 'translate3d(' + x + 'px,0,0) skewX(' + (-skew) + 'deg)';
      window.requestAnimationFrame(loop);
    })();
  }

  /* ---------- Scroll-drawn timeline ---------- */
  function timeline(el) {
    var items = el.querySelectorAll('li');
    function update() {
      var r = el.getBoundingClientRect(), vh = window.innerHeight;
      var p = Math.max(0, Math.min(1, (vh * 0.85 - r.top) / (vh * 0.5)));
      el.style.setProperty('--t', p.toFixed(3));
      items.forEach(function (li, i) {
        li.classList.toggle('lit', p >= (items.length > 1 ? i / (items.length - 1) : 1) - 0.001);
      });
    }
    window.addEventListener('scroll', function () { window.requestAnimationFrame(update); }, { passive: true });
    update();
  }

  /* ---------- Tilt with glare ---------- */
  function tilt(el, max) {
    el.classList.add('tilt');
    el.addEventListener('pointermove', function (e) {
      var r = el.getBoundingClientRect();
      var px = (e.clientX - r.left) / r.width, py = (e.clientY - r.top) / r.height;
      el.style.setProperty('--gx', (px * 100).toFixed(1) + '%');
      el.style.setProperty('--gy', (py * 100).toFixed(1) + '%');
      el.style.transform = 'perspective(900px) rotateX(' + ((0.5 - py) * max).toFixed(2) + 'deg) rotateY(' + ((px - 0.5) * max).toFixed(2) + 'deg) translateY(-3px)';
    });
    el.addEventListener('pointerleave', function () { el.style.transform = ''; });
  }

  /* ---------- Magnetic buttons ---------- */
  function magnetic(el) {
    el.addEventListener('pointermove', function (e) {
      var r = el.getBoundingClientRect();
      var dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
      el.style.transform = 'translate(' + (dx * 0.22).toFixed(1) + 'px,' + (dy * 0.3).toFixed(1) + 'px)';
    });
    el.addEventListener('pointerleave', function () { el.style.transform = ''; });
  }

  /* ---------- Crosshair cursor with coordinate readout ---------- */
  function cursor() {
    var c = document.createElement('div'); c.className = 'cursor'; c.setAttribute('aria-hidden', 'true');
    c.innerHTML = '<span class="box"></span><span class="xy"></span><span class="tag-l"></span>';
    document.body.appendChild(c);
    root.classList.add('has-cursor');
    var xy = c.querySelector('.xy'), tag = c.querySelector('.tag-l');
    var x = -100, y = -100, rx = -100, ry = -100;
    function pad(n) { n = Math.round(n); return ('0000' + n).slice(-4); }
    document.addEventListener('pointermove', function (e) {
      x = e.clientX; y = e.clientY; c.classList.add('on');
      var t = e.target.closest ? e.target.closest('a, button, .tile') : null;
      var word = '';
      if (t) {
        if (t.closest('.tile')) { word = 'View'; }
        else if (t.classList.contains('build-card') || t.classList.contains('essay')) { word = 'Open'; }
      }
      c.classList.toggle('hover', !!t);
      c.classList.toggle('label', !!word);
      tag.textContent = word;
      xy.textContent = 'X ' + pad(e.pageX) + '  Y ' + pad(e.pageY);
    });
    document.addEventListener('pointerleave', function () { c.classList.remove('on'); });
    (function loop() {
      rx += (x - rx) * 0.35; ry += (y - ry) * 0.35;
      c.style.transform = 'translate3d(' + rx + 'px,' + ry + 'px,0)';
      window.requestAnimationFrame(loop);
    })();
  }

  /* ---------- Loader: quick percentage count, once per session ---------- */
  function loader() {
    var seen = false;
    try { seen = sessionStorage.getItem('pkc-loaded') === '1'; sessionStorage.setItem('pkc-loaded', '1'); } catch (e) { seen = true; }
    if (seen) { return; }
    var l = document.createElement('div'); l.className = 'loader'; l.setAttribute('aria-hidden', 'true');
    l.innerHTML = '<span class="ln-h"></span><span class="lbl">P. Krishna Chaitanya · drawing sheet</span><span class="pct">000%</span>';
    document.body.appendChild(l);
    var pct = l.querySelector('.pct'), t0 = null, dur = 1100;
    function frame(ts) {
      if (t0 === null) { t0 = ts; }
      var k = Math.min((ts - t0) / dur, 1), v = Math.round(easeOutExpo(k) * 100);
      pct.textContent = ('00' + v).slice(-3) + '%';
      l.style.setProperty('--k', easeOutExpo(k));
      if (k < 1) { window.requestAnimationFrame(frame); }
      else { l.classList.add('done'); window.setTimeout(function () { l.remove(); }, 1000); }
    }
    window.requestAnimationFrame(frame);
  }

  /* ---------- Scroll-built drawing ---------- */
  function drawingStory(story) {
    var fig = story.querySelector('.drawing'), steps = story.querySelectorAll('.dstep');
    if (!fig || !steps.length) { return; }
    function setStage(n) {
      fig.classList.remove('s0', 's1', 's2', 's3', 's4'); fig.classList.add('s' + n);
      steps.forEach(function (st) { st.classList.toggle('current', +st.getAttribute('data-stage') === n); });
    }
    setStage(0);
    if (!hasIO) { setStage(4); return; }
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { setStage(+e.target.getAttribute('data-stage')); } });
    }, { rootMargin: '-45% 0px -45% 0px' });
    steps.forEach(function (st) { io.observe(st); });
  }

  /* ---------- Pinned statement fills in letter by letter ---------- */
  function statement(sec) {
    var p = sec.querySelector('p');
    if (!p) { return; }
    splitLetters(p);
    var chars = p.querySelectorAll('.ch');
    function update() {
      var r = sec.getBoundingClientRect(), span = r.height - window.innerHeight;
      var k = span > 0 ? Math.max(0, Math.min(1, -r.top / span)) : 1;
      var on = Math.round(k * 1.15 * chars.length);
      chars.forEach(function (ch, i) { ch.classList.toggle('on', i < on); });
    }
    window.addEventListener('scroll', function () { window.requestAnimationFrame(update); }, { passive: true });
    update();
  }

  /* =================== wire up =================== */
  var heroHost = document.querySelector('.hero') || document.querySelector('.page-hero');
  if (heroHost) { flowField(heroHost); }

  if (reduce) { return; } // everything below is pure motion

  root.classList.add('motion');
  loader();

  // Hero title + lede
  var h1 = heroHost && heroHost.querySelector('h1');
  if (h1) { splitLetters(h1); window.requestAnimationFrame(function () { h1.classList.add('go'); }); }
  var lede = heroHost && heroHost.querySelector('.lede');
  if (lede) { splitWords(lede); window.requestAnimationFrame(function () { lede.classList.add('go'); }); }

  // Section titles rise letter by letter when they enter
  document.querySelectorAll('.drawing-story').forEach(drawingStory);
  whenVisible(document.querySelectorAll('.xrd'), function (el) { el.classList.add('drawn'); }, 0.3);
  document.querySelectorAll('.statement').forEach(statement);

  var titles = document.querySelectorAll('h2.section-title');
  titles.forEach(splitLetters);
  whenVisible(titles, function (el) { el.classList.add('go'); }, 0.4);

  // Mono labels decode
  whenVisible(document.querySelectorAll('.sec-num, .status dt, .build-card .kicker, .essay-source, .foot-kicker, .back, .dstep .k'), scramble, 0.6);

  // Counters
  whenVisible(document.querySelectorAll('.stats .num, .bar-value'), countUp, 0.6);

  // Mask wipes on images
  var wipes = document.querySelectorAll('.slot, .tile, .build-card .thumb');
  wipes.forEach(function (el, i) { el.classList.add('wipe'); el.style.setProperty('--d', ((i % 3) * 90) + 'ms'); });
  whenVisible(wipes, function (el) { el.classList.add('on'); }, 0.15);

  // Marquee, timeline
  document.querySelectorAll('.marquee').forEach(marquee);
  document.querySelectorAll('.timeline').forEach(timeline);

  // Pointer-only flourishes
  if (finePointer) {
    document.querySelectorAll('.status').forEach(function (el) { tilt(el, 4); });
    document.querySelectorAll('.btn, .theme-toggle').forEach(magnetic);
    cursor();
  }
})();
