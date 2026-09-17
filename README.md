# odis.org

The website for the **Ocean Data and Information System (ODIS)**, an IOC-UNESCO
initiative coordinated through IODE.

Jekyll, built and deployed to GitHub Pages by GitHub Actions.

Only `odis.org` lives here. `book.odis.org`, `catalogue.odis.org` and
`search.odis.org` are separate systems, managed separately.

## Local development

```sh
bundle install
bundle exec jekyll serve
```

## Checks

```sh
bundle exec jekyll build
python3 script/check_links.py _site
```

`check_links.py` verifies that every internal link and asset reference in the
built site resolves. It runs as a blocking step in CI.

> It replaces html-proofer, which in 5.2.2 reports "0 internal links" and exits
> 0 even on a page containing a deliberately broken link.

## Content

Pages live in `_pages/`, news posts in `_posts/`. Post URLs keep the
`/YYYY/MM/DD/slug/` form inherited from WordPress, so existing links and search
results keep working. Navigation and footer links are data, in `_data/`.

This site was migrated from WordPress. `script/migrate.py` regenerates
`_pages/`, `_posts/` and `assets/` from the original export, and is idempotent.
**The migration source material is deliberately not in this repository** — the
raw WordPress export contains staff email addresses and this repo is public.
It lives alongside the repo instead:

```
odis_migration/
  provenance/     WordPress export, site crawl, media library
  odis-website/   this repo
```

Set `ODIS_PROVENANCE` if that material lives elsewhere.

## Deployment

Pushing to `main` builds and deploys via `.github/workflows/build.yml`.
Repository Settings → Pages → Source must be set to **GitHub Actions**.
The custom domain is pinned by `CNAME`.
