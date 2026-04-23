import os
#!/usr/bin/env python3
"""Set up Med Supp Paper Apps Airtable table and upload MD filings."""

import json, time, urllib.request, urllib.error, urllib.parse

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = "apppTwOnYf8tJrRNu"
TABLE_ID = "tblDkIpJlS0NocV7c"

HEADERS = {
    "Authorization": f"Bearer {AT_TOKEN}",
    "Content-Type": "application/json"
}

def at_req(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read())}

# Step 1: Rename table and add proper fields
print("Renaming table to 'Filings'...")
resp = at_req("PATCH", f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}",
    {"name": "Filings"})
print("  →", "ok" if "error" not in resp else resp["error"])

# Step 2: Get current fields to know what exists
schema = at_req("GET", f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables")
table = next(t for t in schema["tables"] if t["id"] == TABLE_ID)
existing_fields = {f["name"]: f["id"] for f in table["fields"]}
print(f"Existing fields: {list(existing_fields.keys())}")

# Step 3: Rename "Name" → "Carrier" and add needed fields
print("\nRenaming 'Name' field to 'Carrier'...")
resp = at_req("PATCH",
    f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields/{existing_fields['Name']}",
    {"name": "Carrier"})
print("  →", "ok" if "error" not in resp else resp["error"])

# Fields to add
new_fields = [
    {"name": "State", "type": "singleLineText"},
    {"name": "NAIC Code", "type": "singleLineText"},
    {"name": "Product Name", "type": "singleLineText"},
    {"name": "Plan Type", "type": "singleLineText"},
    {"name": "Filing Type", "type": "singleLineText"},
    {"name": "Filing Status", "type": "singleLineText"},
    {"name": "SERFF Tracking #", "type": "singleLineText"},
    {"name": "SERFF URL", "type": "url"},
]

print("\nAdding fields...")
field_map = {"Carrier": existing_fields["Name"]}
for field in new_fields:
    if field["name"] in existing_fields:
        print(f"  {field['name']}: already exists")
        field_map[field["name"]] = existing_fields[field["name"]]
        continue
    resp = at_req("POST",
        f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables/{TABLE_ID}/fields",
        field)
    if "id" in resp:
        print(f"  {field['name']}: created ({resp['id']})")
        field_map[field["name"]] = resp["id"]
    else:
        print(f"  {field['name']}: ERROR {resp}")
    time.sleep(0.2)

# Step 4: Parse MD filings
print("\nParsing MD filing data...")
with open("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff/all_states_results.json") as f:
    data = json.load(f)

md = next(r for r in data if r["state"] == "MD")
raw = md.get("raw_output", "")
idx = raw.find("Filing(s)")
results_text = raw[idx:] if idx >= 0 else raw

records = []
for line in results_text.split("\n"):
    line = line.strip()
    if "|" not in line:
        continue
    parts = [p.strip() for p in line.split("|")]
    if len(parts) >= 7:
        carrier, naic, product, sub_toi, filing_type, status, serff_num = parts[:7]
        if not carrier or carrier.lower() in ("company name", "carrier"):
            continue
        serff_url = f"https://filingaccess.serff.com/sfa/filing/{serff_num}" if serff_num else ""
        records.append({
            "Carrier": carrier,
            "State": "MD",
            "NAIC Code": naic,
            "Product Name": product,
            "Plan Type": sub_toi,
            "Filing Type": filing_type,
            "Filing Status": status,
            "SERFF Tracking #": serff_num,
            "SERFF URL": serff_url,
        })

print(f"Parsed {len(records)} filings")

# Step 5: Upload in batches of 10
print("\nUploading to Airtable...")
url = f"https://api.airtable.com/v0/{BASE_ID}/{urllib.parse.quote('Filings')}"
total = 0
for i in range(0, len(records), 10):
    batch = records[i:i+10]
    resp = at_req("POST", url, {"records": [{"fields": r} for r in batch]})
    if "records" in resp:
        total += len(resp["records"])
        print(f"  {total}/{len(records)} uploaded")
    else:
        print(f"  Batch error: {resp}")
    time.sleep(0.3)

print(f"\nDone. {total} records in Airtable.")
print(f"Base URL: https://airtable.com/{BASE_ID}")
