import argparse
import csv
import datetime
from pathlib import Path
import random
import re
import sys
import time

import cloudscraper
from bs4 import BeautifulSoup

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None


KOBO_BROWSER_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Cache-Control': 'no-cache',
    'Pragma': 'no-cache',
    'Sec-Ch-Ua': '"Google Chrome";v="124", "Chromium";v="124", "Not.A/Brand";v="24"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"Windows"',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}
KOBO_CURL_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.kobo.com/zh/blog',
}
KOBO_IMPERSONATE = 'chrome124'


def clean_title_display(text):
    clean = re.sub(r'[《》「」『』\(\)（）\[\]！？：；]', '', text)
    return clean.strip()


def clean_for_compare(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).strip()


def resolve_month_day(month, day, anchor_date):
    candidates = []
    for year in (anchor_date.year - 1, anchor_date.year, anchor_date.year + 1):
        try:
            candidates.append(datetime.date(year, int(month), int(day)))
        except ValueError:
            continue
    return min(candidates, key=lambda d: abs((d - anchor_date).days))


def get_kobo_week_urls(anchor_date):
    urls = []
    active_thursday = anchor_date - datetime.timedelta(days=(anchor_date.weekday() - 3) % 7)
    week_offsets = (7, 0, -7) if anchor_date.weekday() == 2 else (0, 7, -7)
    for days in week_offsets:
        target_date = active_thursday + datetime.timedelta(days=days)
        iso_year, iso_week, _ = target_date.isocalendar()
        url = f"https://www.kobo.com/zh/blog/weekly-dd99-{iso_year}-w{iso_week:02d}"
        week_anchor = datetime.date.fromisocalendar(iso_year, iso_week, 4)
        if not any(existing_url == url for existing_url, _ in urls):
            urls.append((url, week_anchor))
    return urls


def fetch_kobo_page(url):
    if curl_requests:
        return curl_requests.get(
            url,
            timeout=15,
            headers=KOBO_CURL_HEADERS,
            impersonate=KOBO_IMPERSONATE,
        )

    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    scraper.headers.update(KOBO_BROWSER_HEADERS)
    return scraper.get(url, timeout=15, headers={**KOBO_BROWSER_HEADERS, 'Referer': 'https://www.kobo.com/zh/blog'})


def get_kobo_books():
    now = datetime.datetime.now().date()
    books = []
    for url, week_anchor in get_kobo_week_urls(now):
        resp = fetch_kobo_page(url)
        if resp.status_code == 404:
            time.sleep(random.uniform(2, 4))
            resp = fetch_kobo_page(f"{url}?nocache={int(time.time())}")
        if resp.status_code != 200:
            continue

        soup = BeautifulSoup(resp.text, 'html.parser')
        book_blocks = soup.select('.book-block')
        if not book_blocks:
            continue

        for block in book_blocks:
            search_text = "".join([node.get_text() for node in block.find_all_previous(limit=15)])
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', search_text)
            title_tag = block.select_one('h2 > .title') or block.select_one('.title')
            link_tag = block.select_one('a')
            if not (date_match and title_tag and link_tag and link_tag.get('href')):
                continue

            raw_title = title_tag.get_text(strip=True)
            display_title = clean_title_display(raw_title)
            summary = f"kobo99 {display_title}"
            books.append({
                'summary': summary,
                'compare_key': clean_for_compare(summary),
                'description': f"原始書名：{raw_title}\n連結：{link_tag['href']}",
                'raw_title': raw_title,
                'date': resolve_month_day(date_match.group(1), date_match.group(2), week_anchor).isoformat(),
                'link': link_tag['href'],
                'color': '5',
                'source_url': url,
            })
        if books:
            break
    return books


def write_tsv(rows, output):
    columns = ['summary', 'date', 'raw_title', 'link', 'color', 'source_url', 'compare_key', 'description']
    writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def test_output_path(path):
    output = Path(path)
    if not output.parent or str(output.parent) == ".":
        output = Path("test") / output
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description="Fetch Kobo weekly 99 special books.")
    parser.add_argument("-o", "--output", help="write TSV to this file instead of stdout")
    args = parser.parse_args()

    rows = get_kobo_books()
    rows.sort(key=lambda row: (row['date'], row['summary']))
    if args.output:
        output_path = test_output_path(args.output)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as output:
            write_tsv(rows, output)
        print(f"Wrote {len(rows)} products to {output_path}")
        return
    write_tsv(rows, sys.stdout)


if __name__ == "__main__":
    main()
