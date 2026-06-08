# Sitemap Unpacker

Reads a list of sitemap URLs and unpacks them all into a single flat CSV of page URLs. Handles both sitemap indexes and leaf sitemaps.

## Usage

1. Add sitemap URLs to `sitemaps.txt` — one per line. Optionally prefix each with a label and a tab:

```
Charlotte Observer	https://www.charlotteobserver.com/sitemap/story/update.xml
Miami Herald	https://www.miamiherald.com/sitemap/story/update.xml
```

2. Run:

```bash
python unpack_sitemaps.py
```

Output: `urls.csv` with columns `sitemap_url` and `page_url`.

## Prerequisites

```bash
pip install requests
```
