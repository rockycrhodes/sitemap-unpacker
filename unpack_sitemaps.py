import csv
import sys
import time
import xml.etree.ElementTree as ET
import requests

SITEMAP_FILE = "sitemaps.txt"
OUTPUT_FILE = "urls.csv"
DELAY = 0.5  # seconds between requests to be polite

NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; sitemap-unpacker/1.0)"})


def parse_urls(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"  XML parse error: {e}", file=sys.stderr)
        return []
    # Try namespace-aware first, then fall back to no-namespace
    urls = [loc.text.strip() for loc in root.findall(".//sm:loc", NS) if loc.text]
    if not urls:
        urls = [loc.text.strip() for loc in root.findall(".//loc") if loc.text]
    return urls


def load_sitemaps(path):
    sitemaps = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t", 1)
            url = parts[1].strip() if len(parts) == 2 else parts[0].strip()
            if url:
                sitemaps.append(url)
    return sitemaps


def main():
    sitemaps = load_sitemaps(SITEMAP_FILE)
    print(f"Loaded {len(sitemaps)} sitemaps")

    total_urls = 0
    with open(OUTPUT_FILE, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["sitemap_url", "page_url"])

        for i, sitemap_url in enumerate(sitemaps, 1):
            print(f"[{i}/{len(sitemaps)}] {sitemap_url}", end=" ... ", flush=True)
            try:
                resp = session.get(sitemap_url, timeout=30)
                resp.raise_for_status()
                urls = parse_urls(resp.text)
                for url in urls:
                    writer.writerow([sitemap_url, url])
                total_urls += len(urls)
                print(f"{len(urls)} URLs")
            except requests.RequestException as e:
                print(f"ERROR: {e}", file=sys.stderr)
            time.sleep(DELAY)

    print(f"\nDone. {total_urls} total URLs written to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
