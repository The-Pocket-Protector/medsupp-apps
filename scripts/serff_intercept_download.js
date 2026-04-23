// Intercept the download request to capture the URL/POST params
// Set up request interceptor before clicking
let captured_request = null;

await page.route('**', async (route) => {
    const req = route.request();
    const url = req.url();
    const method = req.method();
    const post_data = req.postData() || '';
    
    if (url.includes('download') || url.includes('Download') || url.includes('.zip') || 
        post_data.includes('download') || post_data.includes('Download')) {
        captured_request = { url, method, post_data: post_data.substring(0, 500) };
    }
    await route.continue();
});

// Select current versions first
const all_as = await page.$$('a');
for (const a of all_as) {
    const t = (await a.textContent()||'').trim();
    if (t === 'Select Current Version Only') { await a.click(); await page.waitForTimeout(300); break; }
}

// Click download button
await page.click('#summaryForm\\:downloadLink').catch(() => {});
await page.waitForTimeout(3000);

// Also capture the full network log
const requests_log = await page.evaluate(() => {
    // Check if there's a download iframe or redirect
    const iframes = Array.from(document.querySelectorAll('iframe'));
    return { 
        iframes: iframes.map(f => f.src || f.id),
        url: window.location.href
    };
});

JSON.stringify({ captured_request, requests_log, page_url: page.url() })
