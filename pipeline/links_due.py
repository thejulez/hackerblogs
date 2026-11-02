"""Write data/out/urls.json: the listed links launcher/check.ts should request this run. New links and links that
failed last time always; links that worked, when due (about monthly). python pipeline/links_due.py data/out"""

import json
import sys
from pathlib import Path

from rules import due

out = Path(sys.argv[1] if len(sys.argv) > 1 else "data/out")
checked_file = out / "url_check.json"
checked = {r["url"]: r["status"] for r in json.loads(checked_file.read_text())} if checked_file.exists() else {}
urls = [b["url"] for b in json.loads((out / "site" / "blogs.json").read_text())]
todo = [u for u in urls if u not in checked or not 0 < checked[u] < 400 or due(u)]
(out / "urls.json").write_text(json.dumps(todo))
print(f"{len(todo)} of {len(urls)} links to check")
