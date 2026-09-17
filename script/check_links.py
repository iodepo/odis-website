#!/usr/bin/env python3
"""Verify every internal link and asset reference in _site resolves.

Replaces html-proofer, which in 5.2.2 reports "0 internal links" and exits 0
even on a file containing a deliberately broken link. Redirects are the whole
point of this migration, so the check needs to actually work.
"""

import os
import re
import sys
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

SITE = sys.argv[1] if len(sys.argv) > 1 else "_site"
REFS = {"a": "href", "link": "href", "img": "src", "script": "src", "iframe": "src"}


class Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        attr = REFS.get(tag)
        if not attr:
            return
        for k, v in attrs:
            if k == attr and v:
                self.found.append((v, self.getpos()[0]))


def resolves(target, from_file):
    """True if a site-internal target exists on disk."""
    path = unquote(urlparse(target).path)
    if not path:
        return True  # pure fragment, e.g. "#main"

    if path.startswith("/"):
        full = os.path.join(SITE, path.lstrip("/"))
    else:
        full = os.path.join(os.path.dirname(from_file), path)

    full = os.path.normpath(full)
    if os.path.isfile(full):
        return True
    # Directory-style URL: /news/ -> _site/news/index.html
    return os.path.isfile(os.path.join(full, "index.html"))


def main():
    broken, checked, pages = [], 0, 0

    for root, _, files in os.walk(SITE):
        for name in files:
            if not name.endswith(".html"):
                continue
            pages += 1
            fp = os.path.join(root, name)
            with open(fp, encoding="utf-8", errors="replace") as fh:
                parser = Refs()
                parser.feed(fh.read())

            for target, line in parser.found:
                # Skip anything not resolvable on disk.
                if re.match(r"^(https?:|mailto:|tel:|data:|//|#)", target):
                    continue
                checked += 1
                if not resolves(target, fp):
                    broken.append((os.path.relpath(fp, SITE), line, target))

    print(f"Checked {checked} internal references across {pages} HTML files.")

    if broken:
        print(f"\n{len(broken)} broken:\n")
        for f, line, target in sorted(broken):
            print(f"  {f}:{line}  ->  {target}")
        return 1

    print("All internal references resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
