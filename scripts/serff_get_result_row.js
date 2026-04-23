// Step: We're on the results page already (from previous search)
// Get the HTML of the results table to understand link structure

const results_html = await page.evaluate(() => {
    const table = document.querySelector('.ui-datatable table, table');
    return table ? table.outerHTML.substring(0, 3000) : 'no table';
});

const all_links = await page.$$('a[href]');
const links_info = [];
for (const a of all_links) {
    const h = await a.getAttribute('href') || '';
    const t = (await a.textContent()||'').trim().substring(0, 80);
    if (h && h !== '#') links_info.push({h, t});
}

// Also check onclick handlers on table rows
const rows_info = await page.evaluate(() => {
    const trs = Array.from(document.querySelectorAll('tr'));
    return trs.slice(0,5).map(tr => ({
        onclick: tr.getAttribute('onclick') || '',
        cls: tr.className,
        text: tr.textContent.trim().substring(0,100)
    }));
});

JSON.stringify({ results_html: results_html.substring(0, 2000), links_info, rows_info })
