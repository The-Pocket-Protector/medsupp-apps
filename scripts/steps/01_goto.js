await page.goto(PAGE_GOTO_URL);
await page.waitForLoadState('networkidle');
JSON.stringify({url: page.url()})
