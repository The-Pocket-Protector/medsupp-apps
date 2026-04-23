import os
#!/usr/bin/env python3
"""
Upload SERFF v2 scrape results to Airtable.
Handles all states from all_states_results_v2.json.
"""

import json
import time
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = "apppTwOnYf8tJrRNu"
TABLE_NAME = "Filings"

HEADERS = {
    "Authorization": f"Bearer {AT_TOKEN}",
    "Content-Type": "application/json"
}

INPUT_FILE = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff/all_states_results_v2.json")


def at_req(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read())}


def upload_records(records, dry_run=False):
    """Upload records to Airtable in batches of 10."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE_NAME)}"
    total = 0
    errors = 0
    
    for i in range(0, len(records), 10):
        batch = records[i:i+10]
        
        if dry_run:
            total += len(batch)
            continue
        
        resp = at_req("POST", url, {"records": [{"fields": r} for r in batch]})
        
        if "records" in resp:
            total += len(resp["records"])
        else:
            print(f"  Batch error: {resp}")
            errors += 1
        
        time.sleep(0.3)  # Rate limit respect
        
        if (i // 10) % 10 == 0:
            print(f"  Uploaded {total} records...")
    
    return total, errors


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    target_states = [a for a in args if not a.startswith('--')] or None
    
    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found")
        return
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    complete = [r for r in data if r.get("status") == "complete"]
    if target_states:
        complete = [r for r in complete if r["state"] in target_states]
    
    print(f"Processing {len(complete)} states")
    if dry_run:
        print("DRY RUN - not uploading")
    
    # Build all records
    all_records = []
    state_counts = {}
    
    for state_result in complete:
        state = state_result["state"]
        filings = state_result.get("filings", [])
        state_records = []
        
        for filing in filings:
            # Map headers from scrape to Airtable fields
            company = filing.get("Company Name", "")
            naic = filing.get("NAIC Company Code", "")
            product = filing.get("Insurance Product Name", "")
            sub_toi = filing.get("Sub Type Of Insurance", "")
            filing_type = filing.get("Filing Type", "")
            status = filing.get("Filing Status", "")
            serff_num = filing.get("SERFF Tracking Number", "")
            
            if not company:
                continue
            
            serff_url = f"https://filingaccess.serff.com/sfa/filing/{serff_num}" if serff_num else ""
            
            record = {
                "Carrier": company,
                "State": state,
                "NAIC Code": naic,
                "Product Name": product,
                "Plan Type": sub_toi,
                "Filing Type": filing_type,
                "Filing Status": status,
                "SERFF Tracking #": serff_num,
                "SERFF URL": serff_url,
            }
            state_records.append(record)
        
        state_counts[state] = len(state_records)
        all_records.extend(state_records)
    
    print(f"\nTotal records to upload: {len(all_records)}")
    print("By state:", {s: c for s, c in state_counts.items()})
    
    if not all_records:
        print("No records to upload!")
        return
    
    # Upload
    total, errors = upload_records(all_records, dry_run=dry_run)
    print(f"\nDone: {total} uploaded, {errors} batch errors")
    print(f"Airtable: https://airtable.com/{BASE_ID}")


if __name__ == "__main__":
    main()
