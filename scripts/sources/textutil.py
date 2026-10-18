"""Turn HTML into clean text lines - the last-resort parsing strategy for every source."""
import html as htmllib
import json
import re


def text_lines(page: str) -> list[str]:
    page = re.sub(r"<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", page, flags=re.S | re.I)
    page = re.sub(r"<br\s*/?>|</(p|div|li|tr|h\d|section|article|td|th|span|a)>", "\n", page, flags=re.I)
    page = re.sub(r"<[^>]+>", " ", page)
    page = htmllib.unescape(page)
    return [ln for ln in (re.sub(r"\s+", " ", x).strip() for x in page.splitlines()) if ln]


def all_json_blobs(page: str):
    """Yield every parseable JSON object embedded in <script> tags (Next.js, Nuxt, Apollo caches)."""
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", page, re.S | re.I):
        body = m.group(1).strip()
        if not body or body[0] not in "{[":
            continue
        try:
            yield json.loads(body)
        except json.JSONDecodeError:
            continue


def walk(obj):
    """Yield every dict inside a JSON structure."""
    stack = [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            yield x
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
