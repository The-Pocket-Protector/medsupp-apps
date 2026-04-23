#!/usr/bin/env python3
"""
serff_tx_appdownloader.py
--------------------------
Searches SERFF Filing Access for Texas filings using:
  - Business Type: "Life, Accident/Health, Annuity, Credit" (2nd option)
  - Type of Insurance: type "supp" in the filter box, check all results

Targets rows where Filing Status = "Closed-Approved" and contains "Application".
Downloads the ZIP for each filing and (optionally) uploads to the MEDSUPP GitHub repo.

Requirements:
    pip install playwright requests PyGithub
    playwright install chromium

Usage:
    python serff_tx_appdownloader.py              # search + download + upload
    python serff_tx_appdownloader.py --no-github  # search + download only
    python serff_tx_appdownloader.py --limit 5    # test run (first 5 filings)
"""

import argparse
import json
import os
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SERFF_BASE = "https://filingaccess.serff.com"
STATE = "TX"
OUTPUT_DIR = Path("output/pdfs/TX")
DEBUG_DIR  = Path("output/pdfs/_debug")
LOG_FILE   = Path("output/pdfs/download_log.json")

# GitHub — set via env or edit here
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")      # e.g. "The-Pocket-Protector/medsupp-apps"
GITHUB_PATH  = os.environ.get("GITHUB_PATH", "filings/TX")

# SERFF search parameters (updated per Christopher's steps)
# Step 3: 2nd Business Type option
BUSINESS_TYPE = "Life, Accident/Health, Annuity, Credit"
# Step 4: type this into the Type of Insurance search box, then check all results
SUPPLEMENT_SEARCH_TERM = "supp"

FILING_STATUS_FILTER = "Closed-Approved"
FILING_TYPE_FILTER   = "Application"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_log() -> dict:
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return {"downloaded": [], "failed": [], "links": []}

def save_log(log: dict):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))

def screenshot(page, name: str):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"  [debug] screenshot -> {path}")

def upload_to_github(local_path: Path, filename: str):
    """Push a file to the configured GitHub repo."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  [github] GITHUB_TOKEN or GITHUB_REPO not set -- skipping upload")
        return False
    try:
        from github import Github
        g = Github(GITHUB_TOKEN)
        repo = g.get_repo(GITHUB_REPO)
        content = local_path.read_bytes()
        remote_path = f"{GITHUB_PATH}/{filename}"
        try:
            existing = repo.get_contents(remote_path)
            repo.update_file(remote_path, f"Update {filename}", content, existing.sha)
            print(f"  [github] updated {remote_path}")
        except Exception:
            repo.create_file(remote_path, f"Add {filename}", content)
            print(f"  [github] created {remote_path}")
        return True
    except Exception as e:
        print(f"  [github] upload failed: {e}")
        return False

# ---------------------------------------------------------------------------
# Browser flow
# ---------------------------------------------------------------------------

def establish_session(page):
    """Navigate to TX home and click Begin Search."""
    print("  [session] establishing TX session ...")
    page.goto(f"{SERFF_BASE}/sfa/home/{STATE}", wait_until="networkidle")
    time.sleep(1)
    # Accept terms if shown
    for btn_text in ["I Agree", "Accept", "Continue", "Agree"]:
        try:
            page.get_by_text(btn_text, exact=False).first.click(timeout=2000)
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)
            break
        except Exception:
            pass
    # Click Begin Search (tries several label variants)
    for link_text in ["Begin Search", "Search Filings", "Continue", "Search"]:
        try:
            page.get_by_text(link_text, exact=False).first.click(timeout=3000)
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)
            break
        except Exception:
            pass
    print(f"  [session] landed on: {page.url}")


def fill_search_form(page):
    """
    Step 3: Select Business Type = 'Life, Accident/Health, Annuity, Credit' (2nd option).
    Step 4: Type 'supp' into the Type of Insurance filter, check all visible options.
    Submit the search.
    """
    # --- Step 3: Business Type ---
    bt_selector = ("select[id*='businessType'], select[name*='businessType'], "
                   "select[id*='BusinessType'], select[id*='business_type']")
    set_bt = False
    try:
        page.select_option(bt_selector, label=BUSINESS_TYPE)
        print(f"  [form] Business Type set by label: {BUSINESS_TYPE}")
        set_bt = True
    except Exception:
        pass

    if not set_bt:
        try:
            # Fall back to 2nd option by index
            options = page.locator(bt_selector + " option").all()
            if len(options) >= 2:
                val = options[1].get_attribute("value")
                page.select_option(bt_selector, value=val)
                print(f"  [form] Business Type set by index [1], value={val}")
                set_bt = True
        except Exception as e:
            print(f"  [form] WARNING: could not set Business Type: {e}")

    time.sleep(0.6)

    # --- Step 4: Type of Insurance — type "supp", check all filtered options ---
    toi_selector = ("select[id*='typeOfInsurance'], select[name*='typeOfInsurance'], "
                    "select[id*='TypeOfInsurance'], select[id*='insuranceType'], "
                    "select[id*='insurance_type']")

    # Try to find a search/filter input associated with the Type of Insurance field
    filter_input = None
    filter_candidates = [
        "input[id*='typeOfInsurance']",
        "input[id*='insuranceType']",
        "input[placeholder*='search' i]",
        "input[placeholder*='filter' i]",
        "input[placeholder*='type' i]",
        "input[aria-label*='insurance' i]",
    ]
    for sel in filter_candidates:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=1500):
                filter_input = el
                print(f"  [form] found Type of Insurance filter input: {sel}")
                break
        except Exception:
            pass

    if filter_input:
        # Live-filter UI: type "supp" then check all visible checkboxes
        print(f"  [form] typing '{SUPPLEMENT_SEARCH_TERM}' into Type of Insurance filter")
        filter_input.clear()
        filter_input.type(SUPPLEMENT_SEARCH_TERM, delay=80)
        time.sleep(0.8)
        # Check every visible unchecked checkbox
        checkboxes = page.locator("input[type='checkbox']").all()
        checked = 0
        for cb in checkboxes:
            try:
                if cb.is_visible() and not cb.is_checked():
                    cb.check()
                    checked += 1
            except Exception:
                pass
        print(f"  [form] checked {checked} supplement option(s)")
    else:
        # Plain <select multiple>: select all options whose text contains "supp"
        print(f"  [form] no filter input found — selecting all <option> containing '{SUPPLEMENT_SEARCH_TERM}'")
        try:
            options = page.locator(toi_selector + " option").all()
            vals_to_select = [
                opt.get_attribute("value")
                for opt in options
                if SUPPLEMENT_SEARCH_TERM.lower() in (opt.inner_text() or "").lower()
                and opt.get_attribute("value")
            ]
            if vals_to_select:
                page.select_option(toi_selector, value=vals_to_select)
                print(f"  [form] selected {len(vals_to_select)} supplement option(s) from <select>")
            else:
                print(f"  [form] WARNING: no options matched '{SUPPLEMENT_SEARCH_TERM}'")
                screenshot(page, "no_supp_options")
        except Exception as e:
            print(f"  [form] Type of Insurance error: {e}")
            screenshot(page, "toi_error")

    time.sleep(0.5)

    # --- Submit ---
    try:
        page.get_by_role("button", name=re.compile("search", re.I)).first.click()
    except Exception:
        page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)


def sort_by_filing_status(page):
    """Click the Filing Status column header to sort alphabetically."""
    try:
        page.get_by_text("Filing Status", exact=False).first.click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)
    except Exception:
        pass


def collect_matching_rows(page) -> list[dict]:
    """
    Page through results collecting rows where Filing Status is
    'Closed-Approved' and contains 'Application'.
    """
    matches = []
    page_num = 0

    while True:
        page_num += 1
        rows = page.locator("tr").all()
        for row in rows:
            text = row.inner_text()
            if FILING_STATUS_FILTER in text and FILING_TYPE_FILTER in text:
                href = None
                try:
                    link = row.locator("a").first
                    href = link.get_attribute("href")
                except Exception:
                    pass
                matches.append({"text": text.strip(), "href": href, "page": page_num})

        # Pagination
        try:
            next_btn = page.get_by_role("link", name=re.compile(r"next|>", re.I)).first
            if next_btn.is_visible():
                next_btn.click()
                page.wait_for_load_state("networkidle")
                time.sleep(0.5)
            else:
                break
        except Exception:
            break

    return matches


def download_filing(page, row: dict, output_dir: Path):
    """
    Navigate to the filing summary, select all attachments, download ZIP.
    Returns (local_zip_path, None) on success or (None, url_link) on failure.
    """
    href = row.get("href")
    if not href:
        print("  [nav] no direct href -- skipping")
        return None, None

    url = href if href.startswith("http") else SERFF_BASE + href
    try:
        page.goto(url, wait_until="networkidle")
        time.sleep(1)
    except Exception as e:
        print(f"  [nav] failed to navigate to {url}: {e}")
        return None, url

    # Session expiry check
    if "session" in page.url.lower() and "expired" in page.content().lower():
        raise RuntimeError("Session expired")

    # Click "Select All" in each attachment section
    for btn_text in ["Select All", "Select all", "SelectAll"]:
        try:
            for b in page.get_by_text(btn_text, exact=False).all():
                if b.is_visible():
                    b.click()
                    time.sleep(0.3)
        except Exception:
            pass

    # Download ZIP
    try:
        with page.expect_download(timeout=60000) as dl_info:
            page.get_by_text("Download Zip File", exact=False).first.click()
        download = dl_info.value
        slug = re.sub(r"[^\w\-]", "_", page.url.split("/")[-1] or "filing")
        dest = output_dir / f"{slug}.zip"
        output_dir.mkdir(parents=True, exist_ok=True)
        download.save_as(str(dest))
        print(f"  [dl] saved -> {dest}")
        return dest, None
    except PWTimeout:
        screenshot(page, f"dl_timeout_{int(time.time())}")
        print("  [dl] download timed out -- collecting link instead")
        return None, page.url
    except Exception as e:
        screenshot(page, f"dl_error_{int(time.time())}")
        print(f"  [dl] error: {e}")
        return None, page.url


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SERFF TX Application downloader")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub upload")
    parser.add_argument("--limit", type=int, default=0, help="Max filings to process (0 = all)")
    args = parser.parse_args()

    log = load_log()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            establish_session(page)

            # Single search: Business Type + "supp" filter covers all supplement options at once
            print(f"\n[search] Business='{BUSINESS_TYPE}' | filter='{SUPPLEMENT_SEARCH_TERM}'")
            all_rows: list[dict] = []
            try:
                if "/filingSearch" not in page.url:
                    establish_session(page)
                fill_search_form(page)
                sort_by_filing_status(page)
                rows = collect_matching_rows(page)
                print(f"  -> {len(rows)} matching rows")
                all_rows.extend(rows)
            except Exception as e:
                screenshot(page, "search_error")
                print(f"  [error] search failed: {e}")

            # Deduplicate by href
            seen = set()
            unique_rows = []
            for r in all_rows:
                key = r.get("href") or r.get("text", "")[:80]
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(r)

            # Skip already downloaded
            todo = [r for r in unique_rows
                    if (r.get("href") or "") not in log["downloaded"]]
            if args.limit:
                todo = todo[:args.limit]

            print(f"\n[run] {len(unique_rows)} unique matches | {len(todo)} to process")

            for i, row in enumerate(todo, 1):
                print(f"\n[{i}/{len(todo)}] {row.get('text', '')[:80]}")
                try:
                    local_path, fallback_link = download_filing(page, row, OUTPUT_DIR)
                except RuntimeError as e:
                    if "Session expired" in str(e):
                        print("  [session] re-establishing ...")
                        establish_session(page)
                        local_path, fallback_link = download_filing(page, row, OUTPUT_DIR)
                    else:
                        raise

                if local_path:
                    log["downloaded"].append(row.get("href") or str(local_path))
                    if not args.no_github:
                        upload_to_github(local_path, local_path.name)
                elif fallback_link:
                    print(f"  [link] {fallback_link}")
                    log["links"].append(fallback_link)
                    if not args.no_github and GITHUB_TOKEN and GITHUB_REPO:
                        links_path = Path("output/pdfs/TX/_links.txt")
                        links_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(links_path, "a") as f:
                            f.write(fallback_link + "\n")

                save_log(log)

        finally:
            context.close()
            browser.close()

    print(f"\n[done]")
    print(f"  Downloaded : {len(log['downloaded'])}")
    print(f"  Links only : {len(log['links'])}")
    print(f"  Log        : {LOG_FILE}")
    if log["links"]:
        print("\nLinks (could not download ZIP):")
        for lnk in log["links"]:
            print(f"  {lnk}")


if __name__ == "__main__":
    main()
