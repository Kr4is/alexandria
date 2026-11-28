Vendored, self-hosted (no CDN):

- `barcode-detector.js`: barcode-detector 3.2.5, `dist/iife/ponyfill.js` (MIT). Exposes `window.BarcodeDetectionAPI`.
- `zxing_reader.wasm`: zxing-wasm 3.1.8, `dist/reader/zxing_reader.wasm` (MIT / Apache-2.0 for zxing-cpp).

To update: `npm pack barcode-detector zxing-wasm`, copy the same files, and keep the two versions in step
(`BarcodeDetectionAPI.ZXING_WASM_VERSION` must match the wasm).
