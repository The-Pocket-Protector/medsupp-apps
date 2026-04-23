// Playwright script to navigate SERFF for Alabama Med Supp filings
// Usage: firecrawl interact --node --code "$(cat this_file.js)" --timeout 120

(async () => {
  const page = context.page;
  
  // Step 1: Click Begin Search
  await page.click('a[href*="userAgreement"]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(1000);
  
  // Step 2: Click Accept on terms
  await page.click('button:text("Accept")');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);
  
  // Step 3: Select Business Type = Life
  const bizTypeSelect = await page.$('select');
  if (bizTypeSelect) {
    await bizTypeSelect.selectOption({ label: 'Life, Accident/Health, Annuity, Credit' });
  } else {
    // Try PrimeFaces dropdown
    await page.click('.ui-selectonemenu:first-child');
    await page.click('li:has-text("Life, Accident/Health, Annuity, Credit")');
  }
  await page.waitForTimeout(2000);
  
  // Step 4: Open TOI dropdown and select MS TOI codes
  // The TOI field is a multi-select panel
  const toiTrigger = await page.$('[id*="toi"], [class*="toi"]');
  if (toiTrigger) {
    await toiTrigger.click();
  } else {
    // Try clicking the "Type of Insurance" field
    await page.click('text="Type of Insurance"');
  }
  await page.waitForTimeout(1000);
  
  // Select MS05I and MS08I by text
  const ms05i = await page.$('text="MS05I Individual Medicare Supplement - Standard Plans"');
  const ms08i = await page.$('text="MS08I Individual Medicare Supplement - Standard Plans 2010"');
  
  if (ms05i) { await ms05i.click(); await page.waitForTimeout(500); }
  if (ms08i) { await ms08i.click(); await page.waitForTimeout(500); }
  
  // Close the TOI dropdown if there's a close button
  const closeBtn = await page.$('a:has-text("Close"), button:has-text("Close")');
  if (closeBtn) { await closeBtn.click(); await page.waitForTimeout(500); }
  
  // Step 5: Click Search
  await page.click('button:has-text("Search"), input[value="Search"]');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(3000);
  
  // Get result count
  const bodyText = await page.evaluate(() => document.body.innerText);
  const countMatch = bodyText.match(/(\d[\d,]*)\s+Filing\(s\)/);
  const count = countMatch ? countMatch[0] : 'unknown';
  
  // Get table rows
  const rows = await page.evaluate(() => {
    const table = document.querySelector('table[class*="result"], table[id*="result"], .ui-datatable table');
    if (!table) return [];
    const trs = Array.from(table.querySelectorAll('tr')).slice(1, 11); // skip header, get 10
    return trs.map(tr => {
      const cells = Array.from(tr.querySelectorAll('td')).map(td => td.innerText.trim());
      return cells.join(' | ');
    });
  });
  
  return { count, rows, url: page.url() };
})()
