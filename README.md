# Sitemap Unpacker

Reads a list of sitemap URLs and unpacks them all into a single flat CSV of page URLs. Handles both sitemap indexes and leaf sitemaps.

## Usage

1. Add sitemap URLs to `sitemaps.txt` — one per line. Optionally prefix each with a label and a tab:

```
Example 	https://www.example.com/sitemap/story/update.xml
Example 	https://www.example-herald.com/sitemap/story/update.xml
```

2. Run:

```bash
python unpack_sitemaps.py
```

Output: `urls.csv` with columns `sitemap_url` and `page_url`.

## Prerequisites

Fetches sitemaps via the `curl` command-line tool, so no Python packages are required.
