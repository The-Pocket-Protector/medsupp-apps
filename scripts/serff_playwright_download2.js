// Navigate and select current versions
const sel_links2 = await page.$$('a');
for (const a of sel_links2) {
    const t = (await a.textContent()||'').trim();
    if (t === 'Select Current Version Only') { await a.click(); await page.waitForTimeout(500); break; }
}

// Try download with event capture
let dl_result;
try {
    const dl_promise = page.waitForEvent('download', { timeout: 20000 });
    await page.click('#summaryForm\\:downloadLink');
    const dl = await dl_promise;
    const fname = dl.suggestedFilename();
    const fpath = await dl.path();
    const fs = require('fs');
    let size = 0;
    let b64_preview = '';
    if (fpath && fs.existsSync(fpath)) {
        const buf = fs.readFileSync(fpath);
        size = buf.length;
        b64_preview = buf.toString('base64').substring(0, 200);
    }
    dl_result = { success: true, fname, fpath, size, b64_preview };
} catch(e) {
    dl_result = { success: false, error: e.message.substring(0, 200) };
}

dl_result
