#!/usr/bin/env python3
"""Convert the WordPress WXR export into Jekyll pages, posts and assets.

Re-runnable: rewrites _pages/, _posts/ and assets from the export every time.

Scope decisions (see odis-migration-brief.md):
  * Live site + Screaming Frog crawl are ground truth; the export's template
    parts and nav are stale and are NOT used here.
  * Only `publish` items migrate. `/who/` (private) and the Privacy Policy
    (draft) appear nowhere in the crawl, so they are not part of the live
    site and are not migrated.
  * Post URLs keep the WordPress /YYYY/MM/DD/slug/ form via _config.yml.
"""

import html
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Migration source material lives OUTSIDE this repo, so the raw WordPress
# export (which contains staff email addresses) is never committed or pushed.
# Default layout:
#     odis_migration/
#       provenance/     <- exports, crawl, media dump
#       odis-website/   <- this repo
# Override with ODIS_PROVENANCE=/path/to/provenance for a different layout.
PROVENANCE = os.environ.get(
    "ODIS_PROVENANCE", os.path.join(os.path.dirname(ROOT), "provenance"))

EXPORT = os.path.join(PROVENANCE, "oceandatainformationsystem.WordPress.2026-09-17.xml")
MEDIA_SRC = os.path.join(PROVENANCE, "downloaded media")
IMG_DIR = os.path.join(ROOT, "assets", "img")
DOC_DIR = os.path.join(ROOT, "assets", "docs")

NS = {
    "dc": "http://purl.org/dc/elements/1.1/",
    "wp": "http://wordpress.org/export/1.2/",
    "content": "http://purl.org/rss/1.0/modules/content/",
    "excerpt": "http://wordpress.org/export/1.2/excerpt/",
}

# Pages that exist on the live site, mapped to their permalink.
# Anything not listed here is not migrated.
PAGES = {
    "https://odis.org/": "/",
    "https://odis.org/overview/": "/overview/",
    "https://odis.org/overview/governance/": "/overview/governance/",
    "https://odis.org/outreach-materials-odis/": "/outreach-materials-odis/",
    "https://odis.org/contact-information/": "/contact-information/",
}
# /news/ is a generated listing (_pages/news.html), not migrated content.
SKIP_TITLES = {"News"}

# Old URLs that must not 404. jekyll-redirect-from emits the stubs.
REDIRECTS = {
    "/outreach-materials-odis/": ["/home/outreach-materials-odis/"],
    "/news/": [
        "/author/devodisadmin/",
        "/author/sofie/",
        "/author/stephenodis/",
        "/category/uncategorized/",
    ],
}

# Images hosted on oceaninfohub.org. OIH was reshaped into ODIS, so that
# domain is a decommissioning risk; mirror them locally rather than hotlink.
MIRROR = [
    "https://oceaninfohub.org/wp-content/uploads/2024/06/Picture-2-1024x424.jpg",
    "https://oceaninfohub.org/wp-content/uploads/2024/06/Picture-4-1024x474.png",
]

# WordPress shipped these images with empty alt text, which is an
# accessibility failure for content images. Descriptions written from the
# images themselves and the surrounding post copy.
ALT_TEXT = {
    "Adam-Leadbetter-headshot.jpeg": "Adam Leadbetter",
    "ETel_pic.jpeg": "Elena Tel",
    "Plastic-surveys-with-UP-bags-7-scaled-1-1024x768.jpeg":
        "Two people walking along a wide sandy beach, one carrying a large "
        "blue Universal Plastic collection bag",
    "Picture-2-1024x424.jpg":
        "Screenshot of an online ODIS meeting, showing twelve participants "
        "in a video call grid",
    "Picture-4-1024x474.png":
        "Screenshot of an online ODIS meeting, showing sixteen participants "
        "in a video call grid",
}

# The homepage's intro, floated video and call-to-action buttons live in a
# WordPress *template part*, not in the page's own content, so they are absent
# from <content:encoded> in the export. Reproduced here from the live site
# (verified against odis.org 2026-09-17). The blockquote that follows does come
# from the export and is appended by the normal conversion path.
HOMEPAGE_INTRO = """<p class="home-lede">The Ocean Data and Information System (ODIS) is a digital ecosystem in which a global community of organisations \u2013 large and small \u2013 share and exchange ocean data and information.</p>

<aside class="home-aside">
  <div class="video-embed">
    <iframe src="https://www.youtube-nocookie.com/embed/0f5I1o1ztk0"
            title="ODIS video, English version" loading="lazy"
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowfullscreen></iframe>
  </div>
  <p class="cta"><a href="https://catalogue.odis.org/">Browse the ODIS Catalogue</a></p>
  <p class="cta"><a href="https://search.odis.org/">Search ODIS (beta-version)</a></p>
</aside>
"""

media_map = {}
unresolved = set()


def mirror_external(url):
    """Download a third-party image into assets/img and return its local path."""
    name = os.path.basename(urlparse(url).path)
    dest = os.path.join(IMG_DIR, name)
    if not os.path.isfile(dest):
        os.makedirs(IMG_DIR, exist_ok=True)
        if os.system(f'curl -sSLf -o "{dest}" "{url}"') != 0:
            unresolved.add(url)
            return url
    return f"/assets/img/{name}"


def apply_alt(body):
    """Fill in alt text for images WordPress left with alt=""."""
    def repl(m):
        tag = m.group(0)
        src = re.search(r'src="([^"]+)"', tag)
        if not src:
            return tag
        alt = ALT_TEXT.get(os.path.basename(urlparse(src.group(1)).path))
        return tag.replace('alt=""', f'alt="{html.escape(alt)}"') if alt else tag

    return re.sub(r'<img[^>]*alt=""[^>]*>', repl, body)


def find_media(filename):
    """Locate a referenced upload in the manually-downloaded media folder.

    Handles two quirks: browser duplicate-download suffixes ("foo (1).png")
    and WordPress size variants ("foo-1024x768.png" -> "foo.png").
    """
    candidates = [filename]

    stem, ext = os.path.splitext(filename)
    # Strip a WordPress size suffix ("-1024x768"), then also try the "-scaled"
    # original WordPress keeps for very large uploads.
    base = re.sub(r"-\d+x\d+$", "", stem)
    if base != stem:
        candidates += [base + ext, base + "-scaled" + ext]
    # Browser duplicate-download naming.
    candidates += [f"{c} (1){e}" for c, e in
                   (os.path.splitext(x) for x in list(candidates))]

    for c in candidates:
        p = os.path.join(MEDIA_SRC, c)
        if os.path.isfile(p):
            return p
    return None


def stage_media(url):
    """Copy a referenced upload into assets/ and return its new site path."""
    if url in media_map:
        return media_map[url]

    filename = os.path.basename(urlparse(url).path)
    src = find_media(filename)
    if not src:
        unresolved.add(filename)
        media_map[url] = url  # leave the absolute URL; flagged in the report
        return url

    is_doc = filename.lower().endswith(".pdf")
    dest_dir = DOC_DIR if is_doc else IMG_DIR
    os.makedirs(dest_dir, exist_ok=True)

    # If the reference was to a WordPress size variant, generate just that
    # size. Shipping the full-resolution original as a thumbnail would mean
    # an 800KB download to render a 212x300 image.
    size = re.search(r"-(\d+)x(\d+)\.[A-Za-z0-9]+$", filename)
    if size and not is_doc and os.path.basename(src) != filename:
        w, h = int(size.group(1)), int(size.group(2))
        thumb = os.path.join(dest_dir, filename)
        if shutil.which("sips"):
            os.system(f'sips -z {h} {w} "{src}" --out "{thumb}" >/dev/null 2>&1')
        if os.path.isfile(thumb):
            media_map[url] = f"/assets/img/{filename}"
            return media_map[url]

    # Otherwise copy the file itself, normalising any browser
    # duplicate-download suffix out of the committed name.
    clean = re.sub(r" \(\d+\)(\.[A-Za-z0-9]+)$", r"\1", os.path.basename(src))
    shutil.copy2(src, os.path.join(dest_dir, clean))

    new = f"/assets/{'docs' if is_doc else 'img'}/{clean}"
    media_map[url] = new
    return new


# --- Content cleaning -------------------------------------------------------

YT_ID = re.compile(r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/))([\w-]{11})")


def video_embed(vid, title="YouTube video", float_right=False):
    src = f"https://www.youtube-nocookie.com/embed/{vid}"
    cls = "video-embed video-embed--float-right" if float_right else "video-embed"
    inner = (
        f'<iframe src="{src}" title="{html.escape(title)}" loading="lazy" '
        f'allow="accelerometer; clipboard-write; encrypted-media; gyroscope; '
        f'picture-in-picture; web-share" allowfullscreen></iframe>'
    )
    if float_right:
        return f'<div class="{cls}"><div class="video-embed__ratio">{inner}</div></div>'
    return f'<div class="{cls}">{inner}</div>'


def clean(body):
    """Turn Gutenberg block markup into plain semantic HTML."""

    # 1. Embed blocks: a bare YouTube URL inside a <figure>. Do this before
    #    stripping block comments, while the block boundary is still visible.
    def embed_repl(m):
        vid = YT_ID.search(m.group(0))
        return video_embed(vid.group(1)) if vid else ""

    body = re.sub(r"<!-- wp:embed .*?<!-- /wp:embed -->", embed_repl, body, flags=re.S)

    # 2. Raw-HTML blocks: the homepage floats a YouTube iframe with inline CSS.
    #    Rebuild as a class-driven float that collapses on mobile.
    def html_repl(m):
        chunk = m.group(0)
        vid = YT_ID.search(chunk)
        if not vid:
            return re.sub(r"<!-- /?wp:html -->", "", chunk)
        t = re.search(r'title="([^"]*)"', chunk)
        floated = "float" in chunk and "right" in chunk
        return video_embed(vid.group(1), t.group(1) if t else "YouTube video", floated)

    body = re.sub(r"<!-- wp:html -->.*?<!-- /wp:html -->", html_repl, body, flags=re.S)

    # 3. File blocks: drop the <object> PDF preview (blocked in most browsers
    #    now) and keep an honest labelled download link.
    def file_repl(m):
        chunk = m.group(0)
        href = re.search(r'href="([^"]+\.pdf)"', chunk, re.I)
        label = re.search(r'<a href="[^"]+\.pdf">([^<]*)</a>', chunk, re.I)
        if not href:
            return ""
        text = (label.group(1).strip() if label else "Download PDF")
        return (f'<p class="file-link"><a href="{stage_media(href.group(1))}">'
                f'{html.escape(text)} <span>(PDF)</span></a></p>')

    body = re.sub(r"<!-- wp:file .*?<!-- /wp:file -->", file_repl, body, flags=re.S)

    # 4. All remaining block delimiters.
    body = re.sub(r"<!-- /?wp:[^>]*?-->", "", body)

    # 5. Rewrite upload URLs to local assets.
    body = re.sub(r"https://odis\.org/wp-content/uploads/[^\"'\s)<]+",
                  lambda m: stage_media(m.group(0)), body)

    # 5a. Mirror third-party images that the site hotlinks.
    for ext in MIRROR:
        body = body.replace(ext, mirror_external(ext))

    # 5b. Internal absolute links -> root-relative, so the site is not bound to
    #     the domain and the link checker can resolve them.
    body = re.sub(r'(?:https?:)?//(?:www\.)?odis\.org(/[^"\'\s)<]*)?',
                  lambda m: m.group(1) or "/", body)

    # 6. Drop WordPress/Superb presentational classes, keep structural ones.
    keep = {"wp-block-columns", "wp-block-column",
            "wp-block-buttons", "wp-block-button", "video-embed",
            "video-embed--float-right", "video-embed__ratio", "file-link"}

    def class_repl(m):
        kept = [c for c in m.group(1).split() if c in keep]
        return f' class="{" ".join(kept)}"' if kept else ""

    body = re.sub(r'\s+class="([^"]*)"', class_repl, body)

    # 7. Strip inline styles and leftover WordPress plumbing attributes.
    body = re.sub(r'\s+style="[^"]*"', "", body)
    body = re.sub(r'\s+(data-id|decoding|srcset|sizes)="[^"]*"', "", body)

    # 8. Rename Gutenberg column classes onto our own grid.
    body = body.replace('class="wp-block-columns"', 'class="columns"')
    body = body.replace('class="wp-block-column"', 'class="column"')

    # 9. Lightbox: exactly one image on the site links to its own media file.
    body = re.sub(
        r'<a href="(/assets/img/[^"]+\.(?:png|jpe?g))"><img',
        r'<a href="\1" data-lightbox><img', body, flags=re.I)

    # 10. Alt text for images WordPress left empty.
    body = apply_alt(body)

    # 11. Tidy whitespace.
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = re.sub(r"[ \t]+\n", "\n", body)
    return body.strip()


# --- Emit -------------------------------------------------------------------

def yaml_quote(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def front_matter(fields):
    out = ["---"]
    for k, v in fields.items():
        if isinstance(v, list):
            out.append(f"{k}:")
            out += [f"  - {item}" for item in v]
        else:
            out.append(f"{k}: {v}")
    out.append("---")
    return "\n".join(out) + "\n\n"


# Brand assets. Header mark and favicon source are different files: the live
# site uses the combined IOC-UNESCO mark in the header and the ODIS logo as
# its favicon. Verified against odis.org 2026-09-17.
HEADER_LOGO = "combined_unesco_ioc_blue_eng.png"
FAVICON_SRC = "cropped-ODIS_FINALlogo_05.06.2024_RGB_RGB_Logo_-full-colour.png"
FAVICONS = [("favicon-32.png", 32), ("favicon-192.png", 192),
            ("apple-touch-icon.png", 180)]


def stage_brand_assets():
    """Copy the header logo and generate favicons from the ODIS logo."""
    os.makedirs(IMG_DIR, exist_ok=True)

    src = find_media(HEADER_LOGO)
    if src:
        shutil.copy2(src, os.path.join(IMG_DIR, HEADER_LOGO))
    else:
        unresolved.add(HEADER_LOGO)

    ico = find_media(FAVICON_SRC)
    if not ico:
        unresolved.add(FAVICON_SRC)
        return
    for name, size in FAVICONS:
        dest = os.path.join(IMG_DIR, name)
        if shutil.which("sips"):
            os.system(f'sips -Z {size} "{ico}" --out "{dest}" >/dev/null 2>&1')
        if not os.path.isfile(dest):
            unresolved.add(name)


def main():
    if not os.path.isdir(PROVENANCE):
        sys.exit(
            f"Provenance directory not found: {PROVENANCE}\n"
            "It is deliberately outside this repo. Set ODIS_PROVENANCE if it "
            "lives elsewhere.")
    if not os.path.isfile(EXPORT):
        sys.exit(f"WordPress export not found: {EXPORT}")

    stage_brand_assets()

    tree = ET.parse(EXPORT)
    channel = tree.getroot().find("channel")

    # login -> display name, for post bylines (the live site shows these).
    # Only display names are used; the export's author_email fields are
    # personal data and are never written into the repo.
    authors = {}
    for a in channel.findall("wp:author", NS):
        login = a.findtext("wp:author_login", default="", namespaces=NS)
        name = a.findtext("wp:author_display_name", default="", namespaces=NS)
        if login:
            authors[login] = name or login

    pages_dir = os.path.join(ROOT, "_pages")
    posts_dir = os.path.join(ROOT, "_posts")
    os.makedirs(pages_dir, exist_ok=True)
    os.makedirs(posts_dir, exist_ok=True)

    # The migration is complete and its output is now hand-edited, so by
    # default this script will not clobber existing files. Pass --force to
    # regenerate from the export (e.g. after a fresh export), accepting that
    # any edits made since are lost.
    force = "--force" in sys.argv
    if force:
        for f in os.listdir(posts_dir):
            if f.endswith((".html", ".md")):
                os.remove(os.path.join(posts_dir, f))

    n_pages = n_posts = 0
    skipped = []
    kept = []

    for item in channel.findall("item"):
        ptype = item.findtext("wp:post_type", default="", namespaces=NS)
        status = item.findtext("wp:status", default="", namespaces=NS)
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()

        if ptype not in ("page", "post"):
            continue
        if status != "publish":
            skipped.append(f"{title} ({status}, not on live site)")
            continue
        if title in SKIP_TITLES:
            continue

        raw = item.findtext("content:encoded", default="", namespaces=NS) or ""
        body = clean(raw)

        if ptype == "page":
            if link not in PAGES:
                skipped.append(f"{title} (no live URL in crawl)")
                continue
            permalink = PAGES[link]
            fm = {"title": yaml_quote(title), "permalink": permalink}
            if permalink in REDIRECTS:
                fm["redirect_from"] = REDIRECTS[permalink]

            if permalink == "/":
                body = HOMEPAGE_INTRO + "\n" + body

            slug = "index" if permalink == "/" else permalink.strip("/").replace("/", "-")
            dest = os.path.join(pages_dir, f"{slug}.html")
            if os.path.exists(dest) and not force:
                kept.append(os.path.relpath(dest, ROOT))
            else:
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(front_matter(fm) + body + "\n")
                n_pages += 1

        else:
            date = item.findtext("wp:post_date", default="", namespaces=NS)[:10]
            slug = item.findtext("wp:post_name", default="", namespaces=NS)
            creator = item.findtext("dc:creator", default="", namespaces=NS)
            fm = {"title": yaml_quote(title), "date": date}
            if creator:
                fm["author"] = yaml_quote(authors.get(creator, creator))
            dest = os.path.join(posts_dir, f"{date}-{slug}.html")
            if os.path.exists(dest) and not force:
                kept.append(os.path.relpath(dest, ROOT))
            else:
                with open(dest, "w", encoding="utf-8") as fh:
                    fh.write(front_matter(fm) + body + "\n")
                n_posts += 1

    # /news/ carries the author- and category-archive redirects.
    news = os.path.join(pages_dir, "news.html")
    with open(news, encoding="utf-8") as fh:
        src = fh.read()
    if "redirect_from" not in src:
        block = "redirect_from:\n" + "".join(
            f"  - {u}\n" for u in REDIRECTS["/news/"])
        src = src.replace("permalink: /news/\n", "permalink: /news/\n" + block, 1)
        with open(news, "w", encoding="utf-8") as fh:
            fh.write(src)

    if kept:
        print(f"Left untouched (already present; --force to regenerate): {len(kept)}")
    print(f"Pages migrated: {n_pages}")
    print(f"Posts migrated: {n_posts}")
    print(f"Media staged:   {len([v for v in media_map.values() if v.startswith('/assets')])}")

    if skipped:
        print("\nDeliberately not migrated:")
        for s in skipped:
            print(f"  - {s}")

    if unresolved:
        print("\nWARNING — referenced media not found locally:")
        for u in sorted(unresolved):
            print(f"  - {u}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
