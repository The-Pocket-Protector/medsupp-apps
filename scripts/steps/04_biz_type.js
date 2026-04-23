JSON.stringify(await page.evaluate(async () => {
    const bizEl = document.getElementById('simpleSearch:businessType');
    if (!bizEl) return { ok: false, error: 'bizEl not found' };
    bizEl.click();
    await new Promise(r => setTimeout(r, 350));
    const bizItems = Array.from(document.querySelectorAll('[id="simpleSearch:businessType_items"] li'));
    const lifeItem = bizItems.find(i => i.textContent.includes('Life, Accident'));
    if (lifeItem) lifeItem.click();
    await new Promise(r => setTimeout(r, 4000));
    const toiCount = document.querySelectorAll('input[name="simpleSearch:availableTois"]').length;
    return { ok: true, toiCount };
}))
