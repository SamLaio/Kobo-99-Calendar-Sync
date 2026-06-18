import datetime
import os
import os.path
import time
import random
import re
import logging
import sys
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
# 請在此填入你的 Google 日曆 ID
CALENDAR_ID = 'Google 日曆 ID'
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

def get_kobo_week_urls(anchor_date):
    """
    產生本週與下週 Kobo 99 URL，正確處理 ISO 週次跨年。
    """
    urls = []
    for days in (0, 7):
        target_date = anchor_date + datetime.timedelta(days=days)
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
    all_books = get_kobo_books() + get_pubu_books()
    if not all_books:
        logging.warning("⚠️ 未抓到任何 Kobo/Pubu 書籍，略過日曆同步")
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
