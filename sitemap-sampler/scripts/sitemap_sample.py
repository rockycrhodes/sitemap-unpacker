#!/usr/bin/env python3
"""
Sitemap Sampler — crawls one or more sitemaps (including nested sitemap indexes),
applies optional filters, and returns a random sample of page URLs.

Usage:
    # Single sitemap
    python sitemap_sample.py --sitemap https://www.example.com/sitemap/story/update.xml

    # Multiple sitemaps (comma-separated)
    python sitemap_sample.py --sitemap https://www.example.com/sitemap/story/update.xml,https://www.example.com/sitemap/section/update.xml

Common options:
    --sample 15          Number of URLs to return (default: 15)
    --filter /news/      Only include URLs containing this string
                         (comma-separated for multiple: /news/,/sports/)
    --exclude /tag/,/author/   Exclude URLs containing these strings
    --days 30            Only include URLs with lastmod within N days
    --seed 42            Random seed for reproducibility (omit for random)
    --output urls.txt    Write results to file instead of stdout
    --max-fetch 100      Max child sitemaps to fetch (safety cap, default: 100)
    --dump               Dump ALL matching URLs instead of sampling
    --verbose            Print progress while fetching
"""

import argparse
import random
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

NS    = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DELAY = 0.3   # seconds between requests


# ── HTTP fetch ────────────────────────────────────────────────────────────────

def fetch_xml(url, timeout=45):
    """Fetch a URL, preferring curl_cffi (Chrome TLS impersonation) to bypass CDN bot detection."""
    try:
        from curl_cffi import requests as cffi_req
        resp = cffi_req.get(url, impersonate="chrome124", timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except ImportError:
        pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    }
    try:
        import requests as req_lib
        # Force HTTP/1.1 — corporate SSL-inspection proxies often break HTTP/2
        session = req_lib.Session()
        session.headers.update(headers)
        resp = session.get(url, timeout=timeout,
                           headers={"Connection": "keep-alive"},
                           allow_redirects=True)
        resp.raise_for_status()
        return resp.text
    except ImportError:
        pass

    # urllib fallback
    import urllib.request
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        raw = resp.read()
        # Handle gzip if Content-Encoding header is set
        encoding = resp.headers.get("Content-Encoding", "")
        if encoding == "gzip":
            import gzip
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")


# ── XML helpers ───────────────────────────────────────────────────────────────

def find_el(parent, tag_ns, tag_plain):
    """Safe find that avoids the ElementTree leaf-element falsy-bool pitfall."""
    el = parent.find(tag_ns, NS)
    if el is None:
        el = parent.find(tag_plain)
    return el


def locs_from(root, child_tag):
    elements = root.findall(f"sm:{child_tag}", NS) or root.findall(child_tag)
    result = []
    for e in elements:
        loc = find_el(e, "sm:loc", "loc")
        if loc is not None and loc.text:
            result.append(loc.text.strip())
    return result


def lastmods_from(root, child_tag):
    elements = root.findall(f"sm:{child_tag}", NS) or root.findall(child_tag)
    result = {}
    for e in elements:
        loc = find_el(e, "sm:loc", "loc")
        lm  = find_el(e, "sm:lastmod", "lastmod")
        if loc is not None and loc.text and lm is not None and lm.text:
            try:
                dt = datetime.fromisoformat(lm.text.strip()[:19]).replace(tzinfo=timezone.utc)
                result[loc.text.strip()] = dt
            except ValueError:
                pass
    return result


def parse_sitemap(xml_text):
    """Returns ('index', child_locs, {}) or ('urlset', page_locs, lastmod_map)."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"XML parse error: {e}")

    tag = root.tag.split("}")[-1] if "}" in root.tag else root.tag
    if tag == "sitemapindex":
        return "index", locs_from(root, "sitemap"), {}
    else:
        return "urlset", locs_from(root, "url"), lastmods_from(root, "url")


# ── Core crawl ────────────────────────────────────────────────────────────────

def crawl(root_urls, max_fetch=100, verbose=False):
    """
    Crawl one or more sitemaps recursively.
    Returns list of (page_url, lastmod_or_None).
    """
    queue   = list(root_urls)
    visited = set()
    pages   = []
    fetched = 0

    while queue and fetched < max_fetch:
        url = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)

        if verbose:
            print(f"  Fetching: {url}", file=sys.stderr)

        try:
            xml_text = fetch_xml(url)
            fetched += 1
        except Exception as e:
            print(f"  Warning: could not fetch {url}: {e}", file=sys.stderr)
            time.sleep(DELAY)
            continue

        try:
            kind, found_locs, lm_map = parse_sitemap(xml_text)
        except ValueError as e:
            print(f"  Warning: {e} for {url}", file=sys.stderr)
            time.sleep(DELAY)
            continue

        if kind == "index":
            queue.extend(l for l in found_locs if l not in visited)
        else:
            for loc in found_locs:
                pages.append((loc, lm_map.get(loc)))

        time.sleep(DELAY)

    if fetched >= max_fetch and queue:
        print(f"  Note: hit --max-fetch {max_fetch} limit; {len(queue)} sitemaps not fetched.", file=sys.stderr)

    return pages


# ── Filtering ─────────────────────────────────────────────────────────────────

def apply_filters(pages, include_patterns, exclude_patterns, cutoff_date):
    result = []
    for url, lm in pages:
        if include_patterns and not any(p in url for p in include_patterns):
            continue
        if exclude_patterns and any(p in url for p in exclude_patterns):
            continue
        if cutoff_date is not None:
            if lm is None or lm < cutoff_date:
                continue
        result.append((url, lm))
    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sample URLs from sitemaps for CWV testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Input — URL or local file(s)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--sitemap",    help="Sitemap URL(s), comma-separated")
    input_group.add_argument("--file",       help="Local sitemap XML file(s), comma-separated. "
                             "Download sitemaps manually in your browser and pass the paths here.")

    parser.add_argument("--sample",    type=int, default=15)
    parser.add_argument("--filter",    default="", help="Include URLs containing these substrings (comma-sep)")
    parser.add_argument("--exclude",   default="", help="Exclude URLs containing these substrings (comma-sep)")
    parser.add_argument("--days",      type=int, default=None)
    parser.add_argument("--seed",      type=int, default=None)
    parser.add_argument("--output",    default=None)
    parser.add_argument("--max-fetch", type=int, default=100, dest="max_fetch")
    parser.add_argument("--dump",      action="store_true")
    parser.add_argument("--verbose",   action="store_true")
    args = parser.parse_args()

    # Resolve sitemap URLs / files
    local_files = []
    if args.file:
        local_files = [f.strip() for f in args.file.split(",") if f.strip()]
        root_urls = []
    else:
        root_urls = [u.strip() for u in args.sitemap.split(",") if u.strip()]

    include_patterns = [p.strip() for p in args.filter.split(",")  if p.strip()] if args.filter  else []
    exclude_patterns = [p.strip() for p in args.exclude.split(",") if p.strip()] if args.exclude else []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=args.days)) if args.days else None
    seed   = args.seed if args.seed is not None else random.randint(0, 99999)

    print(f"Sitemap Sampler", file=sys.stderr)
    for f in local_files:
        print(f"  (local) {f}", file=sys.stderr)
    for u in root_urls:
        print(f"  {u}", file=sys.stderr)
    if include_patterns: print(f"Include filters: {include_patterns}", file=sys.stderr)
    if exclude_patterns: print(f"Exclude filters: {exclude_patterns}", file=sys.stderr)
    if cutoff:           print(f"Recency cutoff:  last {args.days} days (since {cutoff.date()})", file=sys.stderr)
    print(f"Seed: {seed}", file=sys.stderr)
    print(file=sys.stderr)

    # Parse any local files first
    local_pages = []
    for path in local_files:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                xml_text = fh.read()
            kind, found_locs, lm_map = parse_sitemap(xml_text)
            if kind == "index":
                print(f"  Note: {path} is a sitemap index — child sitemaps will be fetched over network.", file=sys.stderr)
                root_urls.extend(found_locs)
            else:
                for loc in found_locs:
                    local_pages.append((loc, lm_map.get(loc)))
                print(f"  {path}: {len(found_locs)} URLs", file=sys.stderr)
        except Exception as e:
            print(f"  Warning: could not read {path}: {e}", file=sys.stderr)

    pages = local_pages + crawl(root_urls, max_fetch=args.max_fetch, verbose=args.verbose)
    print(f"Found {len(pages)} total URLs", file=sys.stderr)

    filtered = apply_filters(pages, include_patterns, exclude_patterns, cutoff)
    print(f"After filters: {len(filtered)} matching URLs", file=sys.stderr)

    if not filtered:
        print("\nNo URLs matched. Try --verbose to debug, or relax --filter / --days.", file=sys.stderr)
        sys.exit(0)

    if args.dump:
        sampled = [url for url, _ in filtered]
    else:
        n = min(args.sample, len(filtered))
        random.seed(seed)
        sampled = [url for url, _ in random.sample(filtered, n)]

    label = "all matching" if args.dump else f"sample of {len(sampled)}"
    print(f"Returning {label} URLs  (seed={seed})\n", file=sys.stderr)

    output_lines = "\n".join(sampled)
    if args.output:
        with open(args.output, "w") as f:
            f.write(output_lines + "\n")
        print(f"Saved to: {args.output}", file=sys.stderr)
    else:
        print(output_lines)


if __name__ == "__main__":
    main()
