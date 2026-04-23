const srch_btns = await page.$$('button');
let srch_btn = null;
for (const b of srch_btns) { if ((await b.textContent()).trim() === 'Search') { srch_btn = b; break; } }
if (srch_btn) { await srch_btn.click(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(4000); }
JSON.stringify({ found: !!srch_btn, url: page.url() })
