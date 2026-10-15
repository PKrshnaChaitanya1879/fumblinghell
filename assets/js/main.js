(function () {
  'use strict';
  var root = document.documentElement;
  root.classList.add('js');

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
