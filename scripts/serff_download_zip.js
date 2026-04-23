// We're on the filing summary page
// Try clicking "Select Current Version Only" first, then Download Zip File

// First select current versions only
const select_btns = await page.$$('a, button');
for (const b of select_btns) {
    const t = (await b.textContent()||'').trim();
    if (t === 'Select Current Version Only') {
        await b.click();
        await page.waitForTimeout(500);
        break;
    }
}

// Set up download listener
const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 15000 }).catch(() => null),
    page.click('#summaryForm\\:downloadLink')
]);

let download_info = { found: false };
if (download) {
    const suggested_filename = download.suggestedFilename();
    const path = await download.path();
    download_info = { found: true, filename: suggested_filename, path };
    // Save to workspace
    const save_path = '/tmp/serff_test_' + suggested_filename;
    await download.saveAs(save_path);
    download_info.saved = save_path;
} else {
    // Check what happened to the page
    await page.waitForTimeout(2000);
    download_info.url_after = page.url();
    download_info.body = await page.evaluate(() => document.body.innerText.substring(0, 300));
}

JSON.stringify(download_info)
