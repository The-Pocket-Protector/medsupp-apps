import re

# Select TOI using PrimeFaces check() method
# We need to open the panel, click items, then search
result = await page.evaluate("""() => {
    const toiWidget = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    
    // Open panel
    toiWidget.show();
    
    // Find and check MS05I and MS08I items
    const panelItems = toiWidget.panel.find("li.ui-selectcheckboxmenu-item");
    const toggled = [];
    
    panelItems.each(function(idx, li) {
        const label = li.querySelector("label");
        if (label) {
            const txt = label.textContent.trim();
            if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                const chkbox = $(li).find(".ui-chkbox-box");
                toiWidget.check(chkbox, true);
                toggled.push(txt.substring(0, 50));
            }
        }
    });
    
    toiWidget.updateLabel();
    toiWidget.hide();
    
    const selected = Array.from(
        document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")
    ).map(cb => cb.value);
    
    const labelText = document.querySelector(".ui-selectcheckboxmenu-label");
    return { 
        toggled, 
        selected, 
        labelText: labelText ? labelText.textContent.trim() : "n/a"
    };
}""")
print("TOI selection result:", result)
