import os
#!/usr/bin/env python3
"""
Upload application-only SERFF filings to Airtable + generate Excel tracker.
Reads from app_filings_results.json.
"""

import json
import time
import sys
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = "apppTwOnYf8tJrRNu"
TABLE_NAME = "Filings"

HEADERS_AT = {
    "Authorization": f"Bearer {AT_TOKEN}",
    "Content-Type": "application/json"
}

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output")
INPUT_FILE = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff/app_filings_results.json")
EXCEL_FILE = OUTPUT_DIR / "medsupp_applications_by_state.xlsx"
CSV_FILE = OUTPUT_DIR / "medsupp_applications_by_state.csv"


def at_req(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS_AT, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read())}


def get_existing_records():
    """Fetch existing records from Airtable to avoid duplication."""
    url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE_NAME)}?pageSize=100"
    existing = set()
    while url:
        resp = at_req("GET", url)
        for rec in resp.get("records", []):
            fields = rec.get("fields", {})
            key = (fields.get("State", ""), fields.get("SERFF Tracking #", ""), fields.get("Filing Type", ""))
            existing.add(key)
        offset = resp.get("offset")
        if offset:
            url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote(TABLE_NAME)}?pageSize=100&offset={offset}"
        else:
            url = None
    return existing


def upload_records(records, dry_run=False):
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
        time.sleep(0.3)
        if (i // 10) % 5 == 0:
            print(f"  Uploaded {total} records...")

    return total, errors


def make_excel(tracker_rows):
    """Create Excel file with State + Insurance Carrier columns."""
    if HAS_OPENPYXL:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Applications by State"
        ws.append(["State", "Insurance Carrier", "Product Name", "Filing Type", "Filing Status", "SERFF Tracking #"])
        for row in tracker_rows:
            ws.append([
                row.get("state", ""),
                row.get("carrier", ""),
                row.get("product", ""),
                row.get("filing_type", ""),
                row.get("status", ""),
                row.get("serff_num", ""),
            ])
        # Auto-width
        for col in ws.columns:
            max_len = max((len(str(cell.value or "")) for cell in col), default=10)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)
        wb.save(EXCEL_FILE)
        print(f"Excel saved: {EXCEL_FILE}")
    else:
        print("openpyxl not available — saving as CSV instead")

    # Always save CSV as backup
    import csv
    with open(CSV_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["State", "Insurance Carrier", "Product Name", "Filing Type", "Filing Status", "SERFF Tracking #"])
        for row in tracker_rows:
            writer.writerow([
                row.get("state", ""),
                row.get("carrier", ""),
                row.get("product", ""),
                row.get("filing_type", ""),
                row.get("status", ""),
                row.get("serff_num", ""),
            ])
    print(f"CSV saved: {CSV_FILE}")


def main():
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    skip_upload = "--no-upload" in args
    skip_excel = "--no-excel" in args

    if not INPUT_FILE.exists():
        print(f"ERROR: {INPUT_FILE} not found. Run serff_app_scraper.py first.")
        return

    with open(INPUT_FILE) as f:
        data = json.load(f)

    complete = [r for r in data if r.get("status") == "complete"]
    print(f"Processing {len(complete)} states")

    all_records = []
    tracker_rows = []

    for state_result in complete:
        state = state_result["state"]
        app_filings = state_result.get("filings", [])

        for filing in app_filings:
            company = filing.get("Company Name", "")
            naic = filing.get("NAIC Company Code", "")
            product = filing.get("Insurance Product Name", "")
            sub_toi = filing.get("Sub Type Of Insurance", "")
            filing_type = filing.get("Filing Type", "")
            status = filing.get("Filing Status", "")
            serff_num = filing.get("SERFF Tracking Number", "")

            if not company:
                continue

            serff_url = f"https://filingaccess.serff.com/sfa/search/filingSummary.xhtml?filingId={serff_num}" if serff_num else ""

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
            all_records.append(record)
            tracker_rows.append({
                "state": state,
                "carrier": company,
                "product": product,
                "filing_type": filing_type,
                "status": status,
                "serff_num": serff_num,
            })

    # Sort tracker by state then carrier
    tracker_rows.sort(key=lambda r: (r["state"], r["carrier"]))

    print(f"\nTotal application records: {len(all_records)}")

    # Summary by state
    from collections import Counter
    state_counts = Counter(r["state"] for r in tracker_rows)
    print("\nApplications by state:")
    for st in sorted(state_counts):
        print(f"  {st}: {state_counts[st]} carriers")

    if not skip_excel:
        print("\nGenerating tracker file...")
        make_excel(tracker_rows)

    if not skip_upload and not dry_run:
        print("\nUploading to Airtable...")
        total, errors = upload_records(all_records)
        print(f"Done: {total} uploaded, {errors} batch errors")
        print(f"Airtable: https://airtable.com/{BASE_ID}")
    elif dry_run:
        print(f"\n[DRY RUN] Would upload {len(all_records)} records")
    else:
        print("\n[Skipped Airtable upload]")


if __name__ == "__main__":
    main()
