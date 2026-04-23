#!/usr/bin/env python3
"""
SERFF Scraper using Firecrawl /v2/browser API directly.
Creates a browser session, navigates SERFF, selects Medicare Supplement TOI, and extracts filings.
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
RESULTS_FILE = OUTPUT_DIR / "all_states_results_v2.json"

SERFF_STATES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "DC", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY"
]


def create_session(url):
    """Create a new browser session starting at URL."""
    resp = requests.post(
        f"{API_URL}/v2/browser",
        headers=HEADERS,
        json={"url": url},
        timeout=30
    )
    data = resp.json()
    if not data.get("success"):
        raise Exception(f"Failed to create session: {data}")
    return data["sessionId"]


def execute(session_id, code, timeout=60):
    """Execute Playwright code in the browser session."""
    resp = requests.post(
        f"{API_URL}/v2/browser/{session_id}/execute",
        headers=HEADERS,
        json={"code": code},
        timeout=timeout + 10
    )
    data = resp.json()
    return data


def delete_session(session_id):
    """Delete a browser session."""
    try:
        requests.delete(
            f"{API_URL}/v2/browser/{session_id}",
            headers=HEADERS,
            timeout=10
        )
    except Exception:
        pass


def scrape_state(state):
    """Scrape one state's Medicare Supplement filings."""
    result = {"state": state, "status": "pending", "filings": [], "errors": []}
    session_id = None
    
    try:
        # Create browser session
        print(f"  [{state}] Creating session...")
        session_id = create_session(f"https://filingaccess.serff.com/sfa/home/{state}")
        print(f"  [{state}] Session: {session_id}")
        time.sleep(2)
        
        # Full navigation + form fill + search in one code block
        code = r"""
async function run() {
    const page = context.page;
    
    // Step 1: Navigate and accept terms
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1000);
    
    const beginLink = await page.$('a[href*="userAgreement"]');
    if (!beginLink) throw new Error('Begin Search link not found');
    await beginLink.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(800);
    
    const buttons = await page.$$('button');
    let acceptBtn = null;
    for (const btn of buttons) {
        const text = await btn.textContent();
        if (text && text.trim() === 'Accept') { acceptBtn = btn; break; }
    }
    if (!acceptBtn) throw new Error('Accept button not found');
    await acceptBtn.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(2000);
    
    // Step 2: Select Business Type = Life
    const bizMenu = await page.$('#simpleSearch\\:businessType');
    if (!bizMenu) throw new Error('Business type menu not found');
    await bizMenu.click();
    await page.waitForTimeout(400);
    
    const bizItems = await page.$$('#simpleSearch\\:businessType_items li');
    let lifeItem = null;
    for (const item of bizItems) {
        const text = await item.textContent();
        if (text && text.includes('Life, Accident')) { lifeItem = item; break; }
    }
    if (!lifeItem) throw new Error('Life option not found');
    await lifeItem.click();
    await page.waitForTimeout(4000); // Wait for AJAX
    
    // Verify TOI options loaded
    const toiCount = await page.evaluate(() => 
        document.querySelectorAll("input[name='simpleSearch:availableTois']").length
    );
    
    // Step 3: Select MS TOI codes
    const toiResult = await page.evaluate(() => {
        const w = PrimeFaces.widgets["widget_simpleSearch_availableTois"];
        if (!w) return { error: "widget not found" };
        
        w.show();
        const items = w.panel.find("li.ui-selectcheckboxmenu-item");
        const toggled = [];
        items.each(function(i, li) {
            const lbl = li.querySelector("label");
            if (lbl) {
                const txt = lbl.textContent.trim();
                if (txt.indexOf("MS05I") === 0 || txt.indexOf("MS08I") === 0) {
                    w.check(jQuery(li).find(".ui-chkbox-box"), true);
                    toggled.push(txt.substring(0, 60));
                }
            }
        });
        w.updateLabel();
        w.hide();
        
        const selected = Array.from(
            document.querySelectorAll("input[name='simpleSearch:availableTois']:checked")
        ).map(cb => cb.value);
        
        return { toggled, selected, toiCount: items.length };
    });
    
    // Step 4: Click Search
    const searchButtons = await page.$$('button');
    let searchBtn = null;
    for (const btn of searchButtons) {
        const text = await btn.textContent();
        if (text && text.trim() === 'Search') { searchBtn = btn; break; }
    }
    if (!searchBtn) throw new Error('Search button not found');
    
    await searchBtn.click();
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(5000);
    
    // Step 5: Extract results
    const bodyText = await page.evaluate(() => document.body.innerText);
    const url = page.url();
    
    // Extract table data
    const tableData = await page.evaluate(() => {
        const tables = Array.from(document.querySelectorAll('table'));
        const dataTable = tables.find(t => t.querySelector('th'));
        if (!dataTable) return { error: 'no table', tableCount: tables.length };
        
        const headers = Array.from(dataTable.querySelectorAll('th')).map(th => th.textContent.trim());
        const trs = Array.from(dataTable.querySelectorAll('tbody tr'));
        const rows = trs.map(tr => 
            Array.from(tr.querySelectorAll('td')).map(td => td.textContent.trim())
        );
        return { headers, rows, totalRows: trs.length };
    });
    
    return { 
        url, 
        bodySnippet: bodyText.substring(0, 500),
        toiResult,
        toiCount,
        tableData
    };
}
return run();
"""
        
        resp = execute(session_id, code, timeout=120)
        print(f"  [{state}] Execute response:", json.dumps(resp, indent=2)[:500])
        
        if resp.get("success"):
            data = resp.get("result", {})
            body = data.get("bodySnippet", "")
            count_match = re.search(r'([\d,]+)\s+Filing\(s\)', body)
            
            if count_match:
                result["total_filings_str"] = count_match.group(0)
                print(f"  [{state}] {count_match.group(0)}")
            
            table_data = data.get("tableData", {})
            result["table_data"] = table_data
            result["toi_result"] = data.get("toiResult", {})
            
            if "rows" in table_data:
                headers = table_data.get("headers", [])
                for row in table_data["rows"]:
                    filing = {}
                    for i, val in enumerate(row):
                        key = headers[i] if i < len(headers) else f"col{i}"
                        filing[key] = val
                    result["filings"].append(filing)
            
            result["status"] = "complete"
            result["debug_body"] = body
        else:
            result["status"] = "error"
            result["errors"].append(json.dumps(resp)[:300])
    
    except Exception as e:
        result["status"] = "error"
        result["errors"].append(str(e)[:300])
        print(f"  [{state}] Exception: {e}")
    
    finally:
        if session_id:
            delete_session(session_id)
            time.sleep(1)
    
    return result


def main():
    # Load existing results
    existing = {}
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            data = json.load(f)
            existing = {r["state"]: r for r in data}
    
    target_states = sys.argv[1:] if len(sys.argv) > 1 else SERFF_STATES
    remaining = [s for s in target_states if s not in existing or existing[s].get("status") not in ("complete",)]
    
    print(f"Scraping {len(remaining)} states...")
    
    for i, state in enumerate(remaining):
        print(f"\n[{i+1}/{len(remaining)}] {state}...")
        
        result = scrape_state(state)
        existing[state] = result
        
        with open(RESULTS_FILE, "w") as f:
            json.dump(list(existing.values()), f, indent=2)
        
        print(f"  [{state}] Status: {result['status']}, Filings: {len(result.get('filings', []))}")
        if result.get("errors"):
            print(f"  [{state}] Errors: {result['errors'][:1]}")
        
        time.sleep(5)  # Polite delay
    
    results = list(existing.values())
    complete = [r for r in results if r.get("status") == "complete"]
    print(f"\nDONE: {len(complete)}/{len(results)} complete")
    for r in complete:
        print(f"  {r['state']}: {r.get('total_filings_str', '?')} | {len(r.get('filings', []))} rows")


if __name__ == "__main__":
    main()
