#!/usr/bin/env python3
"""
SERFF Med Supp scraper using JavaScript extraction — clean data, no ARIA noise.
"""
import json, os, re, subprocess, time
from pathlib import Path

os.environ["FIRECRAWL_API_KEY"] = "fc-94fa12dd36444846851cfcd972c23194"

OUTPUT_DIR = Path("/home/openclaw/.openclaw/workspace/medsupp-apps/output/serff_v3")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_FILE = OUTPUT_DIR / "all_states.json"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"

SERFF_STATES = [
    "AL","AK","AZ","AR","CO","CT","DE","DC","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME",
    "MD","MA","MI","MN","MS","MO","MT","NE","NV",
    "NH","NJ","NM","NC","ND","OH","OK","OR","PA",
    "RI","SC","SD","TN","TX","UT","VT","VA","WA",
    "WV","WI","WY"
]

def run_fc(args, timeout=60):
    env = os.environ.copy()
    try:
        r = subprocess.run(["firecrawl"]+args, capture_output=True, text=True,
                           timeout=timeout+15, env=env)
        return r.stdout + r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "TIMEOUT", -1

def stop():
    run_fc(["interact","stop"], timeout=10)
    time.sleep(2)

def scrape_state(state):
    stop()
    time.sleep(3)

    out, _ = run_fc(["scrape", f"https://filingaccess.serff.com/sfa/home/{state}"], timeout=30)
    m = re.search(r'Scrape ID: ([a-f0-9-]+)', out)
    if not m:
        return {"state": state, "status": "blocked", "rows": []}
    sid = m.group(1)

    prompt = (
        "Complete all steps:\n"
        "1. Click Begin Search\n"
        "2. Click Accept\n"
        "3. In Insurance Product Name type 'Medicare Supplement', select Contains\n"
        "4. Click Search and wait for results\n"
        "5. Run this JavaScript and return its output verbatim:\n"
        "   var count = document.querySelector('.ui-datatable')?.previousElementSibling?.textContent?.trim() || '';\n"
        "   var rows = Array.from(document.querySelectorAll('.ui-datatable-tablewrapper tbody tr')).map(r => Array.from(r.querySelectorAll('td')).map(td=>td.textContent.trim()).join('|')).join('\\n');\n"
        "   'COUNT:'+count+'\\n'+rows;\n"
        "Return ONLY the JavaScript output string. No other text."
    )

    out, _ = run_fc(["interact","--scrape-id",sid,"--prompt",prompt,"--timeout","70"], timeout=90)
    stop()

    # Parse rows from output
    rows = []
    total_str = ""
    in_data = False
    for line in out.split("\n"):
        line = line.strip()
        if line.startswith("COUNT:"):
            total_str = line[6:].strip()
            in_data = True
            continue
        if in_data and "|" in line:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 6:
                rows.append({
                    "carrier": parts[0],
                    "naic": parts[1],
                    "product": parts[2],
                    "sub_toi": parts[3],
                    "filing_type": parts[4],
                    "status": parts[5],
                    "serff_num": parts[6] if len(parts) > 6 else ""
                })

    # Also try extracting from quoted JSON strings in output (the JS eval result format)
    if not rows:
        matches = re.findall(r'"([^"]*\|[^"]*)"', out)
        for match in matches:
            for line in match.replace('\\n','\n').split('\n'):
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6 and parts[0] and parts[0] not in ('Company Name',):
                    rows.append({
                        "carrier": parts[0],
                        "naic": parts[1] if len(parts)>1 else "",
                        "product": parts[2] if len(parts)>2 else "",
                        "sub_toi": parts[3] if len(parts)>3 else "",
                        "filing_type": parts[4] if len(parts)>4 else "",
                        "status": parts[5] if len(parts)>5 else "",
                        "serff_num": parts[6] if len(parts)>6 else ""
                    })
            if rows:
                break

    # Deduplicate
    seen = set()
    unique_rows = []
    for r in rows:
        key = r.get("serff_num") or f"{r['carrier']}|{r['product']}"
        if key not in seen:
            seen.add(key)
            unique_rows.append(r)

    print(f"[{state}] {len(unique_rows)} rows extracted. Total str: '{total_str[:50]}'")
    return {
        "state": state,
        "status": "complete",
        "total_str": total_str,
        "row_count": len(unique_rows),
        "rows": unique_rows
    }

def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {}

def save_progress(p):
    with open(PROGRESS_FILE,'w') as f:
        json.dump(p, f, indent=2)

def main():
    progress = load_progress()
    all_results = []
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            all_results = json.load(f)

    done = set(progress.get("completed", []))
    remaining = [s for s in SERFF_STATES if s not in done]
    print(f"Remaining: {len(remaining)} states")

    for i, state in enumerate(remaining):
        print(f"\n[{i+1}/{len(remaining)}] {state}")
        result = scrape_state(state)
        all_results.append(result)
        with open(RESULTS_FILE,'w') as f:
            json.dump(all_results, f, indent=2)
        if result["status"] == "complete":
            done.add(state)
        progress["completed"] = list(done)
        save_progress(progress)
        if i < len(remaining)-1:
            time.sleep(5)

    # Summary
    complete = [r for r in all_results if r["status"]=="complete"]
    total_rows = sum(r.get("row_count",0) for r in complete)
    print(f"\nDONE: {len(complete)} states, {total_rows} total filing rows")
    for r in sorted(complete, key=lambda x: x.get("row_count",0), reverse=True)[:10]:
        print(f"  {r['state']}: {r.get('row_count',0)} rows")

if __name__ == "__main__":
    main()
