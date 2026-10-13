"""Check ONE citation against the ORIGINAL PDF file (independent of the database).
Usage:  python scripts/check_citation.py <pdf file name> <page number> "<excerpt text>"
Example: python scripts/check_citation.py hr_leave_policy.pdf 2 "Full-time employees receive 24 days"
"""
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.pdf_parser import normalize

if len(sys.argv) != 4:
    sys.exit(__doc__)
name, page, excerpt = sys.argv[1], int(sys.argv[2]), sys.argv[3]
matches = list((Path(__file__).resolve().parent.parent / "samples").rglob(name))
if not matches:
    sys.exit(f"Could not find {name} under samples/")
doc = pymupdf.open(matches[0])
print(f"File: {matches[0]}  ({doc.page_count} pages)")
if not 1 <= page <= doc.page_count:
    sys.exit(f"RESULT: FAIL - page {page} does not exist (pages start at 1)")
want = normalize(excerpt).lower()
on_page = want in normalize(doc[page - 1].get_text()).lower()
found_on = [i + 1 for i, p in enumerate(doc) if want in normalize(p.get_text()).lower()]
print(f"Excerpt on cited page {page}: {on_page}")
print(f"Pages that contain the excerpt: {found_on or 'none'}")
print("RESULT: PASS - the citation matches the original file" if on_page else "RESULT: FAIL - the excerpt is not on that page")