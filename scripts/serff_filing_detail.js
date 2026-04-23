await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(800);

const nav_links = await page.$$('a');
for (const a of nav_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(500);

const acc_btns = await page.$$('button');
for (const b of acc_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

const url1 = page.url();

// Now try navigating directly to a filing detail page
await page.goto('https://filingaccess.serff.com/sfa/search/filingSearch.xhtml');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(500);

// Select business type
await page.evaluate(() => document.getElementById('simpleSearch:businessType').click());
await page.waitForTimeout(300);
await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const li = items.find(i => i.textContent.includes('Life, Accident'));
    if (li) li.click();
});
await page.waitForTimeout(3500);

// Search by SERFF tracking number
const all_inputs = await page.$$('input[type=text]');
let serff_input = null;
for (const inp of all_inputs) {
    const id = await inp.getAttribute('id') || '';
    const name = await inp.getAttribute('name') || '';
    if (id.includes('serffTracking') || name.includes('serffTracking')) { serff_input = inp; break; }
}

let search_result = 'no serff input found - ids: ' + JSON.stringify(await Promise.all(all_inputs.map(async i => await i.getAttribute('id'))));

if (serff_input) {
    await serff_input.fill('CSGA-132809030');
    const btns = await page.$$('button');
    for (const b of btns) { if ((await b.textContent()||'').trim()==='Search') { await b.click(); break; } }
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
    search_result = page.url();
}

const body = await page.evaluate(() => document.body.innerText.substring(0,600));

JSON.stringify({ url1, search_result, body })
