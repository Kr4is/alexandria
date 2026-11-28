/* Alexandria — barcode scanner (/scan). No framework, no build step.
 *
 * Reads the EAN-13 on a book's back cover (an ISBN-13 starting 978/979) from the
 * camera, a photo or typed text, asks the server for the matching book and drops
 * the returned fragment into [data-result]. The server validates the ISBN again.
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
        if (busy || video.readyState < 2) { setTimeout(tick, 200); return; }
        detector.detect(video).then(function (codes) {
            var isbn = firstIsbn(codes);
            if (!isbn || !scanning) { setTimeout(tick, 150); return; }
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
            note('Looking for a barcode', 'Hold the barcode on the back cover inside the frame. The one starting 978 or 979.', false);
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
            lookup(isbn);
        }).catch(function () {
            note('Could not read that photo', 'Try another photo, or type the ISBN.', false);
        });
    });

    /* ---------- typed ISBN ---------- */
    manual.addEventListener('submit', function (e) {
        e.preventDefault();
        var value = manual.elements.isbn.value.trim();
        if (!value) return;
        lookup(value);
    });
})();
