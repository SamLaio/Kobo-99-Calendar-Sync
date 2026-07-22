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


PUBU_URL = "https://www.pubu.com.tw/campaign/event/pubu99select"


def clean_title_display(text):
    clean = re.sub(r'[《》「」『』\(\)（）\[\]！？：；]', '', text)
    return clean.strip()


def clean_for_compare(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).strip()


def resolve_month_day(month, day, anchor_date, prefer_future=False, past_window_days=14):
    candidates = []
    for year in (anchor_date.year - 1, anchor_date.year, anchor_date.year + 1):
        try:
            candidates.append(datetime.date(year, int(month), int(day)))
        except ValueError:
            continue

    if prefer_future:
        oldest_allowed = anchor_date - datetime.timedelta(days=past_window_days)
        return min(candidates, key=lambda d: (d < oldest_allowed, abs((d - anchor_date).days)))
    return min(candidates, key=lambda d: abs((d - anchor_date).days))


def get_pubu_books():
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True})
    books = []
    time.sleep(random.uniform(1, 2))
    resp = scraper.get(PUBU_URL, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, 'html.parser')
    anchor_date = datetime.datetime.now().date()
    for block in soup.select('.in_book'):
        link_tag = block.select_one('.container h2 a, h2 a')
        price_tag = block.select_one('.price-div h3.te span')
        if not (link_tag and price_tag) or price_tag.get_text(strip=True) != '99':
            continue

        title_img = block.select_one('.cover-div img[title], img[title]')
        raw_title = title_img.get('title', '').strip() if title_img else link_tag.get_text(strip=True)
        display_title = clean_title_display(raw_title)
        href = link_tag.get('href', '')
        link = href if href.startswith('http') else "https://www.pubu.com.tw" + href
        desc_tag = block.select_one('.descript')
        desc_text = desc_tag.get_text(strip=True) if desc_tag else ''
        dates = re.findall(r'(\d{1,2})/(\d{1,2})', desc_text)

        if dates and ("〜" in desc_text or "~" in desc_text):
            target_date = resolve_month_day(*dates[0], anchor_date, prefer_future=True).isoformat()
            summary = f"pubu即時99 {display_title}"
        elif dates:
            target_date = resolve_month_day(*dates[0], anchor_date, prefer_future=True).isoformat()
            summary = f"pubu一日99 {display_title}"
        else:
            target_date = anchor_date.isoformat()
            summary = f"pubu即時99 {display_title}"

        books.append({
            'summary': summary,
            'compare_key': clean_for_compare(summary),
            'description': f"原始書名：{raw_title}\n連結：{link}\n(自動同步)",
            'raw_title': raw_title,
            'date': target_date,
            'link': link,
            'color': '10',
        })
    return books


def write_tsv(rows, output):
    columns = ['summary', 'date', 'raw_title', 'link', 'color', 'compare_key', 'description']
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
    parser = argparse.ArgumentParser(description="Fetch Pubu 99 special books.")
    parser.add_argument("-o", "--output", help="write TSV to this file instead of stdout")
    args = parser.parse_args()

    rows = get_pubu_books()
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
