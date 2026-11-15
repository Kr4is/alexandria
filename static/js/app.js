/* Alexandria — shared behaviour for every page. No framework, no build step.
 *
 *  - Flash messages: dismiss button and auto-dismiss.
 *  - form.js-submit-loading: disable the submit button once sent.
 *  - Confirmation modals (#modal-finish, #modal-delete), opened by
 *    [data-confirm="finish|delete"][data-action][data-title] or window.AlexandriaModal.
 *  - The dial: hidden while any [data-dater] is on screen.
 *  - One record held at a time: [data-record] with a [data-hold] toggle;
 *    holding dims the rest, Esc or a second press returns it.
 *  - Page steppers: [data-step="-1|1|10"] next to an input[name=current_page].
 *  - window.Alexandria.toast(message).
 */
(function () {
    'use strict';

    var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');

    /* ---------- toast ---------- */
    var toastEl = document.querySelector('[data-toast]');
    var toastTimer = null;
    function toast(msg) {
        if (!toastEl) return;
        toastEl.textContent = msg;
        toastEl.classList.add('on');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { toastEl.classList.remove('on'); }, 2600);
    }

    /* ---------- flashes ---------- */
    function dismissFlash(el) {
        el.classList.add('leave');
        setTimeout(function () { el.remove(); }, 320);
    }
    document.querySelectorAll('.flash').forEach(function (row) {
        var btn = row.querySelector('.flash-close');
        if (btn) btn.addEventListener('click', function () { dismissFlash(row); });
        var cat = row.getAttribute('data-category');
        var delay = (cat === 'error' || cat === 'danger') ? 9000 : 5000;
        setTimeout(function () { if (row.parentNode) dismissFlash(row); }, delay);
    });

    /* ---------- submit once ---------- */
    document.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form.classList || !form.classList.contains('js-submit-loading')) return;
        var btn = form.querySelector('[type="submit"]');
        if (btn && !btn.disabled) setTimeout(function () { btn.disabled = true; }, 0);
    });

    /* ---------- modals ---------- */
    var lastFocus = null;
    var openModalEl = null;
    function focusables(root) {
        return root.querySelectorAll('a[href], button:not([disabled]), textarea, input:not([type=hidden]), select, [tabindex]:not([tabindex="-1"])');
    }
    function openModal(id) {
        var modal = document.getElementById(id);
        if (!modal) return;
        lastFocus = document.activeElement;
        modal.hidden = false;
        openModalEl = modal;
        document.body.classList.add('modal-open');
        var list = focusables(modal.querySelector('.modal-panel'));
        if (list.length) list[list.length - 1].focus();
    }
    function closeModal(modal) {
        modal = modal || openModalEl;
        if (!modal || modal.hidden) return;
        modal.hidden = true;
        openModalEl = null;
        document.body.classList.remove('modal-open');
        if (lastFocus && lastFocus.focus) lastFocus.focus();
    }
    document.querySelectorAll('[data-modal-close]').forEach(function (el) {
        el.addEventListener('click', function () { closeModal(el.closest('.modal')); });
    });
    document.addEventListener('keydown', function (e) {
        if (!openModalEl) return;
        if (e.key === 'Escape') { e.preventDefault(); closeModal(); return; }
        if (e.key === 'Tab') {
            var list = focusables(openModalEl.querySelector('.modal-panel'));
            if (!list.length) return;
            var first = list[0], last = list[list.length - 1];
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
    });
    function prime(kind, action, title) {
        var form = document.getElementById('modal-' + kind + '-form');
        var body = document.getElementById('modal-' + kind + '-body');
        if (form) form.action = action;
        if (body && title) {
            body.textContent = kind === 'finish'
                ? '“' + title + '” will be stamped finished with today’s date.'
                : '“' + title + '” will be withdrawn and its record removed. This cannot be undone.';
        }
        openModal('modal-' + kind);
    }
    document.addEventListener('click', function (e) {
        var t = e.target.closest('[data-confirm]');
        if (!t) return;
        e.preventDefault();
        prime(t.getAttribute('data-confirm'), t.getAttribute('data-action'), t.getAttribute('data-title'));
    });
    window.AlexandriaModal = {
        openFinish: function (action, title) { prime('finish', action, title); },
        openDelete: function (action, title) { prime('delete', action, title); },
        close: function () { closeModal(); }
    };

    /* ---------- the dial ---------- */
    var dial = document.querySelector('[data-dial]');
    var daters = document.querySelectorAll('[data-dater]');
    if (dial && daters.length && 'IntersectionObserver' in window) {
        var visible = new Set();
        dial.classList.add('away');
        var io = new IntersectionObserver(function (entries) {
            entries.forEach(function (en) {
                if (en.isIntersecting) visible.add(en.target); else visible.delete(en.target);
            });
            dial.classList.toggle('away', visible.size > 0);
        });
        daters.forEach(function (d) { io.observe(d); });
    }

    /* ---------- one record held at a time ---------- */
    var held = null;
    function release() {
        if (!held) return;
        held.classList.remove('held');
        var b = held.querySelector('[data-hold]');
        if (b) b.setAttribute('aria-expanded', 'false');
        held = null;
        document.body.classList.remove('holding');
    }
    function hold(rec) {
        if (held === rec) { release(); return; }
        release();
        held = rec;
        rec.classList.add('held');
        var b = rec.querySelector('[data-hold]');
        if (b) b.setAttribute('aria-expanded', 'true');
        document.body.classList.add('holding');
    }
    document.addEventListener('click', function (e) {
        var btn = e.target.closest('[data-hold]');
        if (btn) { hold(btn.closest('[data-record]')); return; }
        if (held && !e.target.closest('[data-record]') && !e.target.closest('.modal')) release();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && held && !openModalEl) {
            var b = held.querySelector('[data-hold]');
            release();
            if (b) b.focus();
        }
    });

    /* ---------- page steppers + live ruler ---------- */
    document.addEventListener('click', function (e) {
        var b = e.target.closest('[data-step]');
        if (!b) return;
        var form = b.closest('form');
        var input = form && form.querySelector('input[name="current_page"]');
        if (!input) return;
        var max = parseInt(input.max, 10) || Infinity;
        var v = (parseInt(input.value, 10) || 0) + parseInt(b.getAttribute('data-step'), 10);
        input.value = Math.max(0, Math.min(max, v));
        input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    document.addEventListener('input', function (e) {
        var input = e.target;
        if (input.name !== 'current_page') return;
        var scope = input.closest('[data-record]') || input.closest('form');
        var max = parseInt(input.max, 10);
        if (!scope || !max) return;
        var pct = Math.max(0, Math.min(100, Math.round((parseInt(input.value, 10) || 0) / max * 100)));
        var fill = scope.querySelector('.ruler .fill');
        var label = scope.querySelector('.ruler .pct');
        if (fill) fill.style.width = pct + '%';
        if (label) label.textContent = pct + '%';
    });

    /* Stamps marked .land animate once when they enter the viewport. */
    if (!reduce.matches && 'IntersectionObserver' in window) {
        var lands = document.querySelectorAll('.stamp.land');
        if (lands.length) {
            var so = new IntersectionObserver(function (entries) {
                entries.forEach(function (en) {
                    if (en.isIntersecting) { en.target.style.animationPlayState = 'running'; so.unobserve(en.target); }
                });
            }, { threshold: .6 });
            lands.forEach(function (s) { s.style.animationPlayState = 'paused'; so.observe(s); });
        }
    }

    window.Alexandria = { toast: toast, hold: hold, release: release };
})();
