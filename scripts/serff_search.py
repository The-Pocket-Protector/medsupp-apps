import re

# Click Search button
await page.click("button:has-text('Search')")
await page.wait_for_load_state("networkidle")
await page.wait_for_timeout(3000)

# Get total count
body = await page.evaluate("() => document.body.innerText")
count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body)
print("Count:", count_match.group(0) if count_match else "not found")
print("URL:", page.url)

# Extract table data
rows = await page.evaluate("""() => {
    // Find results table
    const tables = Array.from(document.querySelectorAll("table"));
    const dataTable = tables.find(t => t.querySelector("th"));
    if (!dataTable) return {error: "no table found"};
    
    const headers = Array.from(dataTable.querySelectorAll("th")).map(th => th.textContent.trim());
    const trs = Array.from(dataTable.querySelectorAll("tbody tr")).slice(0, 20);
    const rows = trs.map(tr => {
        const cells = Array.from(tr.querySelectorAll("td")).map(td => td.textContent.trim());
        return cells;
    });
    return { headers, rows };
}""")
print("Headers:", rows.get("headers") if isinstance(rows, dict) else rows)
print("First 5 rows:")
if isinstance(rows, dict) and "rows" in rows:
    for r in rows["rows"][:5]:
        print(" |", " | ".join(r))
