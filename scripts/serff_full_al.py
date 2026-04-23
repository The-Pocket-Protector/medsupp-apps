import re
import json

STATE = "AL"

# ── Step 1: Navigate to homepage and start scrape ─────────────────────────
# (This script runs after firecrawl scrape https://filingaccess.serff.com/sfa/home/AL)

# Step 2: Click Begin Search link
begin_link = page.locator("a[href*='userAgreement']")
await begin_link.click()
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(1000)

# Step 3: Click Accept on terms page
accept_btn = page.locator("button:has-text('Accept')")
await accept_btn.click()
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(2000)

print("On search form. URL:", page.url)

# Step 4: Click the Business Type PrimeFaces selectOneMenu
biz_menu = page.locator("#simpleSearch\\:businessType")
await biz_menu.click()
await page.wait_for_timeout(500)

# Click Life option
life_opt = page.locator("#simpleSearch\\:businessType_items li:has-text('Life, Accident')")
await life_opt.click()
await page.wait_for_timeout(3000)  # AJAX loads TOI dropdown

biz_label = await page.evaluate("""() => {
    const el = document.querySelector("#simpleSearch\\\\:businessType .ui-selectonemenu-label");
    return el ? el.textContent.trim() : "not found";
}""")
toi_count = await page.evaluate("() => document.querySelectorAll(\"input[name='simpleSearch:availableTois']\").length")
print(f"Biz type: {biz_label} | TOI options: {toi_count}")

# Step 5: Select MS TOI codes using PrimeFaces widget
toi_result = await page.evaluate("""() => {
    const toiWidget = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    toiWidget.show();
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
    return { toggled, selected };
}""")
print("TOI selected:", toi_result)

# Step 6: Click Search
await page.click("button:has-text('Search')")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(4000)

# Step 7: Get results
body_text = await page.evaluate("() => document.body.innerText")
count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body_text)
total = count_match.group(0) if count_match else "not found"
print(f"Total results: {total}")
print("URL after search:", page.url)

# Step 8: Extract table data
table_data = await page.evaluate("""() => {
    const tables = Array.from(document.querySelectorAll("table"));
    const dataTable = tables.find(t => t.querySelector("th"));
    if (!dataTable) return {error: "no table found", tableCount: tables.length};
    
    const headers = Array.from(dataTable.querySelectorAll("th")).map(th => th.textContent.trim());
    const trs = Array.from(dataTable.querySelectorAll("tbody tr")).slice(0, 10);
    const rows = trs.map(tr => {
        return Array.from(tr.querySelectorAll("td")).map(td => td.textContent.trim());
    });
    return { headers, rows, totalRows: dataTable.querySelectorAll("tbody tr").length };
}""")
print("Table data:", json.dumps(table_data, indent=2))
