JSON.stringify(await page.evaluate(async () => {
    const rpp = document.querySelector('.ui-paginator-rpp-options');
    if (rpp && rpp.value !== '100') {
        rpp.value = '100';
        rpp.dispatchEvent(new Event('change', {bubbles: true}));
        await new Promise(r => setTimeout(r, 3000));
    }
    const body = document.body.innerText;
    const m = body.match(/([0-9,]+)\s+Filing/);
    const total = m ? parseInt(m[1].replace(/,/g,'')) : 0;
    const hdrs = Array.from(document.querySelectorAll('table th')).map(th => th.textContent.trim());
    return { total, hdrs, has_rpp: !!rpp };
}))
