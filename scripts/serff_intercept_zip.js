// Intercept the download response and capture binary data directly
let zip_data_b64 = null;
let zip_fname = null;
let zip_size = 0;
let intercept_error = null;

// Select current versions
const sel2 = await page.$$('a');
for (const a of sel2) {
    if ((await a.textContent()||'').trim() === 'Select Current Version Only') { await a.click(); await page.waitForTimeout(400); break; }
}

// Route intercept
await page.route('https://filingaccess.serff.com/**', async (route) => {
    const req = route.request();
    try {
        const response = await route.fetch();
        const ct = (response.headers()['content-type'] || '').toLowerCase();
        const cd = response.headers()['content-disposition'] || '';
        
        if (ct.includes('zip') || ct.includes('octet-stream') || cd.includes('.zip')) {
            const body = await response.body();
            zip_data_b64 = body.toString('base64');
            zip_size = body.length;
            zip_fname = (cd.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/) || [])[1] || 'filing.zip';
            zip_fname = zip_fname.replace(/["']/g, '').trim();
        }
        await route.fulfill({ response });
    } catch(e) {
        intercept_error = e.message.substring(0, 100);
        await route.continue();
    }
});

// Click download
await page.click('#summaryForm\\:downloadLink').catch(() => {});
await page.waitForTimeout(8000);

JSON.stringify({ 
    captured: !!zip_data_b64,
    fname: zip_fname,
    size: zip_size,
    b64: zip_data_b64,
    intercept_error
})
