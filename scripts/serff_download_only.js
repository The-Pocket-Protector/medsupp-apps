// PRECONDITION: We're on filingSummary.xhtml for filing CSGA-132809030
// This script just does the download

// Confirm we're on the right page
const dl_check_url = page.url();
const dl_check_body = await page.evaluate(() => document.body.innerText.substring(0, 100));

// Select current versions
const dl_sel_links = await page.$$('a');
for (const dl_a of dl_sel_links) {
    if ((await dl_a.textContent()||'').trim() === 'Select Current Version Only') { 
        await dl_a.click(); 
        await page.waitForTimeout(500); 
        break; 
    }
}

// Try download
let dl_final;
try {
    const dl_ev = page.waitForEvent('download', { timeout: 18000 });
    await page.click('#summaryForm\\:downloadLink');
    const dl = await dl_ev;
    const dl_fname = dl.suggestedFilename();
    // Save immediately and synchronously
    const dl_save_path = '/tmp/serff_dl_' + Date.now() + '.zip';
    await dl.saveAs(dl_save_path);
    const fs = require('fs');
    await new Promise(r => setTimeout(r, 2000)); // wait for write
    let dl_size = 0;
    let dl_b64 = '';
    if (fs.existsSync(dl_save_path)) {
        const dl_buf = fs.readFileSync(dl_save_path);
        dl_size = dl_buf.length;
        dl_b64 = dl_buf.toString('base64');
    }
    dl_final = { ok: true, fname: dl_fname, path: dl_save_path, size: dl_size, b64: dl_b64 };
} catch(dl_err) {
    dl_final = { ok: false, err: dl_err.message.substring(0, 200), url: dl_check_url, body: dl_check_body };
}

JSON.stringify(dl_final)
