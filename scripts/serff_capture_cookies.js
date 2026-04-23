// Capture all cookies and the full POST body for the download request
const cookies = await page.context().cookies();

// Also get the ViewState (JSF hidden field needed for form POST)
const view_state = await page.evaluate(() => {
    const vs = document.querySelector('input[name="javax.faces.ViewState"]');
    return vs ? vs.value : null;
});

// Get the filing ID from URL
const filing_id = new URL(page.url()).searchParams.get('filingId');

// Get all attachment IDs from the checkboxes
const attachment_data = await page.evaluate(() => {
    const checkboxes = Array.from(document.querySelectorAll('input[name*="selectedAttachmentIds"], input[name*="AttachmentId"]'));
    return checkboxes.map(cb => ({
        name: cb.name,
        value: cb.value,
        checked: cb.checked,
        type: cb.type
    }));
});

JSON.stringify({ 
    cookie_count: cookies.length,
    cookies: cookies.map(c => c.name + '=' + c.value),
    view_state: view_state ? view_state.substring(0, 50) + '...' : null,
    filing_id,
    attachment_count: attachment_data.length,
    first_5_attachments: attachment_data.slice(0, 5)
})
