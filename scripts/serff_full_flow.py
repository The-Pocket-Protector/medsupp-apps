import re

# Step 1: Click the PrimeFaces selectOneMenu visual trigger for Business Type
# The trigger is the div.ui-selectonemenu itself (or its trigger button)
biz_menu = page.locator("#simpleSearch\\:businessType")
await biz_menu.click()
await page.wait_for_timeout(500)

# Step 2: Click on the Life option in the overlay panel
life_opt = page.locator("#simpleSearch\\:businessType_items li:has-text('Life, Accident')")
await life_opt.click()
await page.wait_for_timeout(3000)  # Wait for AJAX to populate TOI dropdown

# Verify selection
biz_label = await page.evaluate("""() => {
    const el = document.querySelector("#simpleSearch\\\\:businessType .ui-selectonemenu-label");
    return el ? el.textContent.trim() : "not found";
}""")
print("Business type label:", biz_label)

# Check TOI count (should now be populated)
toi_count = await page.evaluate("""() => {
    const inputs = document.querySelectorAll("input[name='simpleSearch:availableTois']");
    return inputs.length;
}""")
print("TOI options count:", toi_count)
