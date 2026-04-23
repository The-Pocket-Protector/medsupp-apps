import os
#!/usr/bin/env python3
"""
Create 'Med Supp Paper Apps' Airtable base and upload MD filing data.
"""

import json
import re
import time
import urllib.request
import urllib.error

# Credentials
AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
WORKSPACE_ID = "wsphJA6Fl4xex3R8G"

HEADERS = {
    "Authorization": f"Bearer {AT_TOKEN}",
    "Content-Type": "application/json"
}


def at_request(method: str, url: str, body: dict = None) -> dict:
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        err = json.loads(e.read())
        print(f"HTTP {e.code}: {err}")
        return {"error": err}


def create_base(name: str, workspace_id: str) -> str:
    """Create a new Airtable base and return its ID."""
    resp = at_request("POST", "https://api.airtable.com/v0/meta/bases", {
        "name": name,
        "workspaceId": workspace_id,
        "tables": [{
            "name": "Filings",
            "fields": [
                {"name": "State", "type": "singleLineText"},
                {"name": "Carrier", "type": "singleLineText"},
                {"name": "NAIC Code", "type": "singleLineText"},
                {"name": "Product Name", "type": "singleLineText"},
                {"name": "Plan Type", "type": "singleLineText"},
                {"name": "Filing Type", "type": "singleLineText"},
                {"name": "Status", "type": "singleLineText"},
                {"name": "SERFF Tracking #", "type": "singleLineText"},
                {"name": "SERFF URL", "type": "url"},
                {"name": "Notes", "type": "multilineText"},
            ]
        }]
    })
    if "id" in resp:
        print(f"Created base: {resp['id']} — {resp['name']}")
        return resp["id"]
    print(f"Create base failed: {resp}")
    return None


def get_workspace_id() -> str:
    """Get the workspace ID for TPP."""
    resp = at_request("GET", "https://api.airtable.com/v0/meta/workspaces")
    if "workspaces" in resp:
        for ws in resp["workspaces"]:
            print(f"  Workspace: {ws['id']} — {ws['name']}")
        # Return first one (TPP's workspace)
        return resp["workspaces"][0]["id"]
    print(f"Workspaces response: {resp}")
    return None


def get_table_id(base_id: str) -> str:
    """Get the Filings table ID."""
    resp = at_request("GET", f"https://api.airtable.com/v0/meta/bases/{base_id}/tables")
    for t in resp.get("tables", []):
        if t["name"] == "Filings":
            return t["id"]
    return None


def parse_md_filings() -> list:
    """Parse MD filing data from the scrape results."""
    with open("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff/all_states_results.json") as f:
        data = json.load(f)

    md = next(r for r in data if r["state"] == "MD")
    raw = md.get("raw_output", "")

    # Find the results section
    idx = raw.find("Filing(s)")
    if idx < 0:
        print("No Filing(s) marker found in MD data")
        return []

    results_text = raw[idx:]
    filings = []

    for line in results_text.split("\n"):
        line = line.strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 7:
            carrier, naic, product, sub_toi, filing_type, status, serff_num = parts[:7]
            # Skip header-like lines
            if carrier.lower() in ("company name", "carrier"):
                continue
            # Build SERFF URL from tracking number
            serff_url = f"https://filingaccess.serff.com/sfa/filing/{serff_num}" if serff_num else ""
            filings.append({
                "State": "MD",
                "Carrier": carrier,
                "NAIC Code": naic,
                "Product Name": product,
                "Plan Type": sub_toi,
                "Filing Type": filing_type,
                "Status": status,
                "SERFF Tracking #": serff_num,
                "SERFF URL": serff_url,
            })

    print(f"Parsed {len(filings)} MD filings")
    return filings


def upload_records(base_id: str, table_name: str, records: list):
    """Upload records to Airtable in batches of 10."""
    url = f"https://api.airtable.com/v0/{base_id}/{urllib.parse.quote(table_name)}"
    
    import urllib.parse
    
    total = 0
    batch_size = 10
    for i in range(0, len(records), batch_size):
        batch = records[i:i+batch_size]
        body = {"records": [{"fields": r} for r in batch]}
        resp = at_request("POST", url, body)
        if "records" in resp:
            total += len(resp["records"])
            print(f"  Uploaded {total}/{len(records)}...")
        else:
            print(f"  Batch error: {resp}")
        time.sleep(0.25)  # Rate limit: 5 req/sec

    print(f"Upload complete: {total} records")
    return total


def main():
    print("=== Med Supp Paper Apps — Airtable Setup ===\n")

    ws_id = WORKSPACE_ID
    print(f"Using workspace: {ws_id}\n")

    # 2. Create base
    print("Creating base 'Med Supp Paper Apps'...")
    base_id = create_base("Med Supp Paper Apps", ws_id)
    if not base_id:
        return
    print()

    # 3. Parse MD data
    print("Parsing MD filing data...")
    filings = parse_md_filings()
    if not filings:
        print("No filings to upload")
        return
    print()

    # 4. Upload
    print(f"Uploading {len(filings)} MD filings to Airtable...")
    uploaded = upload_records(base_id, "Filings", filings)
    print()

    # 5. Done
    base_url = f"https://airtable.com/{base_id}"
    print(f"=== DONE ===")
    print(f"Base URL: {base_url}")
    print(f"Records uploaded: {uploaded}")
    print(f"Base ID: {base_id}")


if __name__ == "__main__":
    main()
