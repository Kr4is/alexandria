/* Books as objects: shared behaviour for the 3D volumes (static/css/books3d.css).
 *
 * 1. Cross-document view transitions: the cover you click flies into the
 *    catalogue card, and flies back to its place when you return. Only one
 *    element per page may carry the `book-cover` name, so it is assigned at
 *    the moment of navigation rather than in the markup.
 * 2. Pointer tilt for [data-tilt] books.
 * 3. A `motion-ok` class on <html> so CSS can stage entrance states only when
 *    JS runs and the reader has not asked for reduced motion.
 *
 * Loaded in <head> (not deferred): `pagereveal` must be registered before the
 * first render for the incoming half of the transition to work.
 */
(function () {
    'use strict';

    var root = document.documentElement;
    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (!reduce.matches) root.classList.add('motion-ok');

    var BOOK_PATH = /^\/book\/(\d+)\/?$/;
    var NAME = 'book-cover';
    var KEY = 'alx:vt-from';

    function bookId(url) {
        try {
            var m = new URL(url, location.href).pathname.match(BOOK_PATH);
            return m ? m[1] : null;
        } catch (e) { return null; }
    }

    function onScreen(el) {
        var r = el.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
    }

    function coverOnScreen(id) {
        var all = document.querySelectorAll('[data-book-cover="' + id + '"]');
        for (var i = 0; i < all.length; i++) if (onScreen(all[i])) return all[i];
        return null;
    }

    function detailCover() { return document.querySelector('[data-book-detail-cover]'); }

    function tag(el, transition) {
        if (!el) return;
        el.style.viewTransitionName = NAME;
        transition.finished.finally(function () { el.style.viewTransitionName = ''; });
    }

    // Outgoing page.
    window.addEventListener('pageswap', function (e) {
        try { sessionStorage.setItem(KEY, location.pathname); } catch (err) { /* private mode */ }
        if (!e.viewTransition || !e.activation || !e.activation.entry) return;
        var toId = bookId(e.activation.entry.url);
        var here = detailCover();
        if (toId && !here) tag(coverOnScreen(toId), e.viewTransition);
        else if (here && !toId) tag(here, e.viewTransition);
    });

    // Incoming page.
    window.addEventListener('pagereveal', function (e) {
        if (!e.viewTransition) return;
        var from = null;
        try { from = sessionStorage.getItem(KEY); } catch (err) { /* ignore */ }
        var fromId = from ? bookId(from) : null;
        var here = detailCover();
        if (here && !fromId) tag(here, e.viewTransition);
        else if (!here && fromId) tag(coverOnScreen(fromId), e.viewTransition);
    });

    // Pointer tilt.
    function initTilt() {
        if (reduce.matches || !window.matchMedia('(hover: hover)').matches) return;
        document.querySelectorAll('.b3d[data-tilt]').forEach(function (book) {
            var host = book.closest('[data-tilt-host]') || book;
            var rest = getComputedStyle(book).getPropertyValue('--ry').trim() || '-24deg';
            var frame = 0;
            host.addEventListener('pointermove', function (ev) {
                cancelAnimationFrame(frame);
                frame = requestAnimationFrame(function () {
                    var r = host.getBoundingClientRect();
                    var x = (ev.clientX - r.left) / r.width - 0.5;   // -0.5 .. 0.5
                    var y = (ev.clientY - r.top) / r.height - 0.5;
                    book.classList.add('is-tilting');
                    book.style.setProperty('--ry', (-18 + x * 44).toFixed(1) + 'deg');
                    book.style.setProperty('--rx', (y * -14).toFixed(1) + 'deg');
                });
            });
            host.addEventListener('pointerleave', function () {
                cancelAnimationFrame(frame);
                book.classList.remove('is-tilting');
                book.style.setProperty('--ry', rest);
                book.style.setProperty('--rx', '0deg');
            });
        });
    }

    // Entrance staging: anything marked [data-reveal] gets .is-in when it scrolls into view.
    function initReveal() {
        var items = document.querySelectorAll('[data-reveal]');
        if (!items.length) return;
        if (reduce.matches || !('IntersectionObserver' in window)) {
            items.forEach(function (el) { el.classList.add('is-in'); });
            return;
        }
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) { en.target.classList.add('is-in'); io.unobserve(en.target); }
            });
        }, { rootMargin: '0px 0px -12% 0px', threshold: 0.15 });
        items.forEach(function (el) { io.observe(el); });
    }

    // Horizontal strips that should open on their latest item (e.g. year piles).
    function initScrollEnd() {
        document.querySelectorAll('[data-scroll-end]').forEach(function (el) {
            if (el.scrollWidth > el.clientWidth) el.scrollLeft = el.scrollWidth;
        });
    }

    function init() { initTilt(); initReveal(); initScrollEnd(); }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
