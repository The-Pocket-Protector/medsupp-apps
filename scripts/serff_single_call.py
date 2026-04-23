import re
import json

STATE = "AL"

# ── Step 1: Navigate ──────────────────────────────────────────────────────
await page.click("a[href*='userAgreement']")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(800)

await page.click("button:has-text('Accept')")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(2000)

print(f"[{STATE}] On search form. URL:", page.url)

# ── Step 2: Select Business Type ──────────────────────────────────────────
await page.locator("#simpleSearch\\:businessType").click()
await page.wait_for_timeout(400)
await page.locator("#simpleSearch\\:businessType_items li:has-text('Life, Accident')").click()
await page.wait_for_timeout(3000)

biz_label = await page.evaluate("""() => {
    const e = document.querySelector('#simpleSearch\\\\:businessType .ui-selectonemenu-label');
    return e ? e.textContent.trim() : 'n/a';
}""")
print(f"[{STATE}] Biz type:", biz_label)

# ── Step 3: Select TOI (MS05I + MS08I) ───────────────────────────────────
await page.evaluate("""() => {
    const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    w.show();
    w.panel.find("li.ui-selectcheckboxmenu-item").each(function(i, li) {
        const lbl = li.querySelector("label");
        if (lbl) {
            const txt = lbl.textContent.trim();
            if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                w.check($(li).find(".ui-chkbox-box"), true);
            }
        }
    });
    w.updateLabel();
    w.hide();
}""")
await page.wait_for_timeout(500)

toi_sel = await page.evaluate("""() =>
    Array.from(document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")).map(cb => cb.value)
""")
print(f"[{STATE}] TOI:", toi_sel)

# ── Step 4: Submit search via form ────────────────────────────────────────
# Get the search button info
search_info = await page.evaluate("""() => {
    const btns = Array.from(document.querySelectorAll("button"));
    const sb = btns.find(b => b.textContent.trim() === "Search");
    return sb ? { id: sb.id, type: sb.type, cls: sb.className, onclick: sb.onclick ? sb.onclick.toString().substring(0,100) : "none" } : "not found";
}""")
print(f"[{STATE}] Search btn:", search_info)

# Click with force to bypass any CSS overlay issues
await page.locator("button:has-text('Search')").click(force=True)
await page.wait_for_timeout(500)

# Also try submitting via JS as backup
js_submit = await page.evaluate("""() => {
    const btn = Array.from(document.querySelectorAll("button")).find(b => b.textContent.trim() === "Search");
    if (btn) { btn.click(); return "clicked"; }
    return "no button";
}""")
print(f"[{STATE}] JS submit:", js_submit)

await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(5000)

print(f"[{STATE}] URL after search:", page.url)

# ── Step 5: Extract results ───────────────────────────────────────────────
body = await page.evaluate("() => document.body.innerText")
count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body)
print(f"[{STATE}] Count:", count_match.group(0) if count_match else "NOT FOUND")
print(f"[{STATE}] Body snippet:", body[:600])
