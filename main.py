import datetime
import os
import os.path
import time
import random
import re
import logging
import sys
from urllib.parse import urlparse
from urllib.request import Request as UrlRequest, urlopen
import cloudscraper
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

# ================= 設定區 =================
# 請用環境變數設定 Google 日曆 ID，避免把個人日曆 ID 寫進版控。
CALENDAR_ID = os.getenv('CALENDAR_ID', '').strip()
# ==========================================

SCOPES = ['https://www.googleapis.com/auth/calendar']
TAIPEI_TZ = datetime.timezone(datetime.timedelta(hours=8))
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
KOBO_IMPERSONATE = os.getenv('KOBO_IMPERSONATE', 'chrome124').strip() or 'chrome124'
ESLITE_BOOK_EXHIBIT_API = "https://athena.eslite.com/api/v1/book_exhibits/{exhibit_id}"
ESLITE_PRICE_API = "https://athena.eslite.com/api/v2/products/{product_ids}/prices"
ESLITE_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
DEFAULT_ESLITE_EXHIBITS = ['CU202501-00235']

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout
)

def clean_title_display(text):
    """
    清理顯示用的書名：移除書名號、括號與常用標點符號，優化日曆視覺效果。
    """
    clean = re.sub(r'[《》「」『』\(\)（）\[\]！？：；]', '', text)
    return clean.strip()

def clean_for_compare(text):
    """
    清理比對用的字串：僅保留文字與數字，確保不會因空格或符號差異導致重複同步。
    """
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).strip()

def normalize_link(link):
    """
    正規化書籍連結，作為跨日期與跨標題格式的穩定比對 key。
    """
    if not link:
        return ''
    link = link.strip().split('#', 1)[0].split('?', 1)[0].rstrip('/')
    return link.lower()

def extract_link_from_description(description):
    """
    從既有日曆事件 description 取回先前寫入的書籍連結。
    """
    if not description:
        return ''
    match = re.search(r'連結：\s*(\S+)', description)
    return normalize_link(match.group(1)) if match else ''

def event_matches_book(event, book):
    """
    先用書籍連結判斷同一本書；舊資料沒有連結時再退回 summary 比對。
    """
    event_link = extract_link_from_description(event.get('description', ''))
    book_link = normalize_link(book.get('link', ''))
    if event_link and book_link and event_link == book_link:
        return True
    return clean_for_compare(event.get('summary', '')) == book['compare_key']

def list_calendar_events(service, time_min, time_max):
    """
    列出指定時間範圍內所有事件，處理 Google Calendar 分頁。
    """
    events = []
    page_token = None
    while True:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            maxResults=2500,
            pageToken=page_token
        ).execute()
        events.extend(result.get('items', []))
        page_token = result.get('nextPageToken')
        if not page_token:
            return events

def resolve_month_day(month, day, anchor_date, prefer_future=False, past_window_days=14):
    """
    將頁面上的 m/d 轉成實際日期；跨年時選擇最接近 anchor_date 的年份。
    """
    candidates = []
    for year in (anchor_date.year - 1, anchor_date.year, anchor_date.year + 1):
        try:
            candidates.append(datetime.date(year, int(month), int(day)))
        except ValueError:
            continue

    if not candidates:
        raise ValueError(f"無效日期: {month}/{day}")

    if prefer_future:
        oldest_allowed = anchor_date - datetime.timedelta(days=past_window_days)
        return min(
            candidates,
            key=lambda d: (d < oldest_allowed, abs((d - anchor_date).days))
        )

    return min(candidates, key=lambda d: abs((d - anchor_date).days))

def parse_eslite_exhibit_id(value):
    """
    支援直接填誠品活動 ID 或完整 exhibitions URL。
    """
    if value.startswith("http://") or value.startswith("https://"):
        parts = [part for part in urlparse(value).path.split("/") if part]
        if len(parts) >= 2 and parts[-2] == "exhibitions":
            return parts[-1]
        raise ValueError("URL does not look like an eslite exhibitions page")
    return value

ESLITE_EXHIBITS = [
    parse_eslite_exhibit_id(exhibit.strip())
    for exhibit in os.getenv('ESLITE_EXHIBITS', ','.join(DEFAULT_ESLITE_EXHIBITS)).split(',')
    if exhibit.strip()
]

def fetch_eslite_json(url):
    """
    誠品 API 偶爾會擋一般 requests；優先用 curl_cffi 模擬 Chrome。
    """
    if curl_requests:
        response = curl_requests.get(
            url,
            headers={"User-Agent": ESLITE_USER_AGENT},
            impersonate="chrome124",
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    request = UrlRequest(url, headers={"User-Agent": ESLITE_USER_AGENT})
    with urlopen(request, timeout=30) as response:
        import json
        return json.load(response)

def iter_eslite_products(exhibit):
    seen = set()

    def add_product(product, section):
        guid = str(product.get("product_guid") or "")
        if not guid or guid in seen:
            return None
        seen.add(guid)
        return {
            '商品': product.get("name") or "",
            '金額': "",
            '區塊': section or "",
            '作者': product.get("author") or "",
            'guid': guid,
        }

    for content in exhibit.get("contents") or []:
        product = content.get("product")
        if product:
            row = add_product(product, content.get("title") or content.get("name"))
            if row:
                yield row

        for book_list in content.get("book_list") or []:
            for product in book_list.get("products") or []:
                row = add_product(product, book_list.get("name") or "")
                if row:
                    yield row

def fetch_eslite_prices(product_ids, batch_size=10):
    prices = {}
    for index in range(0, len(product_ids), batch_size):
        batch = product_ids[index:index + batch_size]
        url = ESLITE_PRICE_API.format(product_ids=",".join(batch))
        for item in fetch_eslite_json(url):
            guid = str(item.get("guid") or "")
            if guid:
                prices[guid] = item.get("final_price")
    return prices

def fetch_eslite_specials(exhibit_id):
    exhibit = fetch_eslite_json(ESLITE_BOOK_EXHIBIT_API.format(exhibit_id=exhibit_id))
    products = list(iter_eslite_products(exhibit))
    prices = fetch_eslite_prices([product['guid'] for product in products])
    for product in products:
        product['活動'] = exhibit.get("name") or exhibit_id
        product['活動ID'] = exhibit_id
        product['金額'] = prices.get(product['guid'], "")
    return products

def parse_eslite_sale_date(*texts):
    """
    從誠品區塊文字解析特價截止日；沒有寫日期就視為今天仍在特價。
    """
    anchor_date = datetime.datetime.now().date()
    text = " ".join(text for text in texts if text)
    match = re.search(r'(?:至|到|~|～)\s*(\d{1,2})/(\d{1,2})', text)
    if match:
        return resolve_month_day(match.group(1), match.group(2), anchor_date, prefer_future=True).isoformat()

    compact_match = re.search(r'\d{4}\s*[-~～]\s*(\d{2})(\d{2})', text)
    if compact_match:
        return resolve_month_day(compact_match.group(1), compact_match.group(2), anchor_date, prefer_future=True).isoformat()

    return anchor_date.isoformat()

def get_kobo_week_urls(anchor_date):
    """
    產生 Kobo 99 URL；Kobo 99 文章以週四為一期起點，不是 ISO 週一。
    """
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

def get_pubu_books():
    """
    抓取 Pubu 特價書單並判定分類。
    """
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    url = "https://www.pubu.com.tw/campaign/event/pubu99select"
    books = []
    logging.info("🔍 正在檢查 Pubu 頁面...")
    
    try:
        time.sleep(random.uniform(1, 2))
        resp = scraper.get(url, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            book_blocks = soup.select('.in_book')
            anchor_date = datetime.datetime.now().date()
            
            for block in book_blocks:
                link_tag = block.select_one('.container h2 a, h2 a')
                price_tag = block.select_one('.price-div h3.te span')
                if not (link_tag and price_tag): continue
                if price_tag.get_text(strip=True) != '99': continue
                
                title_img = block.select_one('.cover-div img[title], img[title]')
                raw_title = title_img.get('title', '').strip() if title_img else ''
                if not raw_title:
                    raw_title = link_tag.get_text(strip=True)
                display_title = clean_title_display(raw_title)
                
                # 處理網址拼接邏輯，避免重複組合
                href = link_tag.get('href', '')
                link = href if href.startswith('http') else "https://www.pubu.com.tw" + href
                
                # 解析日期與分類邏輯；沒有日期的 99 元書視為目前正在特價。
                desc_tag = block.select_one('.descript')
                desc_text = desc_tag.get_text(strip=True) if desc_tag else ''
                dates = re.findall(r'(\d{1,2})/(\d{1,2})', desc_text)

                # 判定為「即時」或「一日」特價
                if dates and ("〜" in desc_text or "~" in desc_text):
                    m, d = dates[0]
                    target_date = resolve_month_day(m, d, anchor_date, prefer_future=True).isoformat()
                    summary = f"pubu即時99 {display_title}"
                elif dates:
                    m, d = dates[0]
                    target_date = resolve_month_day(m, d, anchor_date, prefer_future=True).isoformat()
                    summary = f"pubu一日99 {display_title}"
                else:
                    target_date = anchor_date.isoformat()
                    summary = f"pubu即時99 {display_title}"

                books.append({
                    'summary': summary,
                    'compare_key': clean_for_compare(summary),
                    'description': f"原始書名：{raw_title}\n連結：{link}\n(自動同步)",
                    'link': link,
                    'date': target_date,
                    'color': '10' # 青綠色
                })
    except Exception:
        logging.exception("❌ Pubu 抓取失敗")
    return books

def fetch_kobo_page(url):
    """
    Kobo/Cloudflare 會檢查 TLS 指紋，單純偽裝 User-Agent 在部分 NAS/IP 仍會 403。
    優先使用 curl_cffi 模擬 Chrome；未安裝時退回 cloudscraper。
    """
    fallback_headers = {
        **KOBO_BROWSER_HEADERS,
        'Referer': 'https://www.kobo.com/zh/blog',
    }
    if curl_requests:
        return curl_requests.get(
            url,
            timeout=15,
            headers=KOBO_CURL_HEADERS,
            impersonate=KOBO_IMPERSONATE
        )

    logging.warning("⚠️ curl_cffi 未安裝，Kobo 抓取退回 cloudscraper，可能仍會被 Cloudflare 擋 403")
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    scraper.headers.update(KOBO_BROWSER_HEADERS)
    return scraper.get(url, timeout=15, headers=fallback_headers)

def get_kobo_books():
    """
    抓取 Kobo 特價書單。
    """
    now = datetime.datetime.now().date()
    urls = get_kobo_week_urls(now)
    
    logging.info("🔍 正在檢查 Kobo 頁面...")
    books = []
    for url, week_anchor in urls:
        try:
            resp = fetch_kobo_page(url)
            if resp.status_code == 404:
                time.sleep(random.uniform(2, 4))
                resp = fetch_kobo_page(f"{url}?nocache={int(time.time())}")
            if resp.status_code != 200:
                logging.warning(f"⚠️ Kobo 頁面讀取失敗: {resp.status_code} - {url}")
                continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            book_blocks = soup.select('.book-block')
            if not book_blocks:
                title = soup.title.get_text(strip=True) if soup.title else "無標題"
                logging.warning(f"⚠️ Kobo 頁面沒有找到書籍區塊: {title} - {url}")
                continue

            for block in book_blocks:
                # 往前回溯尋找日期文字
                search_text = "".join([n.get_text() for n in block.find_all_previous(limit=15)])
                date_match = re.search(r'(\d{1,2})/(\d{1,2})', search_text)
                
                if date_match:
                    book_date = resolve_month_day(date_match.group(1), date_match.group(2), week_anchor).isoformat()
                    title_tag = block.select_one('h2 > .title') or block.select_one('.title')
                    if not title_tag: continue
                    
                    raw_title = title_tag.get_text(strip=True)
                    display_title = clean_title_display(raw_title)
                    link_tag = block.select_one('a')
                    if not link_tag or not link_tag.get('href'):
                        continue
                    link = link_tag['href']
                    summary = f"kobo99 {display_title}"
                    
                    books.append({
                        'summary': summary, 
                        'compare_key': clean_for_compare(summary),
                        'description': f"原始書名：{raw_title}\n連結：{link}", 
                        'link': link,
                        'date': book_date, 
                        'color': '5' # 藍色
                    })
            if books: break
        except Exception:
            logging.exception(f"❌ Kobo 抓取失敗: {url}")
            continue
    return books

def get_eslite_books():
    """
    抓取誠品活動頁特價書單。
    """
    books = []
    logging.info("正在檢查誠品活動頁...")
    for exhibit_id in ESLITE_EXHIBITS:
        try:
            specials = fetch_eslite_specials(exhibit_id)
            logging.info(f"誠品 {exhibit_id} 抓到 {len(specials)} 筆")
            for item in specials:
                raw_title = item.get('商品', '')
                display_title = clean_title_display(re.sub(r'\s*\(電子書\)\s*$', '', raw_title))
                price = item.get('金額', '')
                target_date = parse_eslite_sale_date(item.get('區塊', ''), item.get('活動', ''))
                link = f"https://www.eslite.com/product/{item.get('guid')}"
                summary = f"誠品{price} {display_title}" if price else f"誠品 {display_title}"
                books.append({
                    'summary': summary,
                    'compare_key': clean_for_compare(summary),
                    'description': (
                        f"原始書名：{raw_title}\n"
                        f"活動：{item.get('活動', '')}\n"
                        f"區塊：{item.get('區塊', '')}\n"
                        f"金額：{price}\n"
                        f"連結：{link}\n"
                        "(自動同步)"
                    ),
                    'link': link,
                    'date': target_date,
                    'color': '11' # 紅色
                })
        except Exception:
            logging.exception(f"❌ 誠品抓取失敗: {exhibit_id}")
    return books

def get_calendar_service():
    """
    初始化 Google Calendar API 服務。
    """
    creds = None
    base_path = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(base_path, 'token.json')

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                logging.warning("⚠️ Google OAuth token 已失效，準備重新授權並更新 token.json")
                creds = None

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(os.path.join(base_path, 'credentials.json'), SCOPES)
            creds = flow.run_local_server(port=0)
            logging.info("✅ Google OAuth 重新授權成功")

        with open(token_file, 'w') as token:
            token.write(creds.to_json())

    return build('calendar', 'v3', credentials=creds, cache_discovery=False)

def sync_all():
    """
    執行主同步邏輯。
    """
    if not CALENDAR_ID:
        raise RuntimeError("請先設定 CALENDAR_ID 環境變數")

    all_books = get_kobo_books() + get_pubu_books() + get_eslite_books()
    if not all_books:
        logging.warning("⚠️ 未抓到任何 Kobo/Pubu/誠品 書籍，略過日曆同步")
        return
    
    service = get_calendar_service()
    book_dates = [datetime.date.fromisoformat(book['date']) for book in all_books]
    range_start = min(book_dates) - datetime.timedelta(days=60)
    range_end = max(book_dates) + datetime.timedelta(days=2)
    t_range_start = datetime.datetime.combine(range_start, datetime.time.min, TAIPEI_TZ).isoformat()
    t_range_end = datetime.datetime.combine(range_end, datetime.time.min, TAIPEI_TZ).isoformat()
    existing_events = list_calendar_events(service, t_range_start, t_range_end)
    
    for book in all_books:
        # 檢查近期是否已有相同書籍；優先用書籍連結避免標題格式變動造成重複。
        if any(event_matches_book(e, book) for e in existing_events):
            logging.info(f"⏭️ 跳過重複: {book['date']} - {book['summary']}")
            continue
        
        # 建立全天事件
        event = {
            'summary': book['summary'],
            'description': book['description'],
            'start': {'date': book['date']},
            'end': {'date': (datetime.date.fromisoformat(book['date']) + datetime.timedelta(days=1)).isoformat()},
            'colorId': book['color'],
            'transparency': 'transparent'
        }
        created_event = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        existing_events.append(created_event)
        logging.info(f"✅ 同步成功: {book['date']} - {book['summary']}")
        time.sleep(0.3)

if __name__ == "__main__":
    try:
        sync_all()
    except Exception:
        logging.exception("❌ Kobo/Pubu 日曆同步失敗")
        raise
