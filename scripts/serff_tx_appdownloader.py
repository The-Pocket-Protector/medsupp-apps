#!/usr/bin/env python3
"""
serff_tx_appdownloader.py
--------------------------
Searches SERFF Filing Access for Texas filings:
  - Business Type: 2nd option ("Life, Accident/Health, Annuity, Credit")
  - Type of Insurance: select all options containing "supp"

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

# Realistic Chrome user-agent to avoid bot detection
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

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
# Navigation
# ---------------------------------------------------------------------------

def go_to_search_page(page):
    """
    Navigate through SERFF home -> Begin Search.
    Must go through home to get the state session cookie.
    Uses realistic browser headers to avoid 403 bot detection.
    """
    print("  [nav] navigating to TX home ...")
    page.goto(f"{SERFF_BASE}/sfa/home/TX", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15000)
    except Exception:
        pass
    time.sleep(2)

    # Check for 403
    body_text = ""
    try:
        body_text = page.locator("body").inner_text()
    except Exception:
        pass
    if "403" in body_text or "Forbidden" in body_text:
        screenshot(page, "ERROR_403")
        raise RuntimeError(
            "SERFF returned 403 Forbidden.\n"
            "This means SERFF is blocking automated access.\n"
            "Try running with --headed flag to use a visible browser window.\n"
            "See instructions below."
        )

    dshot(page, "01_home")
    print(f"  [nav] home loaded, URL: {page.url}")
    print(f"  [nav] page title: {page.title()}")

    # Accept disclaimer if present
    for btn_text in ["I Agree", "Accept", "Agree", "OK", "Continue"]:
        try:
            btn = page.locator(f"button:has-text('{btn_text}'), input[value='{btn_text}']").first
            if btn.is_visible(timeout=1500):
                print(f"  [nav] accepting terms: {btn_text}")
                btn.click()
                page.wait_for_load_state("domcontentloaded")
                time.sleep(1)
                break
        except Exception:
            pass

    # Log all links for debugging
    links = page.locator("a").all()
    link_info = []
    for lnk in links[:30]:
        try:
            link_info.append((lnk.inner_text().strip(), lnk.get_attribute("href") or ""))
        except Exception:
            pass
    print(f"  [nav] links on home page: {link_info}")

    # Step 1: Click "Begin Search" — goes to userAgreement.xhtml
    for selector in [
        "a:has-text('Begin Search')",
        "a[href*='userAgreement']",
        "a:has-text('Search Filings')",
        "a:has-text('Filing Search')",
        "a[href*='filingSearch']",
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                print(f"  [nav] clicking: {selector}")
                el.click()
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                time.sleep(1.5)
                break
        except Exception:
            pass

    dshot(page, "02_after_begin_search")
    print(f"  [nav] URL: {page.url}")

    # Step 2: If we landed on the user agreement page, accept it
    if "userAgreement" in page.url or "agreement" in page.url.lower():
        print("  [nav] on user agreement page — accepting ...")
        body_text = ""
        try:
            body_text = page.locator("body").inner_text()[:200]
        except Exception:
            pass
        print(f"  [nav] agreement page text: {body_text[:100]}")

        # Log all buttons/inputs on the page
        btns = page.locator("input[type='submit'], input[type='button'], button").all()
        btn_info = []
        for b in btns:
            try:
                btn_info.append((b.get_attribute("value") or b.inner_text(), b.get_attribute("type")))
            except Exception:
                pass
        print(f"  [nav] buttons on agreement page: {btn_info}")

        accepted = False
        # Try common accept button patterns
        for selector in [
            "input[value*='Agree' i]",
            "input[value*='Accept' i]",
            "input[value*='Continue' i]",
            "input[value*='Search' i]",
            "button:has-text('Agree')",
            "button:has-text('Accept')",
            "button:has-text('Continue')",
            "button:has-text('I Agree')",
            "a:has-text('Agree')",
            "a:has-text('Accept')",
            "a:has-text('Continue')",
            "a:has-text('I Agree')",
            # Last resort: first submit button on the page
            "input[type='submit']:first-of-type",
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1500):
                    print(f"  [nav] accepting agreement via: {selector}")
                    el.click()
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    time.sleep(2)
                    accepted = True
                    break
            except Exception:
                pass

        if not accepted:
            screenshot(page, "ERROR_agreement_not_accepted")
            print("  [nav] WARNING: could not accept agreement")

    dshot(page, "03_after_agreement")
    print(f"  [nav] URL after agreement: {page.url}")

    # Step 3: Now wait for the actual filing search form
    print("  [nav] waiting for search form to render ...")
    try:
        page.wait_for_selector("select", timeout=20000)
        print("  [nav] form is ready")
    except PWTimeout:
        body_text = ""
        try:
            body_text = page.locator("body").inner_text()[:400]
        except Exception:
            pass
        screenshot(page, "ERROR_form_never_rendered")
        print(f"  [nav] page body: {body_text}")
        # Log all links in case there's another click needed
        links = page.locator("a").all()
        link_info = [(l.inner_text().strip(), l.get_attribute("href") or "") for l in links[:20]]
        print(f"  [nav] links: {link_info}")
        raise RuntimeError(
            f"Search form never rendered. Page body: {body_text[:150]}"
        )

    dshot(page, "04_form_ready")


def dump_form_info(page):
    selects = page.locator("select").all()
    print(f"  [form] {len(selects)} select(s):")
    for i, sel in enumerate(selects):
        try:
            sid = sel.get_attribute("id") or sel.get_attribute("name") or f"[{i}]"
            opts = [o.inner_text().strip() for o in sel.locator("option").all()[:15]]
            print(f"    [{i}] id={sid}: {opts}")
        except Exception:
            pass


def fill_search_form(page):
    dump_form_info(page)
    dshot(page, "05_before_fill")

    selects = page.locator("select").all()
    if not selects:
        screenshot(page, "ERROR_no_selects")
        raise RuntimeError("No <select> elements on search form")

    # Business Type — find option whose text contains "Life" (not "-- Select --" or "Property")
    bt_options = selects[0].locator("option").all()
    print(f"  [form] Business Type options: {[o.inner_text().strip() for o in bt_options]}")
    life_val = None
    for o in bt_options:
        txt = o.inner_text().strip()
        if "life" in txt.lower() or "accident" in txt.lower() or "health" in txt.lower():
            life_val = o.get_attribute("value")
            print(f"  [form] Business Type -> '{txt}' (value={life_val})")
            break
    if life_val:
        selects[0].select_option(value=life_val)
    else:
        # Fallback: last non-blank option
        non_blank = [o for o in bt_options if o.get_attribute("value") and o.inner_text().strip() != "-- Select --"]
        if non_blank:
            val = non_blank[-1].get_attribute("value")
            selects[0].select_option(value=val)
            print(f"  [form] Business Type fallback -> '{non_blank[-1].inner_text().strip()}'")
        else:
            print("  [form] WARNING: could not find Life/Health Business Type option")

    # Wait for Type of Insurance widget to appear after BT selection (AJAX)
    print("  [form] waiting for Type of Insurance widget to populate ...")
    time.sleep(1.5)

    # SERFF uses a PrimeFaces multi-select widget — NOT a native <select>.
    # The widget has:
    #   - a label/button to open the panel (role=combobox or a div with the field label)
    #   - a filter input inside the panel
    #   - checkboxes for each option
    # Strategy: find the ToI widget container, click it to open, type "supp", check all.

    # Dump everything visible for debugging
    dump_form_info(page)
    dshot(page, "06_after_bt")

    # Log all input elements to find the filter box
    inputs = page.locator("input").all()
    input_info = []
    for inp in inputs:
        try:
            input_info.append({
                "id": inp.get_attribute("id"),
                "name": inp.get_attribute("name"),
                "type": inp.get_attribute("type"),
                "placeholder": inp.get_attribute("placeholder"),
                "class": inp.get_attribute("class"),
                "visible": inp.is_visible(),
            })
        except Exception:
            pass
    print(f"  [form] inputs on page: {input_info}")

    # Step 1: Open the Type of Insurance panel by clicking the widget trigger
    # PrimeFaces multi-select is typically a div or span with role="listbox" parent,
    # or a label that says "Type of Insurance" or "-- Select --" nearby.
    toi_opened = False
    for trigger_sel in [
        # PrimeFaces multi-select trigger button (the dropdown arrow)
        "[id*='typeOfInsurance'] .ui-multiselect",
        "[id*='typeOfInsurance'] .ui-selectonemenu",
        "[id*='typeOfInsurance']",
        "[id*='TypeOfInsurance']",
        "[id*='insuranceType']",
        # Generic: any multiselect widget that isn't the business type one
        ".ui-multiselect:not([id*='businessType'])",
        ".ui-selectmanymenu:not([id*='businessType'])",
        # Try clicking the label text
        "label:has-text('Type of Insurance')",
        "span:has-text('Type of Insurance')",
    ]:
        try:
            el = page.locator(trigger_sel).first
            if el.is_visible(timeout=1500):
                print(f"  [form] clicking ToI trigger: {trigger_sel}")
                el.click()
                time.sleep(0.8)
                toi_opened = True
                break
        except Exception:
            pass

    if not toi_opened:
        print("  [form] WARNING: could not find/open ToI widget directly")
        screenshot(page, "ERROR_toi_widget_not_found")

    dshot(page, "06b_after_toi_open")

    # Step 2: Type "supp" into the filter input (may be visible after opening the panel)
    typed = False
    for filter_sel in [
        "[id*='typeOfInsurance'] input[type='text']",
        "[id*='typeOfInsurance'] input",
        "[id*='TypeOfInsurance'] input",
        ".ui-multiselect-filter-input",
        ".ui-multiselect input",
        "input[id*='filter' i]",
        "input[placeholder*='filter' i]",
        "input[placeholder*='search' i]",
    ]:
        try:
            el = page.locator(filter_sel).first
            if el.is_visible(timeout=1500):
                print(f"  [form] typing 'supp' into filter: {filter_sel}")
                el.click()
                el.fill("")
                el.type("supp", delay=80)
                time.sleep(1.0)  # wait for filter to apply
                typed = True
                break
        except Exception:
            pass

    if not typed:
        print("  [form] could not find filter input — will try checking all visible checkboxes")

    dshot(page, "06c_after_type_supp")

    # Step 3: Check all visible checkboxes in the filtered list
    # Log what checkboxes are now visible
    checkboxes = page.locator("input[type='checkbox']").all()
    cb_info = []
    for cb in checkboxes:
        try:
            cb_info.append({
                "id": cb.get_attribute("id"),
                "value": cb.get_attribute("value"),
                "visible": cb.is_visible(),
                "checked": cb.is_checked(),
            })
        except Exception:
            pass
    print(f"  [form] checkboxes: {cb_info}")

    checked_count = 0
    for cb in checkboxes:
        try:
            if cb.is_visible() and not cb.is_checked():
                # Skip the "select all" checkbox (usually has no value or value="on")
                val = cb.get_attribute("value") or ""
                cb.check()
                checked_count += 1
        except Exception:
            pass
    print(f"  [form] checked {checked_count} checkbox(es)")

    if checked_count == 0 and not typed:
        screenshot(page, "ERROR_no_checkboxes_checked")
        print("  [form] WARNING: no checkboxes were checked — ToI may not have filtered correctly")

    time.sleep(0.5)
    dshot(page, "07_after_toi")

    # Click Search
    for selector in [
        "input[type='submit'][value*='earch' i]",
        "input[type='submit']",
        "button[type='submit']",
        "button:has-text('Search')",
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
                dshot(page, "08_results")
                print(f"  [form] results URL: {page.url}")
                return
        except Exception:
            pass

    screenshot(page, "ERROR_no_search_button")
    raise RuntimeError("Could not find/click the Search button")


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
    except Exception:
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
    parser.add_argument("--headed", action="store_true",
                        help="Run with visible browser window (use if getting 403)")
    args = parser.parse_args()
    DEBUG_MODE = args.debug

    log = load_log()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=not args.headed,
            args=[
                "--disable-blink-features=AutomationControlled",
            ]
        )
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            accept_downloads=True,
            locale="en-US",
            timezone_id="America/Chicago",
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        # Remove webdriver flag that gives away automation
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
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
