#!/usr/bin/env python3
"""
serff_tx_appdownloader.py
--------------------------
Searches SERFF Filing Access for Texas Health / Individual Supplement
"Closed-Approved" Application filings, downloads the ZIP for each,
and (optionally) uploads them to the MEDSUPP GitHub repo.

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
import sys
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
GITHUB_TOKEN   = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO    = os.environ.get("GITHUB_REPO", "")   # e.g. "YourOrg/medsupp-apps"
GITHUB_PATH    = os.environ.get("GITHUB_PATH", "filings/TX")  # folder in repo

# SERFF search parameters
BUSINESS_TYPE  = "Health"
# All "Individual Supplement" options visible in the Type of Insurance dropdown
SUPPLEMENT_OPTIONS = [
    "Medicare Supplement",
    "Medicare Select",
    "Long Term Care",
    "Dental",
    "Vision",
    "Disability Income",
    "Accident Only",
    "Specified Disease",
    "Hospital Indemnity",
    "Critical Illness",
    "Cancer",
    "Limited Benefit",
]
FILING_STATUS_FILTER = "Closed-Approved"
FILING_TYPE_FILTER   = "Application"  # Filing Status must also contain this

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
    print(f"  [debug] screenshot → {path}")

def upload_to_github(local_path: Path, filename: str):
    """Push a file to the configured GitHub repo."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        print("  [github] GITHUB_TOKEN or GITHUB_REPO not set — skipping upload")
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
# Main scraper
# ---------------------------------------------------------------------------

def establish_session(page):
    """Navigate to TX home and click Begin Search."""
    print("  [session] establishing TX session …")
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
    # Click Begin Search (tries several variants)
    for link_text in ["Begin Search", "Search Filings", "Continue", "Search"]:
        try:
            page.get_by_text(link_text, exact=False).first.click(timeout=3000)
            page.wait_for_load_state("networkidle")
            time.sleep(0.5)
            break
        except Exception:
            pass
    print(f"  [session] landed on: {page.url}")


def fill_search_form(page, supplement_option: str):
    """Select Health + one supplement type and submit."""
    # Business Type → Health
    try:
        page.select_option("select[id*='businessType'], select[name*='businessType']",
                           label=BUSINESS_TYPE)
        time.sleep(0.5)
    except Exception:
        # Try by visible text
        page.locator("select").filter(has_text="Health").first.select_option(label=BUSINESS_TYPE)
        time.sleep(0.5)

    # Type of Insurance → supplement option
    try:
        page.select_option("select[id*='typeOfInsurance'], select[name*='typeOfInsurance']",
                           label=supplement_option)
    except Exception:
        pass  # option might not exist for this state; skip

    # Click Search
    try:
        page.get_by_role("button", name=re.compile("search", re.I)).first.click()
    except Exception:
        page.locator("input[type='submit'], button[type='submit']").first.click()
    page.wait_for_load_state("networkidle")
    time.sleep(1)


def sort_by_filing_status(page):
    """Click the Filing Status column header to sort."""
    try:
        page.get_by_text("Filing Status", exact=False).first.click(timeout=3000)
        page.wait_for_load_state("networkidle")
        time.sleep(0.5)
    except Exception:
        pass


def collect_matching_rows(page) -> list[dict]:
    """
    Page through results, collecting rows where Filing Status is
    'Closed-Approved' and contains 'Application'.
    Returns list of {text, href} dicts.
    """
    matches = []
    page_num = 0

    while True:
        page_num += 1
        rows = page.locator("tr").all()
        found_any_application = False

        for row in rows:
            text = row.inner_text()
            if FILING_STATUS_FILTER in text and FILING_TYPE_FILTER in text:
                found_any_application = True
                # Try to get a clickable link in the row
                href = None
                try:
                    link = row.locator("a").first
                    href = link.get_attribute("href")
                except Exception:
                    pass
                matches.append({"text": text.strip(), "href": href, "page": page_num})

        # Pagination — look for Next button
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


def download_filing(page, row: dict, output_dir: Path) -> tuple[Path | None, str | None]:
    """
    Navigate to the filing summary, select all attachments, download ZIP.
    Returns (local_zip_path, None) on success or (None, url_link) on failure.
    """
    href = row.get("href")
    if href:
        url = href if href.startswith("http") else SERFF_BASE + href
        try:
            page.goto(url, wait_until="networkidle")
            time.sleep(1)
        except Exception as e:
            print(f"  [nav] failed to navigate to {url}: {e}")
            return None, url
    else:
        # Try clicking the row text to find the filing
        print("  [nav] no direct href — skipping (no link to click)")
        return None, None

    # Check for session expiry
    if "session" in page.url.lower() and "expired" in page.content().lower():
        raise RuntimeError("Session expired")

    # Click "Select All" in each attachment section
    for btn_text in ["Select All", "Select all", "SelectAll"]:
        try:
            btns = page.get_by_text(btn_text, exact=False).all()
            for b in btns:
                if b.is_visible():
                    b.click()
                    time.sleep(0.3)
        except Exception:
            pass

    # Download the ZIP
    try:
        with page.expect_download(timeout=60000) as dl_info:
            page.get_by_text("Download Zip File", exact=False).first.click()
        download = dl_info.value
        # Derive filename from tracking number in URL or page title
        slug = re.sub(r"[^\w\-]", "_", page.url.split("/")[-1] or "filing")
        dest = output_dir / f"{slug}.zip"
        output_dir.mkdir(parents=True, exist_ok=True)
        download.save_as(str(dest))
        print(f"  [dl] saved → {dest}")
        return dest, None
    except PWTimeout:
        screenshot(page, f"dl_timeout_{int(time.time())}")
        print("  [dl] download timed out — collecting link instead")
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

            all_rows: list[dict] = []

            for option in SUPPLEMENT_OPTIONS:
                print(f"\n[search] Business=Health | TypeOfInsurance={option}")
                try:
                    # Re-establish search form for each option
                    if "/filingSearch" not in page.url:
                        establish_session(page)
                    fill_search_form(page, option)
                    sort_by_filing_status(page)
                    rows = collect_matching_rows(page)
                    print(f"  → {len(rows)} matching rows")
                    all_rows.extend(rows)
                except Exception as e:
                    screenshot(page, f"search_error_{option.replace(' ', '_')}")
                    print(f"  [error] {option}: {e}")
                    try:
                        establish_session(page)
                    except Exception:
                        pass

            # Deduplicate by href
            seen_hrefs = set()
            unique_rows = []
            for r in all_rows:
                key = r.get("href") or r.get("text", "")[:80]
                if key not in seen_hrefs:
                    seen_hrefs.add(key)
                    unique_rows.append(r)

            # Filter already downloaded
            todo = [r for r in unique_rows
                    if (r.get("href") or "") not in log["downloaded"]]

            if args.limit:
                todo = todo[:args.limit]

            print(f"\n[run] {len(unique_rows)} unique matches | {len(todo)} to process")

            for i, row in enumerate(todo, 1):
                print(f"\n[{i}/{len(todo)}] {row.get('text','')[:80]}")
                try:
                    local_path, fallback_link = download_filing(page, row, OUTPUT_DIR)
                except RuntimeError as e:
                    if "Session expired" in str(e):
                        print("  [session] re-establishing …")
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
                        # Append link to a text file in the repo
                        links_path = Path("output/pdfs/TX/_links.txt")
                        links_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(links_path, "a") as f:
                            f.write(fallback_link + "\n")

                save_log(log)

        finally:
            context.close()
            browser.close()

    # Summary
    print(f"\n[done]")
    print(f"  Downloaded : {len(log['downloaded'])}")
    print(f"  Links only : {len(log['links'])}")
    print(f"  Log        : {LOG_FILE}")
    if log["links"]:
        print("\nLinks (could not download ZIP):")
        for l in log["links"]:
            print(f"  {l}")


if __name__ == "__main__":
    main()
