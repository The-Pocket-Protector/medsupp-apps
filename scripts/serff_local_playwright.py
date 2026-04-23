#!/usr/bin/env python3
"""
SERFF Multi-State Scraper using local Playwright.
Scrapes Medicare Supplement filings (TOI: MS05I + MS08I) for all 48 SERFF states.
"""

import json
import time
import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = OUTPUT_DIR / "all_states_results_v2.json"

SERFF_STATES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "DC", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY"
]


def scrape_state(page, state):
    """Scrape one state's Medicare Supplement filings."""
    result = {"state": state, "status": "pending", "filings": [], "errors": []}
    
    try:
        # Navigate to state homepage
        page.goto(f"https://filingaccess.serff.com/sfa/home/{state}", timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Click Begin Search (link to userAgreement)
        begin_links = page.query_selector_all("a")
        begin_link = None
        for a in begin_links:
            href = a.get_attribute("href") or ""
            text = a.text_content() or ""
            if "userAgreement" in href or "Begin Search" in text:
                begin_link = a
                break
        
        if not begin_link:
            result["status"] = "error"
            result["errors"].append("Begin Search link not found")
            return result
        
        begin_link.click()
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        # Click Accept button
        accept_btn = page.query_selector("button")
        btns = page.query_selector_all("button")
        accept_btn = None
        for btn in btns:
            if "Accept" in (btn.text_content() or ""):
                accept_btn = btn
                break
        
        if not accept_btn:
            result["status"] = "error"
            result["errors"].append("Accept button not found")
            return result
        
        accept_btn.click()
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        
        # Select Business Type = Life, Accident/Health, Annuity, Credit
        # The PrimeFaces selectOneMenu - click the label to open
        biz_menu = page.query_selector("[id*='businessType']")
        if not biz_menu:
            result["status"] = "error"
            result["errors"].append("Business Type dropdown not found")
            return result
        
        biz_menu.click()
        time.sleep(0.5)
        
        # Click the Life option in the panel
        life_items = page.query_selector_all("[id*='businessType_items'] li")
        life_item = None
        for li in life_items:
            if "Life" in (li.text_content() or ""):
                life_item = li
                break
        
        if not life_item:
            result["status"] = "error"
            result["errors"].append("Life option not found in Business Type")
            return result
        
        life_item.click()
        time.sleep(3)  # Wait for AJAX to load TOI options
        
        # Select TOI: MS05I and MS08I using PrimeFaces JS API
        toi_result = page.evaluate("""() => {
            const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
            if (!w) return { error: "widget not found" };
            
            w.show();
            const panelItems = w.panel.find("li.ui-selectcheckboxmenu-item");
            const toggled = [];
            
            panelItems.each(function(i, li) {
                const lbl = li.querySelector("label");
                if (lbl) {
                    const txt = lbl.textContent.trim();
                    if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                        w.check($(li).find(".ui-chkbox-box"), true);
                        toggled.push(txt.substring(0, 60));
                    }
                }
            });
            
            w.updateLabel();
            w.hide();
            
            const selected = Array.from(
                document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")
            ).map(cb => cb.value);
            
            return { toggled, selected };
        }""")
        
        if not toi_result.get("selected"):
            result["errors"].append(f"TOI selection failed: {toi_result}")
        
        time.sleep(0.5)
        
        # Click Search button
        btns = page.query_selector_all("button")
        search_btn = None
        for btn in btns:
            if btn.text_content().strip() == "Search":
                search_btn = btn
                break
        
        if not search_btn:
            result["status"] = "error"
            result["errors"].append("Search button not found")
            return result
        
        search_btn.click()
        page.wait_for_load_state("networkidle")
        time.sleep(5)
        
        # Extract results
        body_text = page.evaluate("() => document.body.innerText")
        count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body_text)
        
        if count_match:
            total_str = count_match.group(0)
            result["total_filings_str"] = total_str
            print(f"  [{state}] {total_str}")
        else:
            # Check for "no results" message or errors
            if "no filing" in body_text.lower() or "0 filing" in body_text.lower():
                result["total_filings_str"] = "0 Filing(s)"
                print(f"  [{state}] 0 results")
            else:
                result["errors"].append("Count not found in results page")
                print(f"  [{state}] Count not found. Body: {body_text[:200]}")
        
        # Extract table data
        table_result = page.evaluate("""() => {
            const tables = Array.from(document.querySelectorAll("table"));
            const dataTable = tables.find(t => t.querySelector("th"));
            if (!dataTable) return { error: "no table", tableCount: tables.length };
            
            const headers = Array.from(dataTable.querySelectorAll("th")).map(th => th.textContent.trim());
            const trs = Array.from(dataTable.querySelectorAll("tbody tr"));
            const rows = trs.map(tr => {
                return Array.from(tr.querySelectorAll("td")).map(td => td.textContent.trim());
            });
            return { headers, rows, totalRows: trs.length };
        }""")
        
        result["table_data"] = table_result
        
        if "rows" in table_result:
            # Convert to structured filings
            headers = table_result.get("headers", [])
            for row in table_result["rows"]:
                if len(row) >= 6:
                    filing = dict(zip(headers, row)) if headers else {f"col{i}": v for i, v in enumerate(row)}
                    result["filings"].append(filing)
        
        result["status"] = "complete"
        
    except PlaywrightTimeout as e:
        result["status"] = "timeout"
        result["errors"].append(str(e)[:200])
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e)[:200])
    
    return result


def main():
    # Load existing results
    existing = {}
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            existing = {r["state"]: r for r in data}
    
    # Determine which states to run
    target_states = sys.argv[1:] if len(sys.argv) > 1 else SERFF_STATES
    remaining = [s for s in target_states if s not in existing or existing[s].get("status") not in ("complete",)]
    
    print(f"Scraping {len(remaining)} states: {remaining[:5]}...")
    
    all_results = list(existing.values())
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        
        for i, state in enumerate(remaining):
            print(f"\n[{i+1}/{len(remaining)}] Processing {state}...")
            
            result = scrape_state(page, state)
            
            # Update results
            existing[state] = result
            all_results_out = list(existing.values())
            
            with open(RESULTS_FILE, "w") as f:
                json.dump(all_results_out, f, indent=2)
            
            print(f"  [{state}] Status: {result['status']}")
            if result.get("errors"):
                print(f"  [{state}] Errors: {result['errors'][:2]}")
            
            time.sleep(3)  # Polite delay
        
        browser.close()
    
    # Summary
    results = list(existing.values())
    complete = [r for r in results if r.get("status") == "complete"]
    errors = [r for r in results if r.get("status") != "complete"]
    
    print(f"\n{'='*60}")
    print(f"DONE: {len(complete)} complete, {len(errors)} failed/error")
    with_filings = [r for r in complete if r.get("total_filings_str")]
    for r in with_filings:
        print(f"  {r['state']}: {r.get('total_filings_str', '?')} | {len(r.get('filings', []))} rows")


if __name__ == "__main__":
    main()
