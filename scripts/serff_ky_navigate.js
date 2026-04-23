// Navigate to KY, accept terms, set filters, search, change to 100 rows/page
await page.goto('https://filingaccess.serff.com/sfa/home/KY');
await page.waitForLoadState('networkidle');
await page.waitForTimeout(600);

const ky_links = await page.$$('a');
for (const a of ky_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);
const ky_btns = await page.$$('button');
for (const b of ky_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

await page.evaluate(() => document.getElementById('simpleSearch:businessType').click());
await page.waitForTimeout(300);
await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const li = items.find(i => i.textContent.includes('Life, Accident'));
    if (li) li.click();
});
await page.waitForTimeout(3500);

await page.evaluate(() => {
    const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    w.show();
    w.panel.find("li.ui-selectcheckboxmenu-item").each(function(i, li) {
        const lbl = li.querySelector("label");
        if (lbl) {
            const txt = lbl.textContent.trim();
            if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                w.check(jQuery(li).find(".ui-chkbox-box"), true);
            }
        }
    });
    w.updateLabel();
    w.hide();
});
await page.waitForTimeout(400);

const ky_search_btns = await page.$$('button');
for (const b of ky_search_btns) { if ((await b.textContent()||'').trim()==='Search') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(4000);

// Set 100 rows per page
const rpp = await page.$('.ui-paginator-rpp-options');
if (rpp) { await rpp.selectOption('100'); await page.waitForLoadState('networkidle'); await page.waitForTimeout(2500); }

// Get total count and page info
const ky_body = await page.evaluate(() => document.body.innerText);
const ky_count_m = ky_body.match(/([0-9,]+)\s+Filing/);
const ky_total = ky_count_m ? parseInt(ky_count_m[1].replace(/,/g,'')) : 0;

// Get headers
const ky_headers = await page.evaluate(() => Array.from(document.querySelectorAll('table th')).map(th => th.textContent.trim()));

JSON.stringify({ total: ky_total, headers: ky_headers, url: page.url() })
