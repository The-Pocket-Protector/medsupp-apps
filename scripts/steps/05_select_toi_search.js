JSON.stringify(await page.evaluate(async () => {
    // Select MS TOI
    const w = PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    if (w) {
        w.show();
        w.panel.find("li.ui-selectcheckboxmenu-item").each(function(i, li) {
            const lbl = li.querySelector("label");
            if (lbl) {
                const txt = lbl.textContent.trim();
                if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                    w.check(jQuery(li).find(".ui-chkbox-box"), true);
                }
            }
        });
        w.updateLabel();
        w.hide();
    }
    await new Promise(r => setTimeout(r, 400));

    // Click Search
    const searchBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Search');
    if (searchBtn) searchBtn.click();
    await new Promise(r => setTimeout(r, 5000));

    // Set 100 rows
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
    return { total, hdrs };
}))
