#!/usr/bin/env python3
"""
SERFF Form Filing Scraper - extracts all Form/Application type filings for a state.
Uses pre-written JS step files to avoid shell/REPL variable conflicts.
"""

import json, time, requests, sys
from collections import Counter
from pathlib import Path

API_KEY = "fc-94fa12dd36444846851cfcd972c23194"
API_URL = "https://api.firecrawl.dev"
HEADERS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff")
STEPS_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/scripts/steps")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def create_session():
    r = requests.post(f"{API_URL}/v2/browser", headers=HEADERS, json={}, timeout=20)
    return r.json()["id"]


def execute(sid, code, timeout=30):
    r = requests.post(
        f"{API_URL}/v2/browser/{sid}/execute",
        headers=HEADERS, json={"code": code}, timeout=timeout + 5
    )
    d = r.json()
    return d.get("result", ""), d.get("stderr", "")


def execute_file(sid, filename, replacements=None, timeout=30):
    code = (STEPS_DIR / filename).read_text()
    if replacements:
        for k, v in replacements.items():
            code = code.replace(k, v)
    return execute(sid, code, timeout=timeout)


def delete_session(sid):
    try:
        requests.delete(f"{API_URL}/v2/browser/{sid}", headers=HEADERS, timeout=10)
    except Exception:
        pass


def scrape_state_forms(state):
    sid = None
    try:
        sid = create_session()
        print(f"[{state}] Session: {sid}")
        time.sleep(2)

        state_url = f"https://filingaccess.serff.com/sfa/home/{state}"

        # Step 1: Navigate to homepage
        result, err = execute_file(sid, "01_goto.js", {"PAGE_GOTO_URL": f'"{state_url}"'}, timeout=20)
        if err: print(f"[{state}] goto err: {err[:100]}")
        else: print(f"[{state}] goto: {json.loads(result).get('url')}")
        time.sleep(0.5)

        # Step 2: Click Begin Search
        result, err = execute_file(sid, "02_begin_search.js", timeout=15)
        if err: print(f"[{state}] begin err: {err[:100]}")
        time.sleep(0.5)

        # Step 3: Click Accept
        result, err = execute_file(sid, "03_accept.js", timeout=20)
        if err: print(f"[{state}] accept err: {err[:100]}")
        else:
            try: print(f"[{state}] accept: {json.loads(result).get('url')}")
            except: pass
        time.sleep(0.5)

        # Step 4: Select Business Type (waits for AJAX)
        result, err = execute_file(sid, "04_biz_type.js", timeout=20)
        if err: print(f"[{state}] biztype err: {err[:100]}")
        else:
            try: print(f"[{state}] biztype: TOI count={json.loads(result).get('toiCount')}")
            except: pass

        # Step 5a: Select TOI
        result, err = execute_file(sid, "05a_select_toi.js", timeout=15)
        if err: print(f"[{state}] TOI err: {err[:100]}")
        else:
            try: print(f"[{state}] TOI: {json.loads(result).get('toggled')}")
            except: pass
        time.sleep(0.3)

        # Step 5b: Click Search button
        result, err = execute_file(sid, "05b_click_search.js", timeout=20)
        if err: print(f"[{state}] search click err: {err[:100]}")
        time.sleep(0.5)

        # Step 5c: Set 100 rows + get total count
        result, err = execute_file(sid, "05c_set_rows_and_count.js", timeout=20)
        if err:
            print(f"[{state}] count err: {err[:150]}")
            return None
        if not result:
            print(f"[{state}] No count result")
            return None

        search_data = json.loads(result)
        total = search_data.get("total", 0)
        headers = search_data.get("hdrs", [])
        print(f"[{state}] Total: {total:,} | Headers: {headers}")

        if total == 0:
            return {"state": state, "total_in_serff": 0, "form_rows": []}

        filing_type_idx = next((i for i, h in enumerate(headers) if "Filing Type" in h), 4)

        # Step 6+7: Paginate
        all_rows = []
        for page_num in range(1, 40):
            result, err = execute_file(sid, "06_extract_page.js", timeout=15)
            if not result:
                print(f"[{state}] Page {page_num} empty: {err[:80]}")
                break

            try: page_data = json.loads(result)
            except Exception as e:
                print(f"[{state}] Page {page_num} parse: {e}")
                break

            rows = page_data.get("rows", [])
            has_next = page_data.get("has_next", False)
            page_info = page_data.get("page_info", "")

            form_rows = [r for r in rows if filing_type_idx < len(r) and
                         any(x in (r[filing_type_idx] or "").lower() for x in ["form", "application"])]
            all_rows.extend(form_rows)
            print(f"  Page {page_num}: {len(rows)} rows, {len(form_rows)} form/app ({page_info})", flush=True)

            if not has_next:
                break

            result, err = execute_file(sid, "07_next_page.js", timeout=15)
            if not result:
                print(f"  Next err: {err[:80]}")
                break
            try:
                if not json.loads(result).get("ok"):
                    break
            except:
                break

            time.sleep(0.2)

        # Build structured output
        result_filings = []
        for row in all_rows:
            obj = {h: row[i] if i < len(row) else "" for i, h in enumerate(headers) if h}
            obj["State"] = state
            serff_num = obj.get("SERFF Tracking Number", "")
            obj["SERFF URL"] = f"https://filingaccess.serff.com/sfa/filing/{serff_num}" if serff_num else ""
            result_filings.append(obj)

        return {"state": state, "total_in_serff": total, "form_rows": result_filings}

    except Exception as e:
        print(f"[{state}] Exception: {e}")
        return None
    finally:
        if sid:
            delete_session(sid)
            time.sleep(2)


def main():
    states = sys.argv[1:] if len(sys.argv) > 1 else ["KY"]

    for state in states:
        print(f"\n{'='*50}")
        print(f"Scraping {state}...")
        data = scrape_state_forms(state)

        if not data:
            print(f"[{state}] FAILED")
            continue

        filings = data["form_rows"]
        out_path = OUTPUT_DIR / f"{state.lower()}_form_filings.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        print(f"\n[{state}] Done:")
        print(f"  Total MS filings in SERFF: {data['total_in_serff']:,}")
        print(f"  Form/Application filings: {len(filings)}")

        types = Counter(r.get("Filing Type", "?") for r in filings)
        statuses = Counter(r.get("Filing Status", "?") for r in filings)
        print(f"  By type: {dict(types.most_common())}")
        print(f"  By status: {dict(statuses.most_common(5))}")

        print(f"\n  Sample:")
        for r in filings[:8]:
            print(f"    {r.get('Company Name','?')[:35]} | {r.get('Filing Type')} | {r.get('Filing Status')} | {r.get('SERFF Tracking Number')}")

        print(f"\n  Saved: {out_path}")


if __name__ == "__main__":
    main()
