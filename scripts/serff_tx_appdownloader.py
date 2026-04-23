#!/usr/bin/env python3
"""
serff_tx_appdownloader.py
--------------------------
Searches SERFF Filing Access for Texas filings:
  - Business Type: 2nd option ("Life, Accident/Health, Annuity, Credit")
  - Type of Insurance: type "supp" in filter, check all results

Targets "Closed-Approved" Application filings, downloads ZIPs, uploads to GitHub.

Requirements:
    pip install playwright requests PyGithub
    playwright install chromium

Usage:
    python serff_tx_appdownloader.py --limit 5 --debug
    python serff_tx_appdownloader.py --no-github
    python serff_tx_appdownloader.py
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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO  = os.environ.get("GITHUB_REPO", "")
GITHUB_PATH  = os.environ.get("GITHUB_PATH", "filings/TX")

FILING_STATUS_FILTER = "Closed-Approved"
FILING_TYPE_FILTER   = "Application"

DEBUG_MODE = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_log():
    if LOG_FILE.exists():
        return json.loads(LOG_FILE.read_text())
    return {"downloaded": [], "failed": [], "links": []}

def save_log(log):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    LOG_FILE.write_text(json.dumps(log, indent=2))

def screenshot(page, name):
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        print(f"  [debug] screenshot -> {path}")
    except Exception as e:
        print(f"  [debug] screenshot failed: {e}")

def dshot(page, name):
    if DEBUG_MODE:
        screenshot(page, name)

def upload_to_github(local_path, filename):
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  [github] token/repo not set -- skipping")
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
        except Exception:
            repo.create_file(remote_path, f"Add {filename}", content)
        print(f"  [github] committed {remote_path}")
        return True
    except Exception as e:
        print(f"  [github] error: {e}")
        return False

# ---------------------------------------------------------------------------
# Navigation — must go through home page to set state cookie
# ---------------------------------------------------------------------------

def go_to_search_page(page):
    """
    SERFF requires the state context cookie from /sfa/home/TX.
    Direct navigation to filingSearch.xhtml gives a blank page without it.
    Flow: home -> accept terms if any -> click Begin Search -> wait for form.
    """
    print("  [nav] navigating to TX home ...")
    page.goto(f"{SERFF_BASE}/sfa/home/TX", wait_until="domcontentloaded")

    # Wait for page to settle (SERFF uses JSF which needs JS to run)
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)
    dshot(page, "01_home")
    print(f"  [nav] home loaded, URL: {page.url}")

    # Accept any disclaimer/terms modal
    for btn_text in ["I Agree", "Accept", "Agree", "OK"]:
        try:
            btn = page.locator(f"button:has-text('{btn_text}'), input[value='{btn_text}']").first
            if btn.is_visible(timeout=1500):
                print(f"  [nav] clicking terms button: {btn_text}")
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                dshot(page, "02_after_terms")
                break
        except Exception:
            pass

    # Click "Begin Search" — it should be a link on the home page
    clicked = False
    for selector in [
        "a:has-text('Begin Search')",
        "a:has-text('Search Filings')",
        "a:has-text('Filing Search')",
        "input[value*='Search' i][type='button']",
        "input[value*='Search' i][type='submit']",
        "button:has-text('Search')",
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=3000):
                print(f"  [nav] clicking: {selector}")
                el.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(2)
                clicked = True
                break
        except Exception:
            pass

    if not clicked:
        # Log what links are on the page for debugging
        links = page.locator("a").all()
        link_texts = []
        for lnk in links[:20]:
            try:
                link_texts.append(lnk.inner_text().strip())
            except Exception:
                pass
        print(f"  [nav] WARNING: could not find Begin Search. Page links: {link_texts}")
        screenshot(page, "ERROR_no_begin_search")

    dshot(page, "03_after_click")
    print(f"  [nav] URL after click: {page.url}")

    # Now wait for the search form to actually render
    # SERFF's JSF form renders <select> elements — wait for one to appear
    print("  [nav] waiting for search form to render ...")
    try:
        page.wait_for_selector("select", timeout=20000)
        print("  [nav] form is ready")
    except PWTimeout:
        screenshot(page, "ERROR_form_never_rendered")
        # Dump page content for debugging
        body = page.locator("body").inner_text()[:500]
        print(f"  [nav] page body text: {body}")
        raise RuntimeError("Search form never rendered — SERFF may require login or session is invalid")

    dshot(page, "04_form_ready")


def dump_form_info(page):
    """Print all select IDs and options for debugging."""
    selects = page.locator("select").all()
    print(f"  [form] {len(selects)} select(s) on page:")
    for i, sel in enumerate(selects):
        try:
            sid = sel.get_attribute("id") or sel.get_attribute("name") or f"[{i}]"
            opts = [o.inner_text().strip() for o in sel.locator("option").all()[:12]]
            print(f"    select id={sid}: {opts}")
        except Exception:
            pass


def fill_search_form(page):
    """
    Step 3: Select Business Type = 2nd option.
    Step 4: Select all Type of Insurance options containing 'supp'.
    Step 5: Click Search.
    """
    dump_form_info(page)
    dshot(page, "05_before_fill")

    # --- Business Type: select 2nd option by index ---
    selects = page.locator("select").all()
    if not selects:
        screenshot(page, "ERROR_no_selects")
        raise RuntimeError("No <select> elements found on search form")

    # First select is typically Business Type
    bt_select = selects[0]
    bt_options = bt_select.locator("option").all()
    print(f"  [form] Business Type options: {[o.inner_text().strip() for o in bt_options]}")

    if len(bt_options) >= 2:
        val = bt_options[1].get_attribute("value")
        bt_select.select_option(value=val)
        print(f"  [form] Business Type set to: '{bt_options[1].inner_text().strip()}'")
    else:
        print("  [form] WARNING: Business Type has fewer than 2 options")

    # Wait for Type of Insurance to populate (AJAX reload after BT selection)
    time.sleep(2)
    try:
        page.wait_for_function("document.querySelectorAll('select').length >= 2", timeout=10000)
    except Exception:
        pass
    dump_form_info(page)
    dshot(page, "06_after_bt")

    # --- Type of Insurance: second select, pick all options containing 'supp' ---
    selects = page.locator("select").all()
    if len(selects) < 2:
        screenshot(page, "ERROR_no_toi_select")
        print("  [form] WARNING: only 1 select found after Business Type change")
        toi_select = selects[0]
    else:
        toi_select = selects[1]

    toi_options = toi_select.locator("option").all()
    print(f"  [form] ToI options ({len(toi_options)}): {[o.inner_text().strip() for o in toi_options]}")

    supp_vals = [
        o.get_attribute("value")
        for o in toi_options
        if "supp" in o.inner_text().lower() and o.get_attribute("value")
    ]

    if supp_vals:
        toi_select.select_option(value=supp_vals)
        print(f"  [form] ToI: selected {len(supp_vals)} option(s)")
    else:
        print("  [form] WARNING: no 'supp' options found — selecting all non-blank options")
        all_vals = [
            o.get_attribute("value")
            for o in toi_options
            if o.get_attribute("value") and o.get_attribute("value") != ""
        ]
        if all_vals:
            toi_select.select_option(value=all_vals)
            print(f"  [form] ToI: selected all {len(all_vals)} option(s)")

    time.sleep(0.5)
    dshot(page, "07_after_toi")

    # --- Click Search button ---
    clicked = False
    for selector in [
        "input[type='submit'][value*='earch' i]",
        "input[type='submit']",
        "button[type='submit']",
        "button:has-text('Search')",
        "a:has-text('Search')",
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                print(f"  [form] clicking search: {selector}")
                el.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=20000)
                except Exception:
                    pass
                time.sleep(1.5)
                clicked = True
                break
        except Exception:
            pass

    if not clicked:
        screenshot(page, "ERROR_no_search_button")
        raise RuntimeError("Could not find/click the Search button")

    dshot(page, "08_search_results")
    print(f"  [form] search submitted, URL: {page.url}")


def sort_by_filing_status(page):
    try:
        page.get_by_text("Filing Status", exact=False).first.click(timeout=5000)
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(0.8)
    except Exception:
        pass


def collect_matching_rows(page):
    matches = []
    page_num = 0
    while True:
        page_num += 1
        for row in page.locator("tr").all():
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
            nxt = page.get_by_role("link", name=re.compile(r"next|>", re.I)).first
            if nxt.is_visible(timeout=1000):
                nxt.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                time.sleep(0.8)
            else:
                break
        except Exception:
            break
    return matches


def download_filing(page, row, output_dir):
    href = row.get("href")
    if not href:
        return None, None
    url = href if href.startswith("http") else SERFF_BASE + href
    try:
        page.goto(url, wait_until="domcontentloaded")
        time.sleep(1.5)
    except Exception as e:
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
# Main
# ---------------------------------------------------------------------------

def main():
    global DEBUG_MODE
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-github", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--debug", action="store_true")
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
            all_rows = []
            try:
                fill_search_form(page)
                sort_by_filing_status(page)
                rows = collect_matching_rows(page)
                print(f"  -> {len(rows)} matching rows")
                all_rows.extend(rows)
            except Exception as e:
                screenshot(page, f"search_error_{int(time.time())}")
                print(f"  [error] {e}")

            seen = set()
            unique = []
            for r in all_rows:
                k = r.get("href") or r.get("text", "")[:80]
                if k not in seen:
                    seen.add(k)
                    unique.append(r)

            todo = [r for r in unique if (r.get("href") or "") not in log["downloaded"]]
            if args.limit:
                todo = todo[:args.limit]

            print(f"\n[run] {len(unique)} unique | {len(todo)} to process")

            for i, row in enumerate(todo, 1):
                print(f"\n[{i}/{len(todo)}] {row.get('text','')[:80]}")
                try:
                    lp, fb = download_filing(page, row, OUTPUT_DIR)
                except RuntimeError as e:
                    if "Session expired" in str(e):
                        go_to_search_page(page)
                        lp, fb = download_filing(page, row, OUTPUT_DIR)
                    else:
                        raise

                if lp:
                    log["downloaded"].append(row.get("href") or str(lp))
                    if not args.no_github:
                        upload_to_github(lp, lp.name)
                elif fb:
                    log["links"].append(fb)
                    print(f"  [link] {fb}")
                save_log(log)

        finally:
            context.close()
            browser.close()

    print(f"\n[done] Downloaded: {len(log['downloaded'])} | Links: {len(log['links'])}")
    if log["links"]:
        print("Links (fallback):")
        for lnk in log["links"]:
            print(f"  {lnk}")


if __name__ == "__main__":
    main()
