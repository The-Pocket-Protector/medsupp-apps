#!/usr/bin/env python3
"""Quick 2-state test of the SERFF scraper flow."""
import sys
sys.path.insert(0, '/home/openclaw/.openclaw/workspace/medsupp-apps/scripts')

import serff_full_scraper as scraper

# Override for test
scraper.SERFF_STATES = ["AL", "OH"]
scraper.TOI_CODES = [
    ("MS08I", "Individual Medicare Supplement - Standard Plans 2010"),
]

scraper.main()
