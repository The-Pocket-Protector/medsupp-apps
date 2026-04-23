// Complete flow in one shot - navigate, accept, search, click, download
await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(600);

const step1_links = await page.$$('a');
for (const a of step1_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);
const step1_btns = await page.$$('button');
for (const b of step1_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

// Biz type
await page.evaluate(() => document.getElementById('simpleSearch:businessType').click());
await page.waitForTimeout(300);
await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const li = items.find(i => i.textContent.includes('Life, Accident'));
    if (li) li.click();
});
await page.waitForTimeout(3500);

// Search
const step2_inputs = await page.$$('input[type=text]');
for (const inp of step2_inputs) {
    const id = await inp.getAttribute('id') || '';
    if (id.includes('serffTracking')) { await inp.fill('CSGA-132809030'); break; }
}
const step2_btns = await page.$$('button');
for (const b of step2_btns) { if ((await b.textContent()||'').trim()==='Search') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(3000);

// Click first result row
const step3_rows = await page.$$('table tbody tr');
if (step3_rows.length > 0) {
    await step3_rows[0].click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
}

// Select current versions
const step4_links = await page.$$('a');
for (const a of step4_links) {
    if ((await a.textContent()||'').trim() === 'Select Current Version Only') { await a.click(); await page.waitForTimeout(500); break; }
}

// Download
let final_result;
try {
    const dl_p = page.waitForEvent('download', { timeout: 20000 });
    await page.click('#summaryForm\\:downloadLink');
    const dl = await dl_p;
    const fname = dl.suggestedFilename();
    const fpath = await dl.path();
    const fs = require('fs');
    let size = 0;
    let b64 = '';
    if (fpath && fs.existsSync(fpath)) {
        const buf = fs.readFileSync(fpath);
        size = buf.length;
        b64 = buf.toString('base64');
    }
    final_result = { success: true, fname, fpath, size, b64_preview: b64.substring(0, 100) };
} catch(e) {
    final_result = { success: false, error: e.message.substring(0, 300), page_url: page.url() };
}

final_result
