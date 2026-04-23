#!/usr/bin/env python3
"""
SERFF PDF Downloader - Local Playwright Script
==============================================
Runs on a LOCAL machine (not headless server).
Downloads ZIP files from SERFF filing summaries.

REQUIREMENTS:
  pip install playwright openpyxl
  playwright install chromium

USAGE:
  python serff_pdf_downloader.py                    # All states, all approved Form filings
  python serff_pdf_downloader.py KY IL IN           # Specific states only
  python serff_pdf_downloader.py --limit 10         # Test: first 10 filings only
  python serff_pdf_downloader.py --state KY --limit 5

WHAT IT DOES:
  1. Reads all *_form_filings.json files from ../output/serff/
  2. Filters to "Closed - Approved" Form filings only
  3. For each filing: opens SERFF summary page, clicks "Download Zip File"
  4. Saves ZIP to ../output/pdfs/<STATE>/<TRACKING_NUMBER>.zip
  5. Tracks progress in ../output/pdfs/download_log.json (resume-safe)

OUTPUT LOCATION:
  ../output/pdfs/
    KY/
      AETN-132199103.zip
      ACEH-133226177.zip
    IL/
      ...
    download_log.json   <- tracks what's done/failed, safe to re-run

NOTES:
  - SERFF will ask you to "Accept" terms once per session (auto-handled)
  - The browser window will be VISIBLE so you can see progress
  - Rate: ~5-10 seconds per filing (polite, avoids getting blocked)
  - ~14,000 approved filings total — full run = 15-20 hours
  - Start with one state to verify: python serff_pdf_downloader.py KY
"""

import json
import time
import sys
import glob
import argparse
from pathlib import Path
from datetime import datetime

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
except ImportError:
    print("ERROR: playwright not installed.")
    print("Run: pip install playwright && playwright install chromium")
    sys.exit(1)

# ── Paths ──────────────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR.parent / "output"
SERFF_DIR = OUTPUT_DIR / "serff"
PDF_DIR = OUTPUT_DIR / "pdfs"
LOG_FILE = PDF_DIR / "download_log.json"

PDF_DIR.mkdir(parents=True, exist_ok=True)

SERFF_BASE = "https://filingaccess.serff.com"

def tracking_to_url(tracking_number):
    """
    Convert SERFF tracking number to filing summary URL.
    e.g. AETN-132199103 -> .../filingSummary.xhtml?filingId=132199103
    The numeric ID is the part after the dash.
    """
    parts = tracking_number.split("-")
    if len(parts) == 2 and parts[1].isdigit():
        filing_id = parts[1]
        return f"{SERFF_BASE}/sfa/search/filingSummary.xhtml?filingId={filing_id}"
    # Fallback to old format
    return f"{SERFF_BASE}/sfa/filing/{tracking_number}"

# ── Load filings ───────────────────────────────────────────────────────────────

def load_filings(target_states=None):
    """Load all approved Form filings from JSON files."""
    filings = []
    files = sorted(glob.glob(str(SERFF_DIR / "*_form_filings.json")))
    
    for f in files:
        with open(f) as fp:
            data = json.load(fp)
        state = data.get("state", "??")
        
        if target_states and state not in target_states:
            continue
        
        rows = data.get("form_rows", [])
        approved = [r for r in rows if "Approved" in r.get("Filing Status", "")]
        filings.extend(approved)
        print(f"  {state}: {len(approved)} approved filings")
    
    return filings


def load_log():
    """Load download log (tracks done/failed/skipped)."""
    if LOG_FILE.exists():
        with open(LOG_FILE) as f:
            return json.load(f)
    return {}


def save_log(log):
    """Save download log."""
    with open(LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


# ── SERFF navigation ──────────────────────────────────────────────────────────

def is_session_page(page):
    """Detect if we're on a session-expired or login-required page."""
    url = page.url
    content = page.content().lower()
    return (
        "session" in content and "expir" in content
    ) or "login" in url or "signin" in url or "userAgreement" in url


def ensure_serff_session(page):
    """
    Make sure we have an active SERFF session.
    Navigates through home -> Begin Search -> Accept terms.
    Returns True if session established.
    """
    debug_dir = PDF_DIR / "_debug"
    debug_dir.mkdir(exist_ok=True)

    print("    [session] Establishing fresh SERFF session...")
    
    # Clear all cookies and storage so SERFF sees a brand-new visitor
    try:
        page.context.clear_cookies()
        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
        print("    [session] Cleared cookies and storage")
    except Exception as ce:
        print(f"    [session] Cookie clear warning: {ce}")
    
    # SERFF requires entry via a state DOI referrer link to establish a session.
    # Going directly to filingaccess.serff.com always gives "Session Expired".
    # We spoof the referrer by visiting the KY DOI page first, then following their SERFF link.
    print("    [session] Entering via KY DOI referrer to establish valid session...")
    
    # Try known state referrer URLs (KY first, then fallback)
    state_entry_urls = [
        "https://insurance.ky.gov/ppc/new_default.aspx",
        "https://insurance.ky.gov",
    ]
    
    entered_via_state = False
    for state_url in state_entry_urls:
        try:
            page.goto(state_url, timeout=20000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            # Look for a link to SERFF on the state page
            for a in page.query_selector_all("a"):
                href = a.get_attribute("href") or ""
                txt = (a.text_content() or "").lower()
                if "serff" in href.lower() or "serff" in txt or "filingaccess" in href.lower():
                    print(f"    [session] Found SERFF link: {href}")
                    a.click()
                    page.wait_for_load_state("networkidle")
                    time.sleep(3)
                    entered_via_state = True
                    break
            if entered_via_state:
                break
        except Exception as e:
            print(f"    [session] State URL {state_url} failed: {e}")
    
    if not entered_via_state:
        # Spoof referrer manually and go directly
        print("    [session] No state SERFF link found — going direct with referrer header")
        page.set_extra_http_headers({"Referer": "https://insurance.ky.gov/ppc/new_default.aspx"})
        page.goto(f"{SERFF_BASE}/sfa/home/KY", timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(3)
    
    page.screenshot(path=str(debug_dir / "step1_home.png"))
    print(f"    [session] At: {page.url}")
    
    # Click Begin Search if present
    clicked = False
    for selector in ["text=Begin Search", "a[href*='userAgreement']", "a[href*='beginSearch']"]:
        try:
            page.click(selector, timeout=5000)
            page.wait_for_load_state("networkidle")
            time.sleep(3)
            clicked = True
            print(f"    [session] Clicked '{selector}', now at: {page.url}")
            break
        except Exception:
            pass
    
    page.screenshot(path=str(debug_dir / "step2_after_begin_search.png"))
    
    # Dump all buttons/links at this point
    elems = []
    for e in page.query_selector_all("a, button, input"):
        t = (e.text_content() or e.get_attribute("value") or "").strip()
        h = e.get_attribute("href") or ""
        if t or h:
            elems.append(f"{t} | href={h}")
    with open(debug_dir / "step2_elements.txt", "w") as f:
        f.write(f"URL: {page.url}\n\n" + "\n".join(elems))
    print(f"    [session] After Begin Search — URL: {page.url}")
    print(f"    [session] Screenshot: output/pdfs/_debug/step2_after_begin_search.png")
    
    # Accept terms
    for selector in ["text=Accept", "text=I Accept", "input[value='Accept']",
                     "input[value='I Accept']", "button:has-text('Accept')",
                     "text=Agree", "text=I Agree"]:
        try:
            page.click(selector, timeout=3000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
            print(f"    [session] Terms accepted via {selector}, now at: {page.url}")
            page.screenshot(path=str(debug_dir / "step3_after_accept.png"))
            return True
        except Exception:
            pass
    
    # Manual fallback — browser is open, user can see it
    print("    [session] Could not auto-accept terms.")
    print("    [session] The browser window is open. Please manually navigate through the agreement and click Accept.")
    print("    [session] Then come back here and press Enter.")
    input("    Press Enter after you have accepted the terms in the browser: ")
    page.screenshot(path=str(debug_dir / "step3_manual_accept.png"))
    print(f"    [session] After manual accept — URL: {page.url}")
    return True


def accept_terms_if_needed(page):
    """Accept SERFF terms if the accept button is visible."""
    try:
        btns = page.query_selector_all("button, input[type='submit'], input[type='button']")
        for btn in btns:
            txt = (btn.text_content() or btn.get_attribute("value") or "").strip()
            if txt.lower() in ("accept", "i accept", "agree", "i agree", "continue"):
                print("    [terms] Clicking Accept...")
                btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(1)
                return True
    except Exception:
        pass
    return False


def get_filing_summary_url(page, tracking_number):
    """
    Navigate to filing page and return the filingSummary URL with numeric filingId.
    The tracking number URL redirects to the summary.
    """
    url = f"{SERFF_BASE}/sfa/filing/{tracking_number}"
    page.goto(url, timeout=30000)
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    # Check if we hit the terms page
    accept_terms_if_needed(page)
    page.wait_for_load_state("networkidle")
    time.sleep(1)
    
    # Get current URL — should now be filingSummary.xhtml
    current_url = page.url
    return current_url


def download_filing_zip(page, tracking_number, state, log, dry_run=False):
    """
    Download ZIP from a SERFF filing summary page.
    Returns: 'done', 'skipped', 'failed', 'no_zip'
    """
    log_key = tracking_number
    
    # Skip if already done
    if log.get(log_key, {}).get("status") == "done":
        return "skipped"
    
    state_dir = PDF_DIR / state
    state_dir.mkdir(exist_ok=True)
    zip_path = state_dir / f"{tracking_number}.zip"
    
    # Skip if file already exists
    if zip_path.exists() and zip_path.stat().st_size > 1000:
        log[log_key] = {"status": "done", "path": str(zip_path), "ts": datetime.utcnow().isoformat()}
        return "skipped"
    
    if dry_run:
        print(f"    [dry-run] Would download {tracking_number}")
        return "skipped"
    
    try:
        # Navigate to filing
        url = tracking_to_url(tracking_number)
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle")
        time.sleep(2)
        
        # If session expired or we're on a login/terms page, re-establish session then retry
        if is_session_page(page) or page.url == url and "filingSummary" not in page.url and len(page.query_selector_all("input, button")) < 3:
            print("    [session] Session issue detected — re-establishing...")
            ensure_serff_session(page)
            # Now navigate to the filing
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            time.sleep(2)
        
        # Accept terms if still needed
        accept_terms_if_needed(page)
        page.wait_for_load_state("networkidle")
        time.sleep(1)
        
        current_url = page.url
        
        # Look for "Download Zip File" button/link
        zip_btn = None
        
        # Try various selectors
        for selector in [
            "input[value*='Zip']",
            "input[value*='ZIP']", 
            "button:has-text('Zip')",
            "button:has-text('ZIP')",
            "a:has-text('Download Zip')",
            "a:has-text('Download ZIP')",
            "[id*='downloadZip']",
            "[onclick*='zip']",
            "[onclick*='Zip']",
        ]:
            try:
                elem = page.query_selector(selector)
                if elem:
                    zip_btn = elem
                    break
            except Exception:
                pass
        
        if not zip_btn:
            # Try broader text search
            all_buttons = page.query_selector_all("input[type='submit'], input[type='button'], button, a")
            for elem in all_buttons:
                txt = (elem.text_content() or elem.get_attribute("value") or "").lower()
                if "zip" in txt or "download all" in txt:
                    zip_btn = elem
                    break
        
        if not zip_btn:
            # Debug: save screenshot + dump all button text so we can see what's on the page
            debug_dir = PDF_DIR / "_debug"
            debug_dir.mkdir(exist_ok=True)
            try:
                page.screenshot(path=str(debug_dir / f"{tracking_number}.png"))
                all_elems = page.query_selector_all("input, button, a")
                btn_texts = []
                for e in all_elems:
                    t = (e.text_content() or e.get_attribute("value") or "").strip()
                    if t:
                        btn_texts.append(t)
                with open(debug_dir / f"{tracking_number}_buttons.txt", "w") as dbf:
                    dbf.write(f"URL: {current_url}\n\nButtons/Links/Inputs:\n")
                    dbf.write("\n".join(btn_texts))
                print(f"    [debug] Screenshot + button list saved to output/pdfs/_debug/{tracking_number}.png")
            except Exception as de:
                print(f"    [debug-err] {de}")
            print(f"    [warn] No ZIP button found for {tracking_number}")
            log[log_key] = {"status": "no_zip", "url": current_url, "ts": datetime.utcnow().isoformat()}
            return "no_zip"
        
        # Click and capture download
        print(f"    Downloading {tracking_number}...")
        
        with page.expect_download(timeout=60000) as download_info:
            zip_btn.click()
        
        download = download_info.value
        download.save_as(str(zip_path))
        
        file_size = zip_path.stat().st_size if zip_path.exists() else 0
        print(f"    Saved: {zip_path.name} ({file_size:,} bytes)")
        
        log[log_key] = {
            "status": "done",
            "path": str(zip_path),
            "size": file_size,
            "ts": datetime.utcnow().isoformat()
        }
        return "done"
    
    except PlaywrightTimeout:
        print(f"    [timeout] {tracking_number}")
        log[log_key] = {"status": "timeout", "ts": datetime.utcnow().isoformat()}
        return "failed"
    
    except Exception as e:
        err = str(e)[:200]
        print(f"    [error] {tracking_number}: {err}")
        log[log_key] = {"status": "error", "error": err, "ts": datetime.utcnow().isoformat()}
        return "failed"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SERFF PDF Downloader")
    parser.add_argument("states", nargs="*", help="State codes to process (e.g. KY IL IN). Default: all.")
    parser.add_argument("--limit", type=int, default=None, help="Max filings to process (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Don't actually download, just show what would run")
    parser.add_argument("--resume", action="store_true", default=True, help="Skip already-downloaded filings (default: on)")
    args = parser.parse_args()
    
    target_states = [s.upper() for s in args.states] if args.states else None
    
    print("=" * 60)
    print("SERFF PDF Downloader")
    print("=" * 60)
    
    if target_states:
        print(f"States: {target_states}")
    else:
        print("States: ALL")
    
    if args.limit:
        print(f"Limit: {args.limit} filings")
    
    if args.dry_run:
        print("DRY RUN — no actual downloads")
    
    print()
    
    # Load filings
    print("Loading filings...")
    filings = load_filings(target_states)
    print(f"Total approved Form filings: {len(filings)}")
    
    if args.limit:
        filings = filings[:args.limit]
        print(f"Limited to: {len(filings)}")
    
    if not filings:
        print("No filings to process.")
        return
    
    # Load progress log
    log = load_log()
    already_done = sum(1 for f in filings if log.get(f["SERFF Tracking Number"], {}).get("status") == "done")
    print(f"Already downloaded: {already_done}")
    print(f"To download: {len(filings) - already_done}")
    print()
    
    # Stats
    stats = {"done": 0, "skipped": 0, "no_zip": 0, "failed": 0}
    
    # Launch browser (VISIBLE — not headless, so you can see it work)
    print("Launching browser (will open a visible Chrome window)...")
    print()
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # VISIBLE — required for downloads to work reliably
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            downloads_path=str(PDF_DIR / "_tmp_downloads")
        )
        
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        page = context.new_page()
        
        # ── Accept SERFF terms ─────────────────────────────────────────────
        print("Opening SERFF — establishing session...")
        ensure_serff_session(page)
        print("Session established. Starting downloads...\n")
        
        for i, filing in enumerate(filings):
            tracking = filing.get("SERFF Tracking Number", "")
            state = filing.get("State", "??")
            carrier = filing.get("Company Name", "")
            
            if not tracking:
                continue
            
            print(f"[{i+1}/{len(filings)}] {state} | {carrier[:40]} | {tracking}")
            
            result = download_filing_zip(page, tracking, state, log, dry_run=args.dry_run)
            stats[result if result in stats else "done"] += 1
            
            # Save log every 10 filings
            if (i + 1) % 10 == 0:
                save_log(log)
                done_pct = (stats["done"] + stats["skipped"]) / (i + 1) * 100
                print(f"\n  Progress: {i+1}/{len(filings)} | Done: {stats['done']} | Skipped: {stats['skipped']} | Failed: {stats['failed']}\n")
            
            # Polite delay
            if result != "skipped":
                time.sleep(4)
        
        browser.close()
    
    # Final save
    save_log(log)
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print(f"  Downloaded: {stats['done']}")
    print(f"  Skipped (already done): {stats['skipped']}")
    print(f"  No ZIP button: {stats['no_zip']}")
    print(f"  Failed/timeout: {stats['failed']}")
    print(f"  Log saved: {LOG_FILE}")
    print(f"  ZIPs saved to: {PDF_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
