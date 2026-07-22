import argparse
import csv
from pathlib import Path
import sys
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None


BOOK_EXHIBIT_API = "https://athena.eslite.com/api/v1/book_exhibits/{exhibit_id}"
PRICE_API = "https://athena.eslite.com/api/v2/products/{product_ids}/prices"
DEFAULT_EXHIBITS = ["CU202501-00235"]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


def fetch_json(url):
    if curl_requests:
        response = curl_requests.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            impersonate="chrome124",
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    request = Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        import json

        return json.load(response)


def parse_exhibit_id(value):
    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in urlparse(value).path.split("/") if part]
        if len(parts) >= 2 and parts[-2] == "exhibitions":
            return parts[-1]
        raise ValueError("URL does not look like an eslite exhibitions page")
    return value


def iter_products(exhibit):
    seen = set()

    def add_product(product, section):
        guid = str(product.get("product_guid") or "")
        if not guid or guid in seen:
            return None
        seen.add(guid)
        return {
            "商品": product.get("name") or "",
            "金額": "",
            "區塊": section or "",
            "作者": product.get("author") or "",
            "guid": guid,
            "圖片": product.get("image") or "",
            "狀態": product.get("status") or "",
            "電子書": product.get("is_ebook", ""),
        }

    for content in exhibit.get("contents") or []:
        product = content.get("product")
        if product:
            row = add_product(product, content.get("title") or content.get("name"))
            if row:
                yield row

        for book_list in content.get("book_list") or []:
            section = book_list.get("name") or ""
            for product in book_list.get("products") or []:
                row = add_product(product, section)
                if row:
                    yield row


def batched(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def fetch_prices(product_ids, batch_size=10):
    prices = {}
    for batch in batched(product_ids, batch_size):
        url = PRICE_API.format(product_ids=",".join(batch))
        for item in fetch_json(url):
            guid = str(item.get("guid") or "")
            if guid:
                prices[guid] = item.get("final_price")
    return prices


def fetch_specials(exhibit_id, batch_size=10):
    exhibit = fetch_json(BOOK_EXHIBIT_API.format(exhibit_id=exhibit_id))
    products = list(iter_products(exhibit))
    prices = fetch_prices([product["guid"] for product in products], batch_size)
    for product in products:
        product["活動"] = exhibit.get("name") or exhibit_id
        product["活動ID"] = exhibit_id
        product["金額"] = prices.get(product["guid"], "")
    return products


def write_tsv(rows, output):
    columns = ["活動", "活動ID", "商品", "金額", "區塊", "作者", "guid", "圖片", "狀態", "電子書"]
    writer = csv.DictWriter(output, fieldnames=columns, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)


def print_price_summary(rows):
    counts = {}
    for row in rows:
        counts[row["金額"]] = counts.get(row["金額"], 0) + 1
    for price in sorted(counts, key=lambda value: (value == "", value)):
        print(f"{price or 'unknown'}: {counts[price]}")


def test_output_path(path):
    output = Path(path)
    if not output.parent or str(output.parent) == ".":
        output = Path("test") / output
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def main():
    parser = argparse.ArgumentParser(description="Fetch all eslite exhibition special-price products, not only $99.")
    parser.add_argument("exhibits", nargs="*", default=DEFAULT_EXHIBITS, help="exhibit ids or eslite exhibitions URLs")
    parser.add_argument("-o", "--output", help="write TSV to this file instead of stdout")
    parser.add_argument("--batch-size", type=int, default=10, help="price API product ids per request")
    args = parser.parse_args()

    rows = []
    for exhibit in args.exhibits:
        rows.extend(fetch_specials(parse_exhibit_id(exhibit), args.batch_size))
    rows.sort(key=lambda row: (row["活動ID"], row["金額"] if isinstance(row["金額"], int) else 999999, row["商品"]))

    if args.output:
        output_path = test_output_path(args.output)
        with open(output_path, "w", encoding="utf-8-sig", newline="") as output:
            write_tsv(rows, output)
        print(f"Wrote {len(rows)} products to {output_path}")
        print_price_summary(rows)
        return

    write_tsv(rows, sys.stdout)


if __name__ == "__main__":
    main()
