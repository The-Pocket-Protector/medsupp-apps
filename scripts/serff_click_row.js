// Click the first data row in the results table
const data_rows = await page.$$('table tbody tr');
let clicked_row = false;
if (data_rows.length > 0) {
    await data_rows[0].click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    clicked_row = true;
}

const new_url = page.url();
const new_body = await page.evaluate(() => document.body.innerText.substring(0, 800));

// Also check for any modal/overlay that appeared
const modals = await page.$$('.ui-dialog, .ui-overlay, .modal');
const modal_count = modals.length;

JSON.stringify({ clicked_row, new_url, modal_count, new_body })
