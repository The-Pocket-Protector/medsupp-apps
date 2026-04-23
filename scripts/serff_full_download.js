// Complete flow: navigate → accept → search → click filing → download ZIP
// Returns base64-encoded zip content

await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(600);

// Accept terms
const nav_links = await page.$$('a');
for (const a of nav_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);
const acc_btns = await page.$$('button');
for (const b of acc_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

// Select biz type
await page.evaluate(() => document.getElementById('simpleSearch:businessType').click());
await page.waitForTimeout(300);
await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const li = items.find(i => i.textContent.includes('Life, Accident'));
    if (li) li.click();
});
await page.waitForTimeout(3500);

// Search by tracking number
const all_inputs = await page.$$('input[type=text]');
for (const inp of all_inputs) {
    const id = await inp.getAttribute('id') || '';
    if (id.includes('serffTracking')) { await inp.fill('CSGA-132809030'); break; }
}
const btns = await page.$$('button');
for (const b of btns) { if ((await b.textContent()||'').trim()==='Search') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(3000);

// Click first result row
const data_rows = await page.$$('table tbody tr');
if (data_rows.length > 0) {
    await data_rows[0].click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
}

// Select current versions only
const select_btns = await page.$$('a');
for (const a of select_btns) {
    const t = (await a.textContent()||'').trim();
    if (t === 'Select Current Version Only') { await a.click(); await page.waitForTimeout(500); break; }
}

// Intercept the download response
let zip_base64 = null;
let zip_filename = null;

// Override fetch/XHR to capture binary response
await page.route('**/filingSummary.xhtml*', async (route) => {
    const req = route.request();
    if (req.method() === 'POST') {
        const response = await route.fetch();
        const content_type = response.headers()['content-type'] || '';
        const content_disp = response.headers()['content-disposition'] || '';
        
        if (content_type.includes('zip') || content_type.includes('octet') || content_disp.includes('attachment')) {
            const body = await response.body();
            zip_base64 = body.toString('base64');
            zip_filename = (content_disp.match(/filename="?([^";\n]+)"?/) || [])[1] || 'filing.zip';
            await route.fulfill({ response });
        } else {
            await route.continue();
        }
    } else {
        await route.continue();
    }
});

// Click download
await page.click('#summaryForm\\:downloadLink').catch(() => {});
await page.waitForTimeout(4000);

JSON.stringify({ 
    zip_captured: !!zip_base64,
    zip_filename,
    zip_size_bytes: zip_base64 ? Buffer.from(zip_base64, 'base64').length : 0,
    zip_base64: zip_base64 ? zip_base64.substring(0, 100) + '...[truncated]' : null
})
