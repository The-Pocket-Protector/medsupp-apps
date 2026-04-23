// Direct approach: accept terms then go straight to filing summary URL
await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(500);

// Accept
const lnks = await page.$$('a');
for (const a of lnks) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);
const bts = await page.$$('button');
for (const b of bts) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1200);

// Navigate directly to filing summary (skip search entirely)
await page.goto('https://filingaccess.serff.com/sfa/search/filingSummary.xhtml?filingId=132809030');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

const summary_url = page.url();
const summary_body = await page.evaluate(() => document.body.innerText.substring(0, 200));

summary_url + ' | ' + summary_body
