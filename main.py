import datetime
import os.path
import time
import random
import re
import cloudscraper
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ================= 設定區 =================
# 請在此填入你的 Google 日曆 ID
CALENDAR_ID = 'Google 日曆 ID'
# ==========================================

SCOPES = ['https://www.googleapis.com/auth/calendar']

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

def get_pubu_books():
    """
    抓取 Pubu 特價書單並判定分類。
    """
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    url = "https://www.pubu.com.tw/campaign/event/pubu99select"
    books = []
    print(f"🔍 正在檢查 Pubu 頁面...")
    
    try:
        time.sleep(random.uniform(1, 2))
        resp = scraper.get(url, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            book_blocks = soup.select('.in_book')
            current_year = datetime.datetime.now().year
            
            for block in book_blocks:
                link_tag = block.select_one('.container h2 a')
                desc_tag = block.select_one('.descript')
                if not (link_tag and desc_tag): continue
                
                raw_title = link_tag.get_text(strip=True)
                display_title = clean_title_display(raw_title)
                
                # 處理網址拼接邏輯，避免重複組合
                href = link_tag.get('href', '')
                link = href if href.startswith('http') else "https://www.pubu.com.tw" + href
                
                # 解析日期與分類邏輯
                desc_text = desc_tag.get_text(strip=True)
                dates = re.findall(r'(\d{1,2})/(\d{1,2})', desc_text)
                if not dates: continue

                # 判定為「即時」或「一日」特價
                if "〜" in desc_text or "~" in desc_text:
                    m, d = dates[0]
                    target_date = datetime.date(current_year, int(m), int(d)).isoformat()
                    summary = f"pubu即時99 {display_title}"
                else:
                    m, d = dates[0]
                    target_date = datetime.date(current_year, int(m), int(d)).isoformat()
                    summary = f"pubu一日99 {display_title}"

                books.append({
                    'summary': summary,
                    'compare_key': clean_for_compare(summary),
                    'description': f"原始書名：{raw_title}\n連結：{link}\n(自動同步)",
                    'date': target_date,
                    'color': '10' # 青綠色
                })
    except Exception as e:
        print(f"❌ Pubu 抓取失敗: {e}")
    return books

def get_kobo_books():
    """
    抓取 Kobo 特價書單。
    """
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    now = datetime.datetime.now()
    year, week, _ = now.isocalendar()
    
    # 同時檢查本週與下週 URL 以確保穩定性
    urls = [
        f"https://www.kobo.com/zh/blog/weekly-dd99-{year}-w{week:02d}",
        f"https://www.kobo.com/zh/blog/weekly-dd99-{year}-w{week+1:02d}"
    ]
    
    print(f"🔍 正在檢查 Kobo 頁面...")
    books = []
    for url in urls:
        try:
            resp = scraper.get(url, timeout=15)
            if resp.status_code != 200: continue
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            for block in soup.select('.book-block'):
                # 往前回溯尋找日期文字
                search_text = "".join([n.get_text() for n in block.find_all_previous(limit=15)])
                date_match = re.search(r'(\d{1,2})/(\d{1,2})', search_text)
                
                if date_match:
                    book_date = datetime.date(year, int(date_match.group(1)), int(date_match.group(2))).isoformat()
                    title_tag = block.select_one('h2 > .title') or block.select_one('.title')
                    if not title_tag: continue
                    
                    raw_title = title_tag.get_text(strip=True)
                    display_title = clean_title_display(raw_title)
                    link = block.select_one('a')['href']
                    summary = f"kobo99 {display_title}"
                    
                    books.append({
                        'summary': summary, 
                        'compare_key': clean_for_compare(summary),
                        'description': f"原始書名：{raw_title}\n連結：{link}", 
                        'date': book_date, 
                        'color': '5' # 藍色
                    })
            if books: break
        except: continue
    return books

def get_calendar_service():
    """
    初始化 Google Calendar API 服務。
    """
    creds = None
    base_path = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(base_path, 'token.json')
    if os.path.exists(token_file): creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token: creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(os.path.join(base_path, 'credentials.json'), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token: token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def sync_all():
    """
    執行主同步邏輯。
    """
    all_books = get_kobo_books() + get_pubu_books()
    if not all_books: return
    
    service = get_calendar_service()
    
    for book in all_books:
        # 檢查該日期是否已有相同書籍
        t_start, t_end = f"{book['date']}T00:00:00Z", f"{book['date']}T23:59:59Z"
        events = service.events().list(calendarId=CALENDAR_ID, timeMin=t_start, timeMax=t_end).execute().get('items', [])
        
        if any(clean_for_compare(e.get('summary', '')) == book['compare_key'] for e in events):
            print(f"⏭️ 跳過重複: {book['date']} - {book['summary']}")
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
        service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
        print(f"✅ 同步成功: {book['date']} - {book['summary']}")
        time.sleep(0.3)

if __name__ == "__main__":
    sync_all()