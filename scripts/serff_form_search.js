// Search KY SERFF for Form-type filings, paginate through all results
// Returns all rows
const STATE = 'KY';
const FORM_TYPES = ['Form', 'Application', 'Applications', 'Application Only', 'Form/Rate/Application'];

await page.goto('https://filingaccess.serff.com/sfa/home/' + STATE);
await page.waitForLoadState('networkidle');
await page.waitForTimeout(600);

// Accept terms
const t1_links = await page.$$('a');
for (const a of t1_links) { const h = await a.getAttribute('href')||''; if (h.includes('userAgreement')) { await a.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(400);
const t1_btns = await page.$$('button');
for (const b of t1_btns) { if ((await b.textContent()||'').trim()==='Accept') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(1500);

// Select Business Type
await page.evaluate(() => document.getElementById('simpleSearch:businessType').click());
await page.waitForTimeout(300);
await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const li = items.find(i => i.textContent.includes('Life, Accident'));
    if (li) li.click();
});
await page.waitForTimeout(3500);

// Select MS TOI
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

// Search
const s1_btns = await page.$$('button');
for (const b of s1_btns) { if ((await b.textContent()||'').trim()==='Search') { await b.click(); break; } }
await page.waitForLoadState('networkidle');
await page.waitForTimeout(4000);

// Change rows per page to 100
const rpp_sel = await page.$('.ui-paginator-rpp-options');
if (rpp_sel) {
    await rpp_sel.selectOption('100');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(3000);
}

// Get total count
const total_text = await page.evaluate(() => document.body.innerText);
const total_match = total_text.match(/([0-9,]+)\s+Filing/);
const total_count = total_match ? parseInt(total_match[1].replace(/,/g,'')) : 0;

// Extract all rows - filter to Form/Application types only
const extract_rows = async () => {
    return await page.evaluate(() => {
        const table = document.querySelector('.ui-datatable table, table');
        if (!table) return [];
        const rows = Array.from(table.querySelectorAll('tbody tr'));
        return rows.map(tr => {
            const cells = Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim());
            return cells;
        });
    });
};

const headers = await page.evaluate(() => {
    const ths = Array.from(document.querySelectorAll('table th'));
    return ths.map(th => th.textContent.trim());
});

const form_types_set = new Set(['Form', 'Application', 'Applications', 'Application Only', 'Form/Rate/Application', 'Form/Rate', 'Form/Advertisement', 'Form -  M.U. (Medically underwritten)', 'Form -   Advertising', 'Form -  Other (Not M.U. OR G.I. Product)']);

// Get filing type column index
const filing_type_idx = headers.findIndex(h => h.includes('Filing Type'));
const serff_idx = headers.findIndex(h => h.includes('SERFF Tracking'));

let all_form_rows = [];
let page_num = 1;
let has_more = true;

while (has_more) {
    const rows = await extract_rows();
    const form_rows = rows.filter(row => {
        const ft = row[filing_type_idx] || '';
        return ft.toLowerCase().includes('form') || ft.toLowerCase().includes('application');
    });
    all_form_rows = all_form_rows.concat(form_rows.map(r => {
        const obj = {};
        headers.forEach((h, i) => { if (h) obj[h] = r[i] || ''; });
        return obj;
    }));
    
    // Check for next page
    const next_btn = await page.$('.ui-paginator-next:not(.ui-state-disabled)');
    if (next_btn && page_num < 20) {
        await next_btn.click();
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(2000);
        page_num++;
    } else {
        has_more = false;
    }
}

JSON.stringify({ state: STATE, total_in_serff: total_count, pages_scraped: page_num, form_rows_found: all_form_rows.length, rows: all_form_rows })
