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
    python serff_tx_appdownloader.py --debug      # extra screenshots at each step
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
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")
GITHUB_PATH  = os.environ.get("GITHUB_PATH", "filings/TX")

FILING_STATUS_FILTER = "Closed-Approved"
FILING_TYPE_FILTER   = "Application"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEBUG_MODE = False

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
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  [debug] screenshot -> {path}")
    except Exception as e:
        print(f"  [debug] screenshot failed: {e}")

def debug_shot(page, name: str):
    if DEBUG_MODE:
        screenshot(page, name)

def wait_for_search_page(page, timeout=15):
    """Wait until we're on the filing search form."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if "filingSearch" in page.url or "search" in page.url.lower():
            return True
        time.sleep(0.5)
    return False

def upload_to_github(local_path: Path, filename: str):
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
# Navigation
# ---------------------------------------------------------------------------

def go_to_search_page(page):
    """
    Navigate to the SERFF TX filing search form.
    Strategy: go to /sfa/home/TX, accept any terms, then click the Begin Search link.
    If that fails, try navigating directly to the search URL.
    """
    print("  [nav] loading TX home ...")
    page.goto(f"{SERFF_BASE}/sfa/home/TX", wait_until="domcontentloaded")
    time.sleep(2)
    debug_shot(page, "01_home")

    # Accept terms / disclaimer if present
    for btn_text in ["I Agree", "Accept", "Agree", "OK", "Continue"]:
        try:
            btn = page.get_by_role("button", name=re.compile(btn_text, re.I)).first
            if btn.is_visible(timeout=1000):
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                debug_shot(page, "02_after_terms")
                break
        except Exception:
            pass

    # Try clicking "Begin Search" link
    clicked = False
    for text in ["Begin Search", "Search Filings", "Filing Search", "Search"]:
        try:
            el = page.get_by_text(text, exact=False).first
            if el.is_visible(timeout=2000):
                el.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1.5)
                clicked = True
                break
        except Exception:
            pass

    # Also try anchor tags specifically
    if not clicked or "filingSearch" not in page.url:
        try:
            link = page.locator("a[href*='filingSearch'], a[href*='search']").first
            if link.is_visible(timeout=2000):
                link.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1.5)
        except Exception:
            pass

    # Last resort: navigate directly
    if "filingSearch" not in page.url:
        print("  [nav] clicking didn't land on search — trying direct URL ...")
        page.goto(f"{SERFF_BASE}/sfa/search/filingSearch.xhtml", wait_until="domcontentloaded")
        time.sleep(2)

    debug_shot(page, "03_search_page")
    print(f"  [nav] current URL: {page.url}")

    if "filingSearch" not in page.url and "search" not in page.url.lower():
        screenshot(page, "ERROR_not_on_search_page")
        raise RuntimeError(f"Could not reach filing search page. Currently at: {page.url}")


def dump_form_info(page):
    """Print all select elements and their options for debugging."""
    try:
        selects = page.locator("select").all()
        print(f"  [debug] found {len(selects)} select element(s) on page")
        for i, sel in enumerate(selects):
            try:
                sel_id = sel.get_attribute("id") or sel.get_attribute("name") or f"select[{i}]"
                options = sel.locator("option").all()
                opt_texts = [o.inner_text().strip() for o in options[:10]]
                print(f"    select #{i} id={sel_id}: {opt_texts}")
            except Exception:
                pass
    except Exception as e:
        print(f"  [debug] dump_form_info error: {e}")


def fill_search_form(page):
    """
    Step 3: Select Business Type = 2nd option (Life, Accident/Health, Annuity, Credit).
    Step 4: Find Type of Insurance multi-select, type 'supp' in filter if available,
            then check/select all matching supplement options.
    Step 5: Click Search.
    """
    # Dump all selects so we can see what's there
    dump_form_info(page)
    screenshot(page, "04_before_form_fill")

    # --- Step 3: Business Type (2nd option by index) ---
    bt_set = False
    # Try common selector patterns
    for bt_sel in [
        "select[id*='usinessType']",
        "select[name*='usinessType']",
        "select[id*='business']",
        "select[name*='business']",
    ]:
        try:
            el = page.locator(bt_sel).first
            if el.count() > 0:
                options = el.locator("option").all()
                print(f"  [form] Business Type options: {[o.inner_text().strip() for o in options]}")
                if len(options) >= 2:
                    val = options[1].get_attribute("value")
                    el.select_option(value=val)
                    print(f"  [form] Business Type set to index [1]: '{options[1].inner_text().strip()}'")
                    bt_set = True
                    time.sleep(0.8)
                    break
        except Exception as e:
            print(f"  [form] bt_sel {bt_sel} error: {e}")

    if not bt_set:
        # Try the first select on the page as a fallback
        try:
            selects = page.locator("select").all()
            if selects:
                options = selects[0].locator("option").all()
                if len(options) >= 2:
                    val = options[1].get_attribute("value")
                    selects[0].select_option(value=val)
                    print(f"  [form] Business Type set via first select, index [1]")
                    bt_set = True
                    time.sleep(0.8)
        except Exception as e:
            print(f"  [form] fallback bt error: {e}")

    if not bt_set:
        screenshot(page, "ERROR_business_type_not_set")
        print("  [form] WARNING: could not set Business Type")

    debug_shot(page, "05_after_business_type")

    # --- Step 4: Type of Insurance ---
    # After selecting Business Type, the ToI field may reload (AJAX).
    time.sleep(1.5)
    dump_form_info(page)  # re-dump to see updated options

    toi_set = False
    for toi_sel in [
        "select[id*='nsurance']",
        "select[name*='nsurance']",
        "select[id*='nsuranc']",
        "select[id*='typeOf']",
        "select[name*='typeOf']",
    ]:
        try:
            el = page.locator(toi_sel).first
            if el.count() > 0:
                options = el.locator("option").all()
                opt_texts = [o.inner_text().strip() for o in options]
                print(f"  [form] ToI options ({len(opt_texts)}): {opt_texts[:15]}")
                # Select all options containing 'supp' (case-insensitive)
                supp_vals = [
                    o.get_attribute("value")
                    for o in options
                    if "supp" in o.inner_text().lower() and o.get_attribute("value")
                ]
                if supp_vals:
                    el.select_option(value=supp_vals)
                    print(f"  [form] ToI: selected {len(supp_vals)} 'supp' option(s): {supp_vals}")
                    toi_set = True
                    time.sleep(0.5)
                    break
                else:
                    print(f"  [form] ToI: no 'supp' options in this select, trying next ...")
        except Exception as e:
            print(f"  [form] toi_sel {toi_sel} error: {e}")

    if not toi_set:
        screenshot(page, "ERROR_toi_not_set")
        print("  [form] WARNING: could not set Type of Insurance")

    debug_shot(page, "06_after_toi")

    # --- Step 5: Click Search ---
    clicked_search = False
    for btn_sel in [
        "input[type='submit'][value*='earch' i]",
        "button[type='submit']",
        "input[type='submit']",
        "button:has-text('Search')",
        "a:has-text('Search')",
    ]:
        try:
            el = page.locator(btn_sel).first
            if el.is_visible(timeout=2000):
                el.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1.5)
                clicked_search = True
                break
        except Exception:
            pass

    if not clicked_search:
        screenshot(page, "ERROR_search_not_clicked")
        raise RuntimeError("Could not click the Search button")

    debug_shot(page, "07_after_search")
    print(f"  [form] after search, URL: {page.url}")


def sort_by_filing_status(page):
    try:
        page.get_by_text("Filing Status", exact=False).first.click(timeout=5000)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(0.8)
    except Exception:
        pass


def collect_matching_rows(page) -> list[dict]:
    matches = []
    page_num = 0

    while True:
        page_num += 1
        rows = page.locator("tr").all()
        for row in rows:
            try:
                text = row.inner_text()
            except Exception:
                continue
            if FILING_STATUS_FILTER in text and FILING_TYPE_FILTER in text:
                href = None
                try:
                    href = row.locator("a").first.get_attribute("href")
                except Exception:
                    pass
                matches.append({"text": text.strip(), "href": href, "page": page_num})

        # Next page
        try:
            next_btn = page.get_by_role("link", name=re.compile(r"next|>", re.I)).first
            if next_btn.is_visible(timeout=1000):
                next_btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(0.8)
            else:
                break
        except Exception:
            break

    return matches


def download_filing(page, row: dict, output_dir: Path):
    href = row.get("href")
    if not href:
        print("  [nav] no href -- skipping")
        return None, None

    url = href if href.startswith("http") else SERFF_BASE + href
    try:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(1.5)
    except Exception as e:
        print(f"  [nav] navigate error: {e}")
        return None, url

    if "session" in page.url.lower() and "expired" in page.content().lower():
        raise RuntimeError("Session expired")

    for btn_text in ["Select All", "Select all"]:
        try:
            for b in page.get_by_text(btn_text, exact=False).all():
                if b.is_visible():
                    b.click()
                    time.sleep(0.3)
        except Exception:
            pass

    try:
        with page.expect_download(timeout=60000) as dl_info:
            page.get_by_text("Download Zip File", exact=False).first.click()
        dl = dl_info.value
        slug = re.sub(r"[^\w\-]", "_", page.url.split("/")[-1] or "filing")
        dest = output_dir / f"{slug}.zip"
        output_dir.mkdir(parents=True, exist_ok=True)
        dl.save_as(str(dest))
        print(f"  [dl] saved -> {dest}")
        return dest, None
    except PWTimeout:
        screenshot(page, f"dl_timeout_{int(time.time())}")
        return None, page.url
    except Exception as e:
        screenshot(page, f"dl_error_{int(time.time())}")
        print(f"  [dl] error: {e}")
        return None, page.url


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    global DEBUG_MODE
    parser = argparse.ArgumentParser(description="SERFF TX Application downloader")
    parser.add_argument("--no-github", action="store_true", help="Skip GitHub upload")
    parser.add_argument("--limit", type=int, default=0, help="Max filings to process (0=all)")
    parser.add_argument("--debug", action="store_true", help="Extra screenshots at each step")
    args = parser.parse_args()
    DEBUG_MODE = args.debug

    log = load_log()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()

        try:
            go_to_search_page(page)

            all_rows: list[dict] = []
            try:
                fill_search_form(page)
                sort_by_filing_status(page)
                rows = collect_matching_rows(page)
                print(f"  -> {len(rows)} matching rows found")
                all_rows.extend(rows)
            except Exception as e:
                screenshot(page, f"search_error_{int(time.time())}")
                print(f"  [error] {e}")

            # Deduplicate
            seen = set()
            unique_rows = []
            for r in all_rows:
                key = r.get("href") or r.get("text", "")[:80]
                if key not in seen:
                    seen.add(key)
                    unique_rows.append(r)

            todo = [r for r in unique_rows if (r.get("href") or "") not in log["downloaded"]]
            if args.limit:
                todo = todo[:args.limit]

            print(f"\n[run] {len(unique_rows)} unique | {len(todo)} to process")

            for i, row in enumerate(todo, 1):
                print(f"\n[{i}/{len(todo)}] {row.get('text', '')[:80]}")
                try:
                    local_path, fallback = download_filing(page, row, OUTPUT_DIR)
                except RuntimeError as e:
                    if "Session expired" in str(e):
                        go_to_search_page(page)
                        local_path, fallback = download_filing(page, row, OUTPUT_DIR)
                    else:
                        raise

                if local_path:
                    log["downloaded"].append(row.get("href") or str(local_path))
                    if not args.no_github:
                        upload_to_github(local_path, local_path.name)
                elif fallback:
                    log["links"].append(fallback)
                    print(f"  [link] {fallback}")

                save_log(log)

        finally:
            context.close()
            browser.close()

    print(f"\n[done] Downloaded: {len(log['downloaded'])} | Links: {len(log['links'])}")
    if log["links"]:
        print("Links:")
        for lnk in log["links"]:
            print(f"  {lnk}")


if __name__ == "__main__":
    main()
