// We're on filingSummary.xhtml - get the full page content and document links
const full_body = await page.evaluate(() => document.body.innerText);

// Find all links - especially PDF/document links
const all_links = await page.$$('a[href]');
const all_link_info = [];
for (const a of all_links) {
    const h = await a.getAttribute('href') || '';
    const t = (await a.textContent()||'').trim().substring(0, 100);
    all_link_info.push({h, t});
}

// Check for any download buttons or document sections
const doc_section = await page.evaluate(() => {
    const sections = Array.from(document.querySelectorAll('h2,h3,h4,fieldset,section'));
    const docSec = sections.find(s => s.textContent.includes('Document') || s.textContent.includes('Attachment') || s.textContent.includes('Form'));
    return docSec ? docSec.outerHTML.substring(0,2000) : 'no doc section found';
});

// Get all buttons
const btns_info = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('button,input[type=button],input[type=submit]'))
        .map(b => ({text: b.textContent.trim().substring(0,50), id: b.id, cls: b.className.substring(0,50)}));
});

JSON.stringify({ 
    body: full_body.substring(0, 2000), 
    links: all_link_info, 
    doc_section: doc_section.substring(0, 1500),
    buttons: btns_info
})
