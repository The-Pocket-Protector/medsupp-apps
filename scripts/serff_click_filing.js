await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(600);

const nav_links = await page.$$('a');
for (const a of nav_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);

const acc_btns = await page.$$('button');
for (const b of acc_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
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

// Find result row link - click the company name or tracking number link
const result_links = await page.$$('a');
let filing_link = null;
for (const a of result_links) {
    const t = (await a.textContent()||'').trim();
    const h = await a.getAttribute('href') || '';
    if (t.includes('CSGA-132809030') || h.includes('filing') || h.includes('detail')) {
        filing_link = a;
        break;
    }
}

let filing_url = 'no link found';
let filing_body = '';
let doc_links = [];

if (filing_link) {
    await filing_link.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    filing_url = page.url();
    filing_body = await page.evaluate(() => document.body.innerText.substring(0, 1000));
    
    // Get all links - look for PDF/document links
    const page_links = await page.$$('a[href]');
    for (const a of page_links) {
        const h = await a.getAttribute('href') || '';
        const t = (await a.textContent()||'').trim().substring(0,80);
        if (h.includes('.pdf') || h.includes('document') || h.includes('Download') || t.includes('pdf') || t.length > 3) {
            doc_links.push({href: h, text: t});
        }
    }
}

JSON.stringify({ filing_url, filing_body, doc_links: doc_links.slice(0,15) })
