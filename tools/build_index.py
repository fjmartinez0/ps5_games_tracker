"""Assemble index.html (single self-contained page) from tools/dashboard.css + tools/dashboard.js.
   python3 tools/build_index.py            -> index.html (reads data/*.json at runtime)
   python3 tools/build_index.py --preview  -> .run/preview.html with the data embedded (opens anywhere)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
T = ROOT / "tools"
SHELL = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PS5 Games Tracker</title>
<style>
%CSS%
.star.pending{opacity:.55}
code{font-size:13px;background:var(--paper);padding:1px 5px;border-radius:4px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>PS5 Games Tracker</h1>
    <p class="lede">PS5 games released in 2025 and 2026 that scored 70+ with critics, with Canadian prices. Updated nightly. Last updated <time id="updated">…</time>.</p>
  </header>
  <div class="banner" id="banner" hidden></div>
  <nav class="tabs" role="tablist" id="tabs"></nav>
  <main id="panel"><p class="hint">Loading…</p></main>
</div>
%EMBED%<script>
%JS%
</script>
</body>
</html>
"""


def main():
    html = SHELL.replace("%CSS%", (T / "dashboard.css").read_text().strip()).replace("%JS%", (T / "dashboard.js").read_text().strip())
    if "--preview" in sys.argv:
        data = {n: json.loads((ROOT / "data" / f"{n}.json").read_text()) for n in ("games", "stats", "sales", "wishlist", "events", "meta")}
        embed = "<script>window.EMBEDDED_DATA = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";</script>\n"
        out = ROOT / ".run" / "preview.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(html.replace("%EMBED%", embed))
    else:
        out = ROOT / "index.html"
        out.write_text(html.replace("%EMBED%", ""))
    print("wrote", out)


if __name__ == "__main__":
    main()
