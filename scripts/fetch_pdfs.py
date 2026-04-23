import os
#!/usr/bin/env python3
"""
For each of the top 10 MD App/Form filings:
1. Navigate SERFF to the filing detail page
2. Extract PDF download URL(s)
3. Download the PDF
4. Upload to Airtable as an attachment
"""

import json, os, re, subprocess, time, urllib.request, urllib.parse
from pathlib import Path

os.environ["FIRECRAWL_API_KEY"] = "fc-94fa12dd36444846851cfcd972c23194"

AT_TOKEN = os.environ["AIRTABLE_TOKEN"]
BASE_ID = "apppTwOnYf8tJrRNu"
PDF_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/pdfs")
PDF_DIR.mkdir(parents=True, exist_ok=True)

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
    result = subprocess.run(
        ["firecrawl"] + args,
        capture_output=True, text=True, timeout=timeout + 15,
        env={**os.environ}
    )
    return result.stdout + result.stderr, result.returncode


def stop_session():
    run_fc(["interact", "stop"], timeout=10)
    time.sleep(2)


def get_filing_pdfs(state: str, serff_tracking: str) -> list:
    """
    Navigate SERFF to a specific filing by tracking number and return PDF URLs.
    Returns list of {filename, url} dicts.
    """
    stop_session()
    time.sleep(3)

    # Scrape the state home page
    out, code = run_fc(["scrape", f"https://filingaccess.serff.com/sfa/home/{state}"], timeout=30)
    m = re.search(r'Scrape ID: ([a-f0-9-]+)', out)
    if not m:
        print(f"  [{serff_tracking}] Could not get scrape ID")
        return []
    scrape_id = m.group(1)

    # Navigate: Begin Search → Accept → search by tracking number → open filing → get PDFs
    prompt = (
        f"Do all steps in sequence:\n"
        f"1. Click 'Begin Search'\n"
        f"2. Click 'Accept'\n"
        f"3. In the SERFF Tracking Number field, type '{serff_tracking}'\n"
        f"4. Click Search\n"
        f"5. Wait for results, then click the result row to open the filing detail page\n"
        f"6. On the filing detail page, find all document/attachment links (PDFs)\n"
        f"7. Return ONLY this — no page structure:\n"
        f"   FILING_URL: <the full URL of the filing detail page>\n"
        f"   PDF: <filename> | <full URL of each PDF document>\n"
        f"   (one PDF line per document found)\n"
        f"   If no PDFs found, return: NO_PDFS"
    )

    out, _ = run_fc([
        "interact", "--scrape-id", scrape_id,
        "--prompt", prompt,
        "--timeout", "75"
    ], timeout=95)

    stop_session()
    print(f"  [{serff_tracking}] Interact output:\n{out[-800:]}")

    pdfs = []
    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("PDF:") and "|" in line:
            parts = line[4:].split("|", 1)
            if len(parts) == 2:
                filename = parts[0].strip()
                url = parts[1].strip()
                if url.startswith("http"):
                    pdfs.append({"filename": filename, "url": url})
        elif line.startswith("FILING_URL:"):
            filing_url = line.split(":", 1)[1].strip()
            print(f"  [{serff_tracking}] Filing URL: {filing_url}")

    return pdfs


def download_pdf(url: str, filename: str) -> str | None:
    """Download a PDF and return local path."""
    # Clean filename
    safe_name = re.sub(r'[^\w\-_.]', '_', filename)
    if not safe_name.endswith('.pdf'):
        safe_name += '.pdf'
    local_path = PDF_DIR / safe_name

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
        with open(local_path, 'wb') as f:
            f.write(content)
        print(f"  Downloaded: {safe_name} ({len(content):,} bytes)")
        return str(local_path)
    except Exception as e:
        print(f"  Download failed for {url}: {e}")
        return None


def upload_attachment_to_airtable(record_id: str, pdf_url: str, filename: str):
    """Update Airtable record with PDF URL as attachment."""
    body = {
        "records": [{
            "id": record_id,
            "fields": {
                "Attachments": [{"url": pdf_url, "filename": filename}]
            }
        }]
    }
    resp = at_req("PATCH", f"https://api.airtable.com/v0/{BASE_ID}/Filings", body)
    if "records" in resp:
        print(f"  Airtable updated with attachment: {filename}")
        return True
    print(f"  Airtable attachment error: {resp}")
    return False


def main():
    print("Fetching PDFs for top 10 MD Med Supp filings\n")

    # Get top 10 records prioritizing Application Only, then Form, then Form/Rate
    resp = at_req("GET", f"https://api.airtable.com/v0/{BASE_ID}/Filings?pageSize=100")
    records = resp.get("records", [])

    priority_order = ["Application Only", "Form", "Form/Rate"]
    sorted_records = sorted(
        records,
        key=lambda r: priority_order.index(r["fields"].get("Filing Type", "")) 
                      if r["fields"].get("Filing Type", "") in priority_order else 99
    )
    targets = sorted_records[:10]

    print(f"Target records:")
    for r in targets:
        f = r["fields"]
        print(f"  {f.get('Carrier','')} | {f.get('SERFF Tracking #','')} | {f.get('Filing Type','')}")

    print()
    results = []

    for i, record in enumerate(targets):
        fields = record["fields"]
        state = fields.get("State", "MD")
        serff_num = fields.get("SERFF Tracking #", "")
        carrier = fields.get("Carrier", "")
        filing_type = fields.get("Filing Type", "")

        print(f"\n[{i+1}/10] {carrier} — {serff_num} ({filing_type})")

        pdfs = get_filing_pdfs(state, serff_num)

        if not pdfs:
            print(f"  No PDFs found for {serff_num}")
            # Update notes to reflect this
            at_req("PATCH", f"https://api.airtable.com/v0/{BASE_ID}/Filings", {
                "records": [{"id": record["id"], "fields": {
                    "Notes": f"SERFF Tracking: {serff_num} — No PDFs extracted automatically. Manual retrieval needed."
                }}]
            })
            results.append({"serff": serff_num, "status": "no_pdfs"})
            continue

        # Use the first PDF URL directly in Airtable (Airtable can fetch from URL)
        pdf = pdfs[0]
        success = upload_attachment_to_airtable(record["id"], pdf["url"], pdf["filename"])

        results.append({
            "serff": serff_num,
            "status": "uploaded" if success else "failed",
            "pdf_url": pdf["url"],
            "filename": pdf["filename"]
        })

        time.sleep(4)  # Rate limit between states

    print(f"\n{'='*50}")
    print("DONE")
    uploaded = [r for r in results if r["status"] == "uploaded"]
    no_pdfs = [r for r in results if r["status"] == "no_pdfs"]
    print(f"  Uploaded: {len(uploaded)}")
    print(f"  No PDFs:  {len(no_pdfs)}")
    for r in uploaded:
        print(f"    {r['serff']}: {r['filename']}")


if __name__ == "__main__":
    main()
