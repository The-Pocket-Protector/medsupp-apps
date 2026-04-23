JSON.stringify(await page.evaluate(async () => {
    const btn = document.querySelector('.ui-paginator-next:not(.ui-state-disabled)');
    if (!btn) return { ok: false };
    btn.click();
    await new Promise(r => setTimeout(r, 3000));
    return { ok: true };
}))
