/* Alexandria — barcode scanner (/scan). No framework, no build step.
 *
 * Reads the EAN-13 on a book's back cover (an ISBN-13 starting 978/979) from the
 * camera, a photo or typed text, asks the server for the matching book and drops
 * the returned fragment into [data-result]. The server validates the ISBN again.
 * Batch mode keeps the camera open and files each book straight away (see enqueue()),
 * listing every outcome with an undo for the ones it added.
 * Uses the native BarcodeDetector when the browser has it, otherwise the vendored
 * barcode-detector ponyfill (zxing-wasm, served from /static, no CDN).
 */
(function () {
    'use strict';

    var root = document.querySelector('[data-scan]');
    if (!root) return;

    var $ = function (sel) { return root.querySelector(sel); };
    var view = $('[data-view]'), video = $('[data-video]');
    var noteBox = $('[data-note]'), noteTitle = $('[data-note-title]'), noteBody = $('[data-note-body]');
    var startBtn = $('[data-start]'), stopBtn = $('[data-stop]');
    var photoWrap = $('[data-photo-wrap]'), photoInput = $('[data-photo]');
    var manual = $('[data-manual]'), result = $('[data-result]'), live = $('[data-live]');
    var lookupUrl = root.getAttribute('data-lookup-url');
    var batchUrl = root.getAttribute('data-batch-url');
    var undoUrl = root.getAttribute('data-undo-url');
    var batchBox = $('[data-batch]'), batchOpts = $('[data-batch-opts]');
    var log = $('[data-log]'), logList = $('[data-log-list]'), logSummary = $('[data-log-summary]');
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    var seen = {};                       // ISBNs already handled this session: never sent twice
    var counts = { added: 0, owned: 0, missing: 0 };

    var stream = null, detector = null, scanning = false, busy = false;

    function note(title, body, hidden) {
        noteTitle.textContent = title;
        noteBody.textContent = body;
        noteBox.hidden = !!hidden;
    }

    function announce(msg) { live.textContent = ''; setTimeout(function () { live.textContent = msg; }, 50); }

    function isIsbnCandidate(value) { return /^97[89]\d{10}$/.test(value || ''); }

    /* ---------- detector ---------- */
    function getDetector() {
        if (detector) return Promise.resolve(detector);
        var native = window.BarcodeDetector;
        var supported = native && native.getSupportedFormats
            ? native.getSupportedFormats() : Promise.resolve([]);
        return supported.then(function (formats) {
            if (native && formats.indexOf('ean_13') !== -1) {
                detector = new native({ formats: ['ean_13'] });
            } else {
                var api = window.BarcodeDetectionAPI;
                if (!api) throw new Error('decoder-missing');
                api.prepareZXingModule({
                    overrides: {
                        locateFile: function (path, prefix) {
                            return path.endsWith('.wasm') ? root.getAttribute('data-wasm') : prefix + path;
                        }
                    }
                });
                detector = new api.BarcodeDetector({ formats: ['ean_13'] });
            }
            return detector;
        });
    }

    function firstIsbn(codes) {
        for (var i = 0; i < codes.length; i++) {
            if (isIsbnCandidate(codes[i].rawValue)) return codes[i].rawValue;
        }
        return null;
    }

    /* ---------- lookup ---------- */
    function lookup(isbn) {
        if (busy) return Promise.resolve();
        busy = true;
        result.setAttribute('aria-busy', 'true');
        return fetch(lookupUrl + '?isbn=' + encodeURIComponent(isbn), { credentials: 'same-origin' })
            .then(function (res) {
                if (res.redirected || res.status === 401) { window.location.reload(); return null; }
                if (!res.ok) throw new Error('http-' + res.status);
                return res.text();
            })
            .then(function (html) {
                if (html === null) return;
                result.innerHTML = html;
                var state = result.querySelector('[data-state]');
                announce(state && state.getAttribute('data-state') === 'found' ? 'Book found.' : 'Lookup finished.');
                result.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
            })
            .catch(function () {
                result.innerHTML = '';
                note('Lookup failed', 'The archives did not answer. Check your connection and try again.');
            })
            .then(function () { busy = false; result.removeAttribute('aria-busy'); });
    }

    /* ---------- batch mode ---------- */
    function batchStatus() {
        var picked = root.querySelector('input[name="batch-status"]:checked');
        return picked ? picked.value : 'tbr';
    }

    function renderSummary() {
        var parts = [counts.added + ' added'];
        if (counts.owned) parts.push(counts.owned + ' already in library');
        if (counts.missing) parts.push(counts.missing + ' not found');
        logSummary.textContent = parts.join(' · ');
    }

    function el(tag, cls, text) {
        var node = document.createElement(tag);
        if (cls) node.className = cls;
        if (text) node.textContent = text;
        return node;
    }

    function paintRow(row, out) {
        // Titles come from outside APIs: only ever set as text, never as HTML.
        row.textContent = '';
        row.setAttribute('data-result', out.result);
        var tag = { added: 'Filed', owned: 'In your library', missing: 'Not found', invalid: 'Not an ISBN' }[out.result] || 'Error';
        row.appendChild(el('span', 'status-tag scan-tag scan-tag-' + out.result, tag));
        var body = el('div', 'scan-row-body');
        if (out.title) {
            var title = out.url ? el('a', 'scan-row-title', out.title) : el('span', 'scan-row-title', out.title);
            if (out.url) title.href = out.url;
            body.appendChild(title);
            if (out.authors) body.appendChild(el('span', 'scan-row-by', out.authors));
        } else {
            body.appendChild(el('span', 'scan-row-title', out.message || 'ISBN ' + out.isbn));
        }
        body.appendChild(el('span', 'scan-row-isbn mono', 'ISBN ' + out.isbn));
        row.appendChild(body);
        var actions = el('div', 'scan-row-actions');
        if (out.result === 'added') {
            var undo = el('button', 'btn-line scan-undo', 'Undo');
            undo.type = 'button';
            undo.setAttribute('aria-label', 'Undo: withdraw ' + out.title);
            undo.addEventListener('click', function () { undoAdd(row, out, undo); });
            actions.appendChild(undo);
        } else if (out.result === 'missing') {
            var retry = el('button', 'btn-line scan-undo', 'Try again');
            retry.type = 'button';
            retry.addEventListener('click', function () { delete seen[out.isbn]; row.remove(); counts.missing--; renderSummary(); enqueue(out.isbn); });
            actions.appendChild(retry);
        }
        row.appendChild(actions);
    }

    function undoAdd(row, out, button) {
        button.disabled = true;
        fetch(undoUrl.replace('/0/', '/' + out.book_id + '/'), {
            method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }
        }).then(function (res) {
            if (!res.ok) throw new Error('http-' + res.status);
            counts.added--; delete seen[out.isbn]; renderSummary();
            row.setAttribute('data-result', 'undone');
            row.textContent = '';
            row.appendChild(el('span', 'status-tag scan-tag', 'Withdrawn'));
            row.appendChild(el('div', 'scan-row-body', out.title + ' was removed. Scan it again to re-file it.'));
            announce(out.title + ' withdrawn.');
        }).catch(function () { button.disabled = false; announce('Could not undo. Try again.'); });
    }

    function enqueue(raw) {
        var isbn = String(raw).replace(/[\s-]/g, '');
        if (seen[isbn]) return;
        seen[isbn] = true;
        log.hidden = false;
        var row = el('li', 'scan-row');
        row.setAttribute('data-result', 'pending');
        row.appendChild(el('span', 'status-tag scan-tag', 'Reading…'));
        row.appendChild(el('div', 'scan-row-body', 'ISBN ' + isbn));
        logList.insertBefore(row, logList.firstChild);
        var body = new URLSearchParams({ isbn: isbn, status: batchStatus() });
        fetch(batchUrl, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }, body: body })
            .then(function (res) {
                if (res.redirected || res.status === 401) { window.location.reload(); return null; }
                if (!res.ok) throw new Error('http-' + res.status);
                return res.json();
            })
            .then(function (out) {
                if (!out) return;
                if (out.result === 'added') counts.added++;
                else if (out.result === 'owned') counts.owned++;
                else if (out.result === 'missing') counts.missing++;
                if (out.result === 'invalid') delete seen[isbn];
                paintRow(row, out);
                renderSummary();
                announce({ added: 'Filed ' + out.title, owned: out.title + ' is already in your library',
                    missing: 'ISBN ' + isbn + ' not found', invalid: 'Not an ISBN' }[out.result] || 'Done');
            })
            .catch(function () {
                delete seen[isbn];
                paintRow(row, { result: 'error', isbn: isbn, message: 'The archives did not answer. Scan it again.' });
            });
    }

    batchBox.addEventListener('change', function () {
        batchOpts.hidden = !batchBox.checked;
        result.innerHTML = '';
        startBtn.textContent = 'Start camera';
        if (stream) note(batchBox.checked ? 'Batch mode' : 'Looking for a barcode',
            batchBox.checked ? 'Keep scanning: each book is filed as soon as it is read.' : 'Hold the barcode on the back cover inside the frame. The one starting 978 or 979.', false);
    });

    /* ---------- camera ---------- */
    function stop() {
        scanning = false;
        if (stream) stream.getTracks().forEach(function (t) { t.stop(); });
        stream = null;
        video.srcObject = null;
        view.hidden = true;
        stopBtn.hidden = true;
        startBtn.hidden = false;
    }

    function tick() {
        if (!scanning) return;
        if ((busy && !batchBox.checked) || video.readyState < 2) { setTimeout(tick, 200); return; }
        detector.detect(video).then(function (codes) {
            var isbn = firstIsbn(codes);
            if (!isbn || !scanning) { setTimeout(tick, 150); return; }
            if (batchBox.checked) {
                if (!seen[isbn] && navigator.vibrate) navigator.vibrate(60);
                enqueue(isbn);
                setTimeout(tick, 600);
                return;
            }
            if (navigator.vibrate) navigator.vibrate(60);
            stop();
            startBtn.textContent = 'Scan another';
            note('Barcode read', 'ISBN ' + isbn, false);
            lookup(isbn);
        }).catch(function () { setTimeout(tick, 400); });
    }

    function cameraProblem(err) {
        var name = err && err.name;
        if (name === 'NotAllowedError' || name === 'SecurityError') {
            note('Camera blocked', 'Allow camera access for this site in your browser settings, then try again. You can still type the ISBN or take a photo.');
        } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
            note('No camera found', 'This device has no usable camera. Take a photo of the barcode or type the ISBN.');
        } else if (err && err.message === 'decoder-missing') {
            note('Scanner not loaded', 'The barcode reader did not load. Reload the page, or type the ISBN.');
        } else {
            note('Camera unavailable', 'Another app may be using it. Close it and try again, or type the ISBN.');
        }
    }

    function start() {
        result.innerHTML = '';
        startBtn.disabled = true;
        note('Starting camera', 'Waiting for permission…', false);
        Promise.all([
            getDetector(),
            navigator.mediaDevices.getUserMedia({
                video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
                audio: false
            })
        ]).then(function (parts) {
            stream = parts[1];
            video.srcObject = stream;
            return video.play();
        }).then(function () {
            view.hidden = false;
            startBtn.hidden = true;
            stopBtn.hidden = false;
            stopBtn.focus();
            if (batchBox.checked) note('Batch mode', 'Keep scanning: each book is filed as soon as it is read.', false);
            else note('Looking for a barcode', 'Hold the barcode on the back cover inside the frame. The one starting 978 or 979.', false);
            announce('Camera on. Looking for a barcode.');
            scanning = true;
            tick();
        }).catch(function (err) {
            stop();
            cameraProblem(err);
        }).then(function () { startBtn.disabled = false; });
    }

    /* ---------- start-up: can this page use a camera at all? ---------- */
    var canCamera = window.isSecureContext && navigator.mediaDevices && navigator.mediaDevices.getUserMedia;
    if (canCamera) {
        startBtn.addEventListener('click', start);
        stopBtn.addEventListener('click', function () {
            stop();
            note('Camera off', 'Press Start camera to scan again.', false);
            startBtn.focus();
        });
    } else {
        startBtn.hidden = true;
        note(window.isSecureContext ? 'No camera access' : 'Camera needs HTTPS',
            window.isSecureContext
                ? 'This browser cannot open a camera. Take a photo of the barcode or type the ISBN.'
                : 'Browsers only allow the camera on pages served over HTTPS. Open this site through its HTTPS address, or take a photo or type the ISBN below.',
            false);
    }
    document.addEventListener('visibilitychange', function () { if (document.hidden && stream) { stop(); note('Camera off', 'Paused while the page was hidden.', false); } });
    window.addEventListener('pagehide', stop);

    /* ---------- photo ---------- */
    photoInput.addEventListener('change', function () {
        var file = photoInput.files && photoInput.files[0];
        photoInput.value = '';
        if (!file) return;
        note('Reading photo', 'One moment…', false);
        getDetector().then(function (d) {
            return createImageBitmap(file).then(function (bmp) {
                return d.detect(bmp).then(function (codes) { if (bmp.close) bmp.close(); return codes; });
            });
        }).then(function (codes) {
            var isbn = firstIsbn(codes);
            if (!isbn) {
                note('No ISBN in that photo', 'Take it again closer, flat and in good light, with the whole barcode in view. Or type the number.', false);
                return;
            }
            note('Barcode read', 'ISBN ' + isbn, false);
            if (batchBox.checked) enqueue(isbn); else lookup(isbn);
        }).catch(function () {
            note('Could not read that photo', 'Try another photo, or type the ISBN.', false);
        });
    });

    /* ---------- typed ISBN ---------- */
    manual.addEventListener('submit', function (e) {
        e.preventDefault();
        var value = manual.elements.isbn.value.trim();
        if (!value) return;
        if (batchBox.checked) { enqueue(value); manual.elements.isbn.value = ''; } else lookup(value);
    });
})();
