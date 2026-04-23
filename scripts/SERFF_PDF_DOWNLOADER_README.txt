SERFF PDF DOWNLOADER — Quick Start
====================================

WHAT THIS DOES
--------------
Downloads all approved Medicare Supplement Form filing ZIPs from SERFF.
Each ZIP contains the actual PDF application forms for that carrier/state.

Total filings to grab: ~14,000 (across 35+ states)
Estimated full run time: ~15-20 hours (runs in background, resume-safe)

PRE-REQS (run once on your laptop)
------------------------------------
1. Install Python 3.8+ (https://python.org)
2. Run these commands in Terminal:

   pip install playwright
   playwright install chromium

3. Copy the files you need to your laptop:
   - serff_pdf_downloader.py  (this script)
   - ../output/serff/         (all the *_form_filings.json files — ~35 files)
   
   OR clone/sync the whole medsupp-apps folder.

RUNNING IT
----------
Open Terminal in the folder where serff_pdf_downloader.py lives, then:

# TEST FIRST — just download Kentucky (5 filings):
python serff_pdf_downloader.py KY --limit 5

# Check if it worked — you should see ZIPs in ../output/pdfs/KY/

# One state (all approved filings):
python serff_pdf_downloader.py KY

# Multiple states:
python serff_pdf_downloader.py KY IL IN TX

# All states (long run — ~15-20 hours):
python serff_pdf_downloader.py

A Chrome window will open and you'll watch it work.
Don't close it — but you can minimize it.

RESUME AFTER STOPPING
----------------------
Just re-run the same command. It skips anything already downloaded.
Progress is saved every 10 filings to ../output/pdfs/download_log.json.

OUTPUT
------
../output/pdfs/
  KY/
    AETN-132199103.zip    <- unzip this to get the PDFs
    ACEH-133226177.zip
  IL/
    ...
  download_log.json       <- progress tracker

WHERE ARE THE PDFs INSIDE THE ZIPs?
-------------------------------------
Each ZIP contains 1+ PDFs. To unzip all at once on Mac:
   cd ../output/pdfs/KY
   for f in *.zip; do unzip -o "$f" -d "${f%.zip}"; done

On Windows: just double-click any ZIP.

QUESTIONS?
----------
Ping @JoeTwo in Slack with any errors.
