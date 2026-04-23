import re
import json

# Step 1: Begin Search + Accept
await page.click("a[href*='userAgreement']")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(800)
await page.click("button:has-text('Accept')")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(2000)

# Step 2: Business Type
await page.locator("#simpleSearch\\:businessType").click()
await page.wait_for_timeout(400)
await page.locator("#simpleSearch\\:businessType_items li:has-text('Life, Accident')").click()
await page.wait_for_timeout(3000)

print("BizType:", await page.evaluate("""() => { 
    const e = document.querySelector('#simpleSearch\\\\:businessType .ui-selectonemenu-label'); 
    return e ? e.textContent.trim() : 'n/a'; 
}"""))

# Step 3: Select TOI via PrimeFaces widget
await page.evaluate("""() => {
    const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    w.show();
    w.panel.find("li.ui-selectcheckboxmenu-item").each(function(i, li) {
        const lbl = li.querySelector("label");
        if (lbl && (lbl.textContent.trim().indexOf("MS05I") === 0 || lbl.textContent.trim().indexOf("MS08I") === 0)) {
            w.check($(li).find(".ui-chkbox-box"), true);
        }
    });
    w.updateLabel();
    w.hide();
}""")
await page.wait_for_timeout(500)

# Verify TOI
toi_selected = await page.evaluate("""() => 
    Array.from(document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")).map(cb => cb.value)
""")
print("TOI selected:", toi_selected)

# Step 4: Check validation state - get search button info
btn_info = await page.evaluate("""() => {
    const btn = document.querySelector("button:contains('Search')") || 
                Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Search");
    return btn ? { id: btn.id, disabled: btn.disabled, cls: btn.className } : { error: "no button" };
}""")
print("Search btn:", btn_info)

# Step 5: Click search and wait longer
search_btn = page.locator("button:has-text('Search')").last()
await search_btn.click()
await page.wait_for_timeout(6000)

print("URL after search:", page.url)

# Check for errors or results
body = await page.evaluate("() => document.body.innerText")
# Look for filing count OR error messages
count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body)
error_match = re.search(r'(You must|No\s+\w+\s+found|error)', body, re.IGNORECASE)
print("Count:", count_match.group(0) if count_match else "not found")
print("Error:", error_match.group(0) if error_match else "none")
print("Body snippet:", body[:500])
