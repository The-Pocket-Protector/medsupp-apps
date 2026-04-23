#!/usr/bin/env python3
"""
SERFF Application-Only Scraper.
Filters for Application/Application Only filing types that are Approved or Filed.
Builds output for Airtable + Excel tracker.
"""

import json
import time
import re
import sys
import requests
from pathlib import Path

API_KEY = "fc-94fa12dd36444846851cfcd972c23194"
API_URL = "https://api.firecrawl.dev"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = OUTPUT_DIR / "app_filings_results.json"

# All SERFF states
SERFF_STATES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "DC", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY"
]

# Filing types that represent paper applications
APP_FILING_TYPES = {
    "Application",
    "Application Only",
    "Applications",
    "Form/Rate/Application",
}

# Statuses that mean approved or filed (not withdrawn/disapproved)
APPROVED_STATUSES = {
    "Closed - Approved",
    "Closed - APPROVED",
    "Closed - Approved As Amended",
    "Closed - Approved as Amended",
    "Closed - Approved as revised",
    "Closed - Approved-Closed",
    "Closed - Approved and Filed",
    "Closed - Filed",
    "Closed - FILED",
    "Closed - FILED FOR USE",
    "Closed - FILED FOR USE (Pursuant to U.C.A 31A-21-201)",
    "Closed - Filed - Approved",
    "Closed - Filed - Approved with Stipulations",
    "Closed - Filed As Amended",
    "Closed - Filed Only",
    "Closed - Filed-Closed",
    "Closed - Filed as information",
    "Closed - (APP)Form Approval",
    "Closed - (RAP)Rate Approval",
    "Closed - (ACK)Acknowledge and File",
    "Closed - (ACL)Acknowledge and File Letter",
    "Closed - (01) Filed",
    "Closed - (02) Approved",
    "Closed - Accepted/Filed",
    "Closed - Acknowledged",
    "Closed - Reviewed and Filed",
    "Closed - Reviewed",
    "Closed - REVIEWED AND FILED FOR USE",
    "Closed - Rates Placed on File",
    "Closed - RATES FILED",
    "Closed - Received and Filed",
}


JS_NAVIGATE = """
await page.goto("{state_url}");
await page.waitForLoadState("networkidle");
await page.waitForTimeout(1000);
page.url()
"""

JS_BEGIN_SEARCH = """
const nav_links = await page.$$("a");
let nav_found = false;
for (const nav_a of nav_links) {
    const nav_href = await nav_a.getAttribute("href") || "";
    const nav_txt = await nav_a.textContent() || "";
    if (nav_href.includes("userAgreement") || nav_txt.includes("Begin Search")) {
        await nav_a.click();
        nav_found = true;
        break;
    }
}
await page.waitForLoadState("networkidle");
await page.waitForTimeout(800);
"begin:" + nav_found + "|" + page.url()
"""

JS_ACCEPT = """
const acc_btns = await page.$$("button");
let acc_clicked = false;
for (const acc_btn of acc_btns) {
    const acc_txt = await acc_btn.textContent() || "";
    if (acc_txt.trim() === "Accept") {
        await acc_btn.click();
        acc_clicked = true;
        break;
    }
}
await page.waitForLoadState("networkidle");
await page.waitForTimeout(2000);
"accept:" + acc_clicked + "|" + page.url()
"""

JS_SELECT_BIZTYPE = """
const biz_menu = await page.evaluate(() => document.getElementById("simpleSearch:businessType"));
if (!biz_menu) throw new Error("bizMenu not found");
await page.evaluate(() => document.getElementById("simpleSearch:businessType").click());
await page.waitForTimeout(400);

const biz_life_item = await page.evaluate(() => {
    const items = Array.from(document.querySelectorAll("[id='simpleSearch:businessType_items'] li"));
    return items.findIndex(li => li.textContent.includes("Life, Accident"));
});
if (biz_life_item < 0) throw new Error("Life option not found");
await page.evaluate((idx) => {
    const items = Array.from(document.querySelectorAll("[id='simpleSearch:businessType_items'] li"));
    items[idx].click();
}, biz_life_item);
await page.waitForTimeout(4000);
const biz_toi_count = await page.evaluate(() => document.querySelectorAll("input[name='simpleSearch:availableTois']").length);
"biz:Life|toiCount:" + biz_toi_count
"""

JS_SELECT_TOI = """
const toi_res = await page.evaluate(() => {
    const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
    if (!w) return { error: "widget not found" };
    w.show();
    const toi_items = w.panel.find("li.ui-selectcheckboxmenu-item");
    const toi_toggled = [];
    toi_items.each(function(i, li) {
        const lbl = li.querySelector("label");
        if (lbl) {
            const txt = lbl.textContent.trim();
            if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                w.check(jQuery(li).find(".ui-chkbox-box"), true);
                toi_toggled.push(txt.substring(0, 50));
            }
        }
    });
    w.updateLabel();
    w.hide();
    const toi_sel = Array.from(document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")).map(cb => cb.value);
    return { toggled: toi_toggled, selected: toi_sel };
});
JSON.stringify(toi_res)
"""

# Try to filter by Filing Type = Application on the search form
JS_SELECT_FILING_TYPE_APP = """
const ft_res = await page.evaluate(() => {
    // Look for a filing type dropdown or multiselect
    const ftEl = document.getElementById("simpleSearch:filingType") ||
                 document.getElementById("simpleSearch:availableFilingTypes") ||
                 document.querySelector("[id*='filingType']");
    if (!ftEl) return { found: false, note: "no filing type element" };
    return { found: true, tag: ftEl.tagName, id: ftEl.id };
});
JSON.stringify(ft_res)
"""

JS_SEARCH_AND_GET_COUNT = """
const srch_btns = await page.$$("button");
let srch_clicked = false;
for (const srch_btn of srch_btns) {
    const srch_txt = await srch_btn.textContent() || "";
    if (srch_txt.trim() === "Search") {
        await srch_btn.click();
        srch_clicked = true;
        break;
    }
}
await page.waitForLoadState("networkidle");
await page.waitForTimeout(5000);
const srch_body = await page.evaluate(() => document.body.innerText);
const srch_cm = srch_body.match(/([0-9,]+) Filing/);
const srch_count = srch_cm ? srch_cm[0] : "NOT FOUND";
"clicked:" + srch_clicked + "|count:" + srch_count + "|url:" + page.url()
"""

JS_CHANGE_ROWS_100 = """
const rpp = await page.$(".ui-paginator-rpp-options, select[id*='rowsPerPage'], .rowsPerPage select");
if (rpp) {
    await rpp.selectOption("100");
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);
    "rpp:100"
} else {
    "rpp:not found"
}
"""

JS_EXTRACT_TABLE = """
const tbl_data = await page.evaluate(() => {
    const tables = Array.from(document.querySelectorAll("table"));
    const dt = tables.find(t => t.querySelector("th"));
    if (!dt) return { error: "no table", cnt: tables.length };
    const headers = Array.from(dt.querySelectorAll("th")).map(th => th.textContent.trim());
    const trs = Array.from(dt.querySelectorAll("tbody tr"));
    const rows = trs.map(tr => Array.from(tr.querySelectorAll("td")).map(td => td.textContent.trim()));
    return { headers, rows, total: trs.length };
});
JSON.stringify(tbl_data)
"""

# Get all pages - paginate through remaining
JS_GET_NEXT_PAGE = """
const np_btn = await page.$(".ui-paginator-next:not(.ui-state-disabled)");
if (np_btn) {
    await np_btn.click();
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(3000);
    "next:clicked"
} else {
    "next:disabled"
}
"""


def create_session():
    resp = requests.post(f"{API_URL}/v2/browser", headers=HEADERS, json={}, timeout=30)
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"Failed to create session: {data}")
    return data["id"]


def execute(session_id, code, timeout=60):
    resp = requests.post(
        f"{API_URL}/v2/browser/{session_id}/execute",
        headers=HEADERS,
        json={"code": code},
        timeout=timeout + 10
    )
    return resp.json()


def delete_session(session_id):
    try:
        requests.delete(f"{API_URL}/v2/browser/{session_id}", headers=HEADERS, timeout=10)
    except Exception:
        pass


def is_app_filing(filing):
    ft = filing.get("Filing Type", "")
    fs = filing.get("Filing Status", "")
    return ft in APP_FILING_TYPES and fs in APPROVED_STATUSES


def scrape_state(state):
    result = {"state": state, "status": "pending", "filings": [], "all_filings": [], "errors": []}
    session_id = None

    try:
        session_id = create_session()
        print(f"  [{state}] Session: {session_id}")
        time.sleep(2)

        state_url = f"https://filingaccess.serff.com/sfa/home/{state}"
        r = execute(session_id, JS_NAVIGATE.format(state_url=state_url), timeout=30)
        if r.get("stderr"):
            raise Exception(f"Nav error: {r['stderr'][:150]}")

        r = execute(session_id, JS_BEGIN_SEARCH, timeout=30)
        if r.get("stderr"):
            raise Exception(f"BeginSearch error: {r['stderr'][:150]}")

        r = execute(session_id, JS_ACCEPT, timeout=30)
        if r.get("stderr"):
            raise Exception(f"Accept error: {r['stderr'][:150]}")

        r = execute(session_id, JS_SELECT_BIZTYPE, timeout=30)
        if r.get("stderr"):
            raise Exception(f"BizType error: {r['stderr'][:150]}")

        r = execute(session_id, JS_SELECT_TOI, timeout=30)
        if r.get("stderr"):
            print(f"  [{state}] TOI stderr: {r['stderr'][:150]}")
        toi_result = json.loads(r.get("result") or "{}")
        result["toi_result"] = toi_result
        print(f"  [{state}] TOI: {toi_result.get('toggled', [])}")

        if not toi_result.get("selected"):
            result["errors"].append(f"TOI not selected: {toi_result}")

        # Check if filing type filter is available
        r = execute(session_id, JS_SELECT_FILING_TYPE_APP, timeout=20)
        ft_check = json.loads(r.get("result") or "{}")
        print(f"  [{state}] FilingTypeField: {ft_check}")
        result["filing_type_field"] = ft_check

        r = execute(session_id, JS_SEARCH_AND_GET_COUNT, timeout=70)
        if r.get("stderr"):
            print(f"  [{state}] Search stderr: {r['stderr'][:150]}")
        search_out = r.get("result", "")
        print(f"  [{state}] Search: {search_out}")

        count_match = re.search(r'([0-9,]+) Filing', search_out)
        if count_match:
            result["total_filings_str"] = count_match.group(0) + "(s)"

        # Try to change rows per page to 100
        r = execute(session_id, JS_CHANGE_ROWS_100, timeout=20)
        print(f"  [{state}] RowsPerPage: {r.get('result')}")

        # Paginate through ALL pages to find application filings
        page_num = 1
        all_filings_raw = []
        app_filings = []

        while True:
            r = execute(session_id, JS_EXTRACT_TABLE, timeout=30)
            table_data = json.loads(r.get("result") or "{}")
            rows_this_page = table_data.get("total", 0)
            print(f"  [{state}] Page {page_num}: {rows_this_page} rows")

            if "rows" in table_data:
                headers = table_data.get("headers", [])
                for row in table_data["rows"]:
                    filing = {headers[i] if i < len(headers) else f"col{i}": val for i, val in enumerate(row)}
                    all_filings_raw.append(filing)
                    if is_app_filing(filing):
                        app_filings.append(filing)

            if rows_this_page == 0:
                break

            # Try next page
            r = execute(session_id, JS_GET_NEXT_PAGE, timeout=30)
            next_result = r.get("result", "")
            print(f"  [{state}] NextPage: {next_result}")
            if "disabled" in next_result or "clicked" not in next_result:
                break
            page_num += 1
            if page_num > 20:  # Safety cap
                print(f"  [{state}] Hit 20-page cap")
                break

        result["all_filings"] = all_filings_raw
        result["filings"] = app_filings
        result["pages_scraped"] = page_num
        result["status"] = "complete"
        print(f"  [{state}] Done: {len(all_filings_raw)} total, {len(app_filings)} app filings")

    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e)[:300])
        print(f"  [{state}] EXCEPTION: {e}")

    finally:
        if session_id:
            delete_session(session_id)
            time.sleep(2)

    return result


def main():
    existing = {}
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            existing = {r["state"]: r for r in data}

    target_states = sys.argv[1:] if len(sys.argv) > 1 else SERFF_STATES
    remaining = [s for s in target_states if existing.get(s, {}).get("status") != "complete"]

    print(f"Scraping {len(remaining)} states for APPLICATION filings: {remaining}")
    print()

    for i, state in enumerate(remaining):
        print(f"\n[{i+1}/{len(remaining)}] {state}...")
        result = scrape_state(state)
        existing[state] = result

        with open(RESULTS_FILE, "w") as f:
            json.dump(list(existing.values()), f, indent=2)

        if result.get("status") != "complete":
            print(f"  FAILED: {result.get('errors', [])[:1]}")

        time.sleep(5)

    results = list(existing.values())
    complete = [r for r in results if r.get("status") == "complete"]
    total_app_filings = sum(len(r.get("filings", [])) for r in complete)
    print(f"\n{'='*60}")
    print(f"DONE: {len(complete)}/{len(results)} complete")
    print(f"Total application filings found: {total_app_filings}")
    for r in complete:
        app_count = len(r.get("filings", []))
        if app_count > 0:
            print(f"  {r['state']}: {app_count} app filings")


if __name__ == "__main__":
    main()
