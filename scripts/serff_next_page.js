JSON.stringify(await (async () => {
    const has = !!document.querySelector && await page.evaluate(() => !!document.querySelector('.ui-paginator-next:not(.ui-state-disabled)'));
    if (has) {
        await page.click('.ui-paginator-next:not(.ui-state-disabled)');
        await page.waitForLoadState('networkidle');
        await page.waitForTimeout(1500);
    }
    return { ok: has };
})())
