"""Check internal and external links in docs/ and README.md (R80)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = ROOT / "docs"

LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
URL_RE = re.compile(r"https?://[^\s)\]>\"]+")


def check_links() -> int:
    internal_broken: list[tuple[str, str]] = []
    external_links: set[str] = set()

    md_files = [*list(DOCS_DIR.rglob("*.md")), ROOT / "README.md", ROOT / "SECURITY.md"]

    for md_file in md_files:
        if not md_file.is_file():
            continue
        content = md_file.read_text(encoding="utf-8")
        for u in URL_RE.findall(content):
            external_links.add(u.rstrip(".,;"))
        for match in LINK_RE.finditer(content):
            target = match.group(2).strip().split()[0]
            if target.startswith(("http://", "https://")):
                external_links.add(target)
                continue
            if target.startswith(("mailto:", "#")):
                continue
            # Handle anchor
            path_part = target.split("#")[0]
            if not path_part:
                continue
            # In markdown docs, links might be relative to doc or relative to docs root
            resolved = (md_file.parent / path_part).resolve()
            not_in_root = not (ROOT / path_part).resolve().exists()
            not_in_docs = not (DOCS_DIR / path_part).resolve().exists()
            if not resolved.exists() and not_in_root and not_in_docs:
                internal_broken.append((str(md_file.relative_to(ROOT)), target))

    print(f"Scanned {len(md_files)} markdown files.")
    print(f"Internal broken links: {len(internal_broken)}")
    for f, t in internal_broken:
        print(f"  BROKEN: {f} -> {t}")

    print(f"\nChecking {len(external_links)} unique external links (best-effort)...")
    external_failures: list[tuple[str, str]] = []
    headers = {"User-Agent": "Mozilla/5.0"}
    with httpx.Client(timeout=8.0, follow_redirects=True, headers=headers) as client:
        for url in sorted(external_links):
            try:
                res = client.head(url)
                if res.status_code in (405, 403, 404):  # Some servers disallow HEAD
                    res = client.get(url)
                if res.status_code >= 400:
                    external_failures.append((url, f"status {res.status_code}"))
                    print(f"  WARN: {url} -> HTTP {res.status_code}")
                else:
                    print(f"  OK: {url} (HTTP {res.status_code})")
            except Exception as e:
                external_failures.append((url, str(e)))
                print(f"  WARN: {url} -> {type(e).__name__}: {e}")

    summary_msg = (
        f"\nSummary: {len(internal_broken)} broken internal links, "
        f"{len(external_failures)} external warnings."
    )
    print(summary_msg)
    if internal_broken:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(check_links())
