(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');

  /* ---- Theme toggle (light / dark), remembered on this device ---- */
  var toggle = document.querySelector('.theme-toggle');
  var prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
  function currentTheme() {
    var set = root.getAttribute('data-theme');
    if (set) { return set; }
    return prefersDark && prefersDark.matches ? 'dark' : 'light';
  }
  if (toggle) {
    toggle.addEventListener('click', function () {
      var next = currentTheme() === 'dark' ? 'light' : 'dark';
      root.setAttribute('data-theme', next);
      try { localStorage.setItem('theme', next); } catch (e) { /* storage blocked: theme still switches */ }
    });
  }

  /* ---- Scroll progress bar and nav shadow ---- */
  var bar = document.querySelector('.progress');
  var nav = document.querySelector('.nav');
  var ticking = false;
  function onScroll() {
    var max = document.documentElement.scrollHeight - window.innerHeight;
    if (bar) { bar.style.setProperty('--p', max > 0 ? Math.min(window.scrollY / max, 1) : 0); }
    if (nav) { nav.classList.toggle('scrolled', window.scrollY > 8); }
    ticking = false;
  }
  window.addEventListener('scroll', function () {
    if (!ticking) { ticking = true; window.requestAnimationFrame(onScroll); }
  }, { passive: true });
  onScroll();

  /* ---- Scroll reveal ---- */
  var reveals = document.querySelectorAll('.reveal');
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    reveals.forEach(function (el) { io.observe(el); });
  } else {
    reveals.forEach(function (el) { el.classList.add('in'); });
  }

  /* ---- Highlight the nav link for the section in view (home page) ---- */
  var links = {};
  document.querySelectorAll('.nav ul a[href^="#"]').forEach(function (a) {
    links[a.getAttribute('href').slice(1)] = a;
  });
  if ('IntersectionObserver' in window && Object.keys(links).length) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        var link = links[e.target.id];
        if (!link) { return; }
        if (e.isIntersecting) {
          Object.keys(links).forEach(function (k) { links[k].classList.remove('active'); links[k].removeAttribute('aria-current'); });
          link.classList.add('active');
          link.setAttribute('aria-current', 'true');
        }
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    Object.keys(links).forEach(function (id) {
      var sec = document.getElementById(id);
      if (sec) { spy.observe(sec); }
    });
  }

  /* ---- Image slots: if the file exists, swap the placeholder for it ---- */
  document.querySelectorAll('.slot[data-src]').forEach(function (slot) {
    var probe = new Image();
    probe.onload = function () {
      probe.alt = slot.getAttribute('data-alt') || '';
      probe.loading = 'lazy';
      slot.appendChild(probe);
      slot.classList.add('has-img');
    };
    probe.src = slot.getAttribute('data-src');
  });

  /* ---- Lightbox ---- */
  var box = document.getElementById('lightbox');
  var big = document.getElementById('lb-img');
  var thumbs = Array.prototype.slice.call(document.querySelectorAll('#gallery .tile button'));
  if (!box || !thumbs.length) { return; }
  var idx = 0, opener = null;

  function show(i) {
    idx = (i + thumbs.length) % thumbs.length;
    var img = thumbs[idx].querySelector('img');
    big.src = thumbs[idx].getAttribute('data-full') || img.src;
    big.alt = img.alt;
  }
  function open(i) {
    opener = document.activeElement;
    show(i);
    if (typeof box.showModal === 'function') { box.showModal(); } else { box.setAttribute('open', ''); }
    box.querySelector('.lb-close').focus();
  }
  function close() {
    if (typeof box.close === 'function') { box.close(); } else { box.removeAttribute('open'); }
    if (opener) { opener.focus(); }
  }

  thumbs.forEach(function (b, i) { b.addEventListener('click', function () { open(i); }); });
  box.querySelector('.lb-close').addEventListener('click', close);
  box.querySelector('.lb-prev').addEventListener('click', function () { show(idx - 1); });
  box.querySelector('.lb-next').addEventListener('click', function () { show(idx + 1); });
  box.addEventListener('click', function (e) { if (e.target === box) { close(); } });
  document.addEventListener('keydown', function (e) {
    if (!box.hasAttribute('open')) { return; }
    if (e.key === 'ArrowLeft') { show(idx - 1); }
    else if (e.key === 'ArrowRight') { show(idx + 1); }
    else if (e.key === 'Escape') { e.preventDefault(); close(); }
  });
})();
