import os
#!/usr/bin/env python3
"""
For each of the top 10 MD App/Form filings, navigate SERFF to get the filing summary
URL and document list, then update Airtable with a working SERFF URL and doc names.
"""

import json, os, re, subprocess, time, urllib.request, urllib.parse
from pathlib import Path

os.environ["FIRECRAWL_API_KEY"] = "fc-94fa12dd36444846851cfcd972c23194"

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = "apppTwOnYf8tJrRNu"

AT_HEADERS = {"Authorization": f"Bearer {AT_TOKEN}", "Content-Type": "application/json"}


def at_req(method, url, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=AT_HEADERS, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"error": json.loads(e.read())}


def run_fc(args, timeout=90):
    env = os.environ.copy()
    result = subprocess.run(["firecrawl"] + args, capture_output=True, text=True,
                            timeout=timeout + 15, env=env)
    return result.stdout + result.stderr, result.returncode


def stop_session():
    run_fc(["interact", "stop"], timeout=10)
    time.sleep(2)


def get_filing_summary(state, serff_tracking):
    """Navigate SERFF, find filing, return summary URL and document list."""
    stop_session()
    time.sleep(3)

    out, code = run_fc(["scrape", f"https://filingaccess.serff.com/sfa/home/{state}"], timeout=30)
    m = re.search(r'Scrape ID: ([a-f0-9-]+)', out)
    if not m:
        return None, []
    scrape_id = m.group(1)

    prompt = (
        f"Steps:\n"
        f"1. Click Begin Search\n"
        f"2. Click Accept\n"
        f"3. Type '{serff_tracking}' in the SERFF Tracking Number field\n"
        f"4. Click Search\n"
        f"5. Click the result row\n"
        f"6. You are on the filing summary page. Return ONLY:\n"
        f"   SUMMARY_URL: <exact URL from address bar>\n"
        f"   FILING_ID: <the filingId number from the URL if visible>\n"
        f"   Then for each Form document (not rate, not correspondence): FORM_DOC: <filename>\n"
        f"   No other text."
    )

    out, _ = run_fc(["interact", "--scrape-id", scrape_id,
                     "--prompt", prompt, "--timeout", "70"], timeout=90)
    stop_session()

    summary_url = None
    docs = []
    filing_id = None

    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY_URL:"):
            summary_url = line.split(":", 1)[1].strip()
        elif line.startswith("FILING_ID:"):
            filing_id = line.split(":", 1)[1].strip()
        elif line.startswith("FORM_DOC:"):
            docs.append(line[9:].strip())

    # Extract filingId from URL if not explicitly returned
    if summary_url and not filing_id:
        m = re.search(r'filingId=(\d+)', summary_url)
        if m:
            filing_id = m.group(1)

    print(f"  [{serff_tracking}] URL: {summary_url}, docs: {docs}")
    return summary_url, docs, filing_id


def main():
    # Get top 10 records
    resp = at_req("GET", f"https://api.airtable.com/v0/{BASE_ID}/Filings?pageSize=100")
    records = resp.get("records", [])

    priority_order = ["Application Only", "Form", "Form/Rate"]
    sorted_records = sorted(
        records,
        key=lambda r: priority_order.index(r["fields"].get("Filing Type", ""))
                      if r["fields"].get("Filing Type", "") in priority_order else 99
    )
    targets = sorted_records[:10]

    print("Updating Airtable with working SERFF filing summary URLs\n")

    updates = []
    for i, record in enumerate(targets):
        fields = record["fields"]
        state = fields.get("State", "MD")
        serff_num = fields.get("SERFF Tracking #", "")
        carrier = fields.get("Carrier", "")

        print(f"[{i+1}/10] {carrier} — {serff_num}")

        summary_url, docs, filing_id = get_filing_summary(state, serff_num)

        # Build working URL
        if filing_id:
            working_url = f"https://filingaccess.serff.com/sfa/search/filingSummary.xhtml?filingId={filing_id}"
        elif summary_url:
            working_url = summary_url
        else:
            working_url = f"https://filingaccess.serff.com/sfa/home/{state}"

        notes = f"SERFF Tracking: {serff_num}"
        if docs:
            notes += f"\nForm Documents: {', '.join(docs)}"
        notes += "\nNote: Click SERFF URL to open filing. Documents require SERFF session to download."

        updates.append({
            "id": record["id"],
            "fields": {
                "SERFF URL": working_url,
                "Notes": notes
            }
        })

        time.sleep(3)

    # Batch update Airtable
    print(f"\nUpdating {len(updates)} Airtable records...")
    for i in range(0, len(updates), 10):
        batch = updates[i:i+10]
        resp = at_req("PATCH", f"https://api.airtable.com/v0/{BASE_ID}/Filings",
                      {"records": batch})
        if "records" in resp:
            print(f"  Updated {min(i+10, len(updates))}/{len(updates)}")
        else:
            print(f"  Error: {resp}")
        time.sleep(0.3)

    print("\nDone.")


if __name__ == "__main__":
    main()
