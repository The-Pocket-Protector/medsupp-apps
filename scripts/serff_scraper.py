#!/usr/bin/env python3
"""
SERFF Medicare Supplement Application PDF Scraper
Searches SERFF Filing Access for Med Supp paper application filings
across all 50 states + DC, downloads approved Form filings.
"""

import asyncio
import json
import os
import re
import time
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = OUTPUT_DIR / "scrape_log.json"
RESULTS_FILE = OUTPUT_DIR / "results.json"

# States using SERFF (47) — FL, NY, CA use their own systems
SERFF_STATES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "DC", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY"
]

# Major Med Supp carriers (legal names for SERFF search)
CARRIERS = [
    "Aetna",
    "Cigna",
    "Humana",
    "UnitedHealthcare",
    "United American",
    "Mutual of Omaha",
    "Transamerica",
    "Globe Life",
    "American General",
    "Bankers Life",
    "Colonial Penn",
    "USAA",
    "Physicians Mutual",
    "State Farm",
    "Anthem",
    "Blue Cross",
    "Blue Shield",
    "HealthMarkets",
    "Medico",
    "Chesapeake Life",
    "Combined Insurance",
]

SERFF_BASE = "https://filingaccess.serff.com/sfa/home/{state}"
SEARCH_URL = "https://filingaccess.serff.com/sfa/search"


async def scrape_state(page, state: str, results: list, log: list):
    """Search SERFF for Medicare Supplement applications in a given state."""
    url = SERFF_BASE.format(state=state)
    print(f"[{state}] Navigating to {url}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(1)

        # Look for the search form
        # SERFF search: Filing Type = Form, TOI = Medicare Supplement
        # Try to find a search input
        title = await page.title()
        print(f"[{state}] Page title: {title}")

        # Take a screenshot for debugging
        screenshot_path = OUTPUT_DIR / f"screenshot_{state}.png"
        await page.screenshot(path=str(screenshot_path))

        # Look for search elements
        content = await page.content()

        # Check if we got a real page or a block
        if "403" in content[:500] or "Forbidden" in content[:500]:
            log.append({"state": state, "status": "blocked", "note": "403 Forbidden"})
            print(f"[{state}] BLOCKED — 403")
            return

        # Look for the main search form
        # SERFF uses a specific form structure
        search_input = await page.query_selector('input[name="company"]') or \
                       await page.query_selector('input[placeholder*="company" i]') or \
                       await page.query_selector('#company')

        toi_select = await page.query_selector('select[name="TOICode"]') or \
                     await page.query_selector('#TOICode') or \
                     await page.query_selector('select[name="toi"]')

        print(f"[{state}] search_input found: {search_input is not None}, toi_select found: {toi_select is not None}")

        # Log page structure for analysis
        forms = await page.query_selector_all('form')
        inputs = await page.query_selector_all('input, select, textarea')
        input_info = []
        for inp in inputs[:20]:
            name = await inp.get_attribute('name')
            id_ = await inp.get_attribute('id')
            type_ = await inp.get_attribute('type')
            placeholder = await inp.get_attribute('placeholder')
            input_info.append({"name": name, "id": id_, "type": type_, "placeholder": placeholder})

        log.append({
            "state": state,
            "status": "visited",
            "title": title,
            "forms_count": len(forms),
            "inputs": input_info,
            "screenshot": str(screenshot_path)
        })

        # Save page HTML for analysis
        html_path = OUTPUT_DIR / f"page_{state}.html"
        with open(html_path, 'w') as f:
            f.write(content[:50000])  # First 50KB

        print(f"[{state}] Saved page HTML and screenshot")

    except PlaywrightTimeout:
        log.append({"state": state, "status": "timeout"})
        print(f"[{state}] TIMEOUT")
    except Exception as e:
        log.append({"state": state, "status": "error", "error": str(e)})
        print(f"[{state}] ERROR: {e}")


async def probe_serff_structure():
    """
    Phase 1: Visit a sample of states to understand SERFF's search form structure,
    then build a full automated search from there.
    """
    results = []
    log = []

    # Start with a small probe set to understand the UI
    probe_states = ["AL", "TX", "OH", "GA", "CO"]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        for state in probe_states:
            await scrape_state(page, state, results, log)
            await asyncio.sleep(2)  # Polite delay

        await browser.close()

    # Save logs
    with open(LOG_FILE, 'w') as f:
        json.dump(log, f, indent=2)

    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n=== PROBE COMPLETE ===")
    print(f"Log saved to: {LOG_FILE}")
    print(f"Results saved to: {RESULTS_FILE}")
    print(f"\nState summaries:")
    for entry in log:
        print(f"  {entry['state']}: {entry['status']}")
        if entry.get('inputs'):
            print(f"    Form inputs: {[i['name'] or i['id'] for i in entry['inputs'] if i['name'] or i['id']]}")


if __name__ == "__main__":
    asyncio.run(probe_serff_structure())
