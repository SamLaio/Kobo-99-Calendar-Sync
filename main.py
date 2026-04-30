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
# ⚠️ 請務必確認日曆 ID 是否正確
CALENDAR_ID = '你的日曆ID@group.calendar.google.com'
# ==========================================

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_weekly_kobo_99():
    """抓取整週特價書單並回傳"""
    scraper = cloudscraper.create_scraper(
        browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        }
    )
    
    now = datetime.datetime.now()
    year, week, weekday = now.isocalendar()
    url = f"https://www.kobo.com/zh/blog/weekly-dd99-{year}-w{week:02d}"

    print(f"--- Kobo 一週特價同步啟動 ---")
    print(f"🚀 目標網址: {url}")

    try:
        # 隨機延遲模擬真人
        time.sleep(random.uniform(2, 5))
        resp = scraper.get(url, timeout=20)
        
        if resp.status_code != 200:
            print(f"❌ 進入網頁失敗，狀態碼: {resp.status_code}")
            return []

        print("✅ 成功繞過 Cloudflare！")
        soup = BeautifulSoup(resp.text, 'html.parser')
        blocks = soup.select('.book-block')
        
        weekly_books = []
        for block in blocks:
            search_text = ""
            prev_nodes = block.find_all_previous(limit=10)
            for node in prev_nodes:
                search_text += node.get_text()
                if node.get('class') and 'book-block' in node.get('class'):
                    break
            
            # 偵測日期 (5/1 或 05/01)
            date_match = re.search(r'(\d{1,2})/(\d{1,2})', search_text)
            
            if date_match:
                month = int(date_match.group(1))
                day = int(date_match.group(2))
                book_date = datetime.date(year, month, day).isoformat()
                
                try:
                    title = block.select_one('h2 > .title').get_text(strip=True)
                    # 清洗書名：移除特殊符號以利比對
                    clean_title = re.sub(r'[^\w\s\u4e00-\u9fff]', '', title)
                    
                    author = block.select_one('h2 > .author').get_text(strip=True).replace('由 ', '').replace('◎著', '')
                    link = block.select_one('.book-block__link')['href']
                    if not link.startswith('http'):
                        link = "https://www.kobo.com" + link
                    
                    weekly_books.append({
                        'summary': f"Kobo 99: {clean_title}",
                        'description': f"作者：{author}\n傳送門：{link}\n\n(系統自動同步)",
                        'date': book_date
                    })
                    print(f"📍 偵測到書單: {month}/{day} - {clean_title}")
                except AttributeError:
                    continue
        return weekly_books
    except Exception as e:
        print(f"❌ 抓取異常: {e}")
        return []

def get_calendar_service():
    """管理 Google API 憑證"""
    creds = None
    base_path = os.path.dirname(os.path.abspath(__file__))
    cred_file = os.path.join(base_path, 'credentials.json')
    token_file = os.path.join(base_path, 'token.json')

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(cred_file):
                raise FileNotFoundError(f"找不到憑證檔案: {cred_file}")
            flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def is_event_exists(service, date, summary):
    """嚴格比對該日是否已有相同標題"""
    t_start = f"{date}T00:00:00Z"
    t_end = f"{date}T23:59:59Z"
    try:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=t_start,
            timeMax=t_end,
            singleEvents=True
        ).execute()
        events = events_result.get('items', [])
        for event in events:
            if event.get('summary', '').strip() == summary.strip():
                return True
        return False
    except:
        return False

def sync_to_calendar(book_list):
    """執行同步"""
    if not book_list: return
    try:
        service = get_calendar_service()
        print(f"📅 開始同步至行事曆...")
        for book in book_list:
            if is_event_exists(service, book['date'], book['summary']):
                print(f"⏭️ 已有項目，跳過: {book['date']} - {book['summary']}")
                continue
            
            # Google 全天事件結束日期需為隔日
            end_date = (datetime.date.fromisoformat(book['date']) + datetime.timedelta(days=1)).isoformat()
            
            event = {
                'summary': book['summary'],
                'description': book['description'],
                'start': {'date': book['date']},
                'end': {'date': end_date},
                'colorId': '5', 
                'transparency': 'transparent',
            }
            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"✅ 同步成功: {book['date']} - {book['summary']}")
            time.sleep(0.8) # 稍微延遲

        print(f"🎉 任務執行完畢！")
    except Exception as e:
        print(f"❌ 行事曆寫入錯誤: {e}")

if __name__ == "__main__":
    books = get_weekly_kobo_99()
    if books:
        sync_to_calendar(books)