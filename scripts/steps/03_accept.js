const accept_btns = await page.$$('button');
let accept_btn = null;
for (const b of accept_btns) { if ((await b.textContent()).trim() === 'Accept') { accept_btn = b; break; } }
if (accept_btn) { await accept_btn.click(); await page.waitForLoadState('networkidle'); await page.waitForTimeout(1500); }
JSON.stringify({ found: !!accept_btn, url: page.url() })
