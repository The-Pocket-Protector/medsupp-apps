// Navigate and get to filing summary - we're already there
// Use Playwright download API properly

// Select current versions
const sel_links = await page.$$('a');
for (const a of sel_links) {
    const t = (await a.textContent()||'').trim();
    if (t === 'Select Current Version Only') { 
        await a.click(); 
        await page.waitForTimeout(500); 
        break; 
    }
}

// Use Promise.all to wait for download and click simultaneously
try {
    const download_promise = page.waitForEvent('download', { timeout: 20000 });
    const click_promise = page.click('#summaryForm\\:downloadLink');
    
    const [download_result] = await Promise.all([download_promise, click_promise]);
    
    const filename = download_result.suggestedFilename();
    const download_path = await download_result.path();
    
    // Read the downloaded file
    const fs = require('fs');
    if (download_path && fs.existsSync(download_path)) {
        const content = fs.readFileSync(download_path);
        const base64 = content.toString('base64');
        JSON.stringify({ 
            success: true, 
            filename, 
            size_bytes: content.length,
            base64_preview: base64.substring(0, 100)
        })
    } else {
        JSON.stringify({ success: false, error: 'no path', filename, path: download_path })
    }
} catch(e) {
    JSON.stringify({ success: false, error: e.message, page_url: page.url() })
}
