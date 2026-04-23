const begin_lnk = await page.$('a[href*="userAgreement"]');
if (begin_lnk) { await begin_lnk.click(); await page.waitForLoadState('networkidle'); }
JSON.stringify({ found: !!begin_lnk, url: page.url() })
