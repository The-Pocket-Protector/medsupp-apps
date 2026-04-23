JSON.stringify(await page.evaluate(() => {
    const w = PrimeFaces && PrimeFaces.widgets && PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    if (!w) return { ok: false, error: 'widget not found' };
    w.show();
    const toggled = [];
    w.panel.find("li.ui-selectcheckboxmenu-item").each(function(i, li) {
        const lbl = li.querySelector("label");
        if (lbl) {
            const txt = lbl.textContent.trim();
            if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                w.check(jQuery(li).find(".ui-chkbox-box"), true);
                toggled.push(txt.substring(0, 40));
            }
        }
    });
    w.updateLabel();
    w.hide();
    return { ok: true, toggled };
}))
