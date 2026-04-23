#!/usr/bin/env python3
"""
SERFF Medicare Supplement Application PDF Scraper - Full 47-State Run
Searches for Form filings with "Medicare Supplement" product name, status Approved.
"""

import json
import os
import subprocess
import time
import re
from pathlib import Path

os.environ["FIRECRAWL_API_KEY"] = "fc-94fa12dd36444846851cfcd972c23194"

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

RESULTS_FILE = OUTPUT_DIR / "all_states_results.json"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

SERFF_STATES = [
    "AL", "AK", "AZ", "AR", "CO", "CT", "DE", "DC", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME",
    "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NC", "ND", "OH", "OK", "OR", "PA",
    "RI", "SC", "SD", "TN", "TX", "UT", "VT", "VA", "WA",
    "WV", "WI", "WY"
]


def run_cmd(args: list, timeout: int = 60) -> tuple:
    env = os.environ.copy()
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1
    except Exception as e:
        return f"ERROR: {e}", -1


def stop_session():
    run_cmd(["firecrawl", "interact", "stop"], timeout=10)
    time.sleep(2)


def get_scrape_id(state: str) -> str | None:
    url = f"https://filingaccess.serff.com/sfa/home/{state}"
    out, code = run_cmd(["firecrawl", "scrape", url], timeout=45)
    if code != 0 or "403 Forbidden" in out:
        return None
    m = re.search(r'Scrape ID: ([a-f0-9-]+)', out)
    return m.group(1) if m else None


def interact(scrape_id: str, prompt: str, timeout: int = 90) -> str:
    out, _ = run_cmd([
        "firecrawl", "interact",
        "--scrape-id", scrape_id,
        "--prompt", prompt,
        "--timeout", str(timeout)
    ], timeout=timeout + 20)
    return out


def scrape_state(state: str) -> dict:
    print(f"\n[{state}] Starting...")
    result = {"state": state, "status": "pending", "filings": [], "errors": []}

    stop_session()
    time.sleep(2)

    scrape_id = get_scrape_id(state)
    if not scrape_id:
        result["status"] = "blocked"
        print(f"[{state}] Blocked/error on scrape")
        return result

    print(f"[{state}] Scrape ID: {scrape_id}")

    # Single comprehensive prompt: navigate → search → extract results only
    prompt = (
        "Complete all steps in sequence and return ONLY the final data, no page structure:\n"
        "1. Click the 'Begin Search' link\n"
        "2. Click 'Accept' on the terms page\n"
        "3. Select 'Life, Accident/Health, Annuity, Credit' from the Business Type dropdown\n"
        "4. Type 'Medicare Supplement' in the Insurance Product Name field and select 'Contains'\n"
        "5. Click Search and wait for results\n"
        "6. Change rows per page to 100\n"
        "7. Return ONLY this — nothing else, no page structure, no ARIA tree:\n"
        "   Line 1: TOTAL: <number> Filing(s) matching your criteria\n"
        "   Then one row per line: Company Name | NAIC Code | Product Name | Sub TOI | Filing Type | Status | SERFF Tracking #\n"
        "   If no results, return: TOTAL: 0\n"
        "Do NOT return any page HTML, ARIA tree, or navigation elements — ONLY the data rows."
    )

    out = interact(scrape_id, prompt, timeout=90)
    stop_session()

    print(f"[{state}] Output (first 600):\n{out[:600]}")

    if "TIMEOUT" in out:
        result["status"] = "timeout"
        result["errors"].append("Timed out on main interact")
    elif "rate limit" in out.lower() or "Rate limit" in out:
        result["status"] = "rate_limited"
        result["errors"].append(out[:200])
    elif "concurrent" in out.lower():
        result["status"] = "concurrent_limit"
        result["errors"].append(out[:200])
    else:
        result["status"] = "complete"
        result["raw_output"] = out[:20000]

        # Try to extract total count
        count_match = re.search(r'([\d,]+)\s+Filing\(s\)', out)
        if count_match:
            result["total_filings_str"] = count_match.group(0)
            print(f"[{state}] Found: {count_match.group(0)}")

    return result


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}


def save_progress(progress: dict):
    with open(PROGRESS_FILE, 'w') as f:
        json.dump(progress, f, indent=2)


def main():
    print("SERFF Medicare Supplement Scraper - Full Run")
    print(f"Output: {OUTPUT_DIR}")

    progress = load_progress()
    all_results = []

    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            all_results = json.load(f)

    completed_states = set(progress.get("completed", []))
    # Re-run states that hit transient errors
    retry_statuses = {"timeout", "rate_limited", "concurrent_limit", "pending"}
    retry_states = {r["state"] for r in all_results if r.get("status") in retry_statuses}
    completed_states -= retry_states
    # Remove retry states from all_results so we replace them
    all_results = [r for r in all_results if r["state"] not in retry_states]

    print(f"Completed: {len(completed_states)}, Retrying: {len(retry_states)}")

    remaining = [s for s in SERFF_STATES if s not in completed_states]
    print(f"Remaining: {len(remaining)} states")

    for i, state in enumerate(remaining):
        print(f"\n[{i+1}/{len(remaining)}] {state}")

        result = scrape_state(state)
        all_results.append(result)

        with open(RESULTS_FILE, 'w') as f:
            json.dump(all_results, f, indent=2)

        if result["status"] == "complete":
            completed_states.add(state)
        progress["completed"] = list(completed_states)
        save_progress(progress)

        # Polite delay between states — avoid rate limits
        if i < len(remaining) - 1:
            delay = 8 if result["status"] == "rate_limited" else 4
            time.sleep(delay)

    # Summary
    complete = [r for r in all_results if r["status"] == "complete"]
    blocked = [r for r in all_results if r["status"] == "blocked"]
    failed = [r for r in all_results if r["status"] not in ("complete", "blocked")]

    print(f"\n{'='*60}")
    print(f"DONE: {len(complete)} complete, {len(blocked)} blocked, {len(failed)} failed")
    if blocked:
        print(f"Blocked: {[r['state'] for r in blocked]}")
    if failed:
        print(f"Failed: {[(r['state'], r['status']) for r in failed]}")

    with_filings = [r for r in complete if r.get("total_filings_str")]
    print(f"States with filing count found: {len(with_filings)}")
    for r in with_filings:
        print(f"  {r['state']}: {r['total_filings_str']}")

    print(f"\nResults: {RESULTS_FILE}")


if __name__ == "__main__":
    main()
