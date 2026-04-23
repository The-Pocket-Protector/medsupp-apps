import asyncio
import re

# Business type selection
await page.evaluate("""() => {
    const bizWidget = PrimeFaces.widgets["widget_simpleSearch_businessType"];
    const select = document.getElementById("simpleSearch:businessType_input");
    for (let i = 0; i < select.options.length; i++) {
        if (select.options[i].text.includes("Life")) { bizWidget.selectValue(i); break; }
    }
}""")
await page.wait_for_timeout(2000)

# Select TOI using PrimeFaces widget API
result = await page.evaluate("""() => {
    const toiWidget = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    
    // Open panel
    toiWidget.show();
    
    // Panel items
    const panelItems = toiWidget.panel.find("li.ui-selectcheckboxmenu-item");
    const results = [];
    
    panelItems.each(function(i, li) {
        const label = li.querySelector("label");
        if (label) {
            const txt = label.textContent.trim();
            if (txt.startsWith("MS05I") || txt.startsWith("MS08I")) {
                const chkbox = $(li).find(".ui-chkbox-box");
                toiWidget.check(chkbox, true);
                results.push(txt.substring(0,40));
            }
        }
    });
    
    toiWidget.updateLabel();
    toiWidget.hide();
    
    const selected = Array.from(document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")).map(cb => cb.value);
    return { toggled: results, selected };
}""")
print("TOI result:", result)
