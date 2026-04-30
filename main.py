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
# ⚠️ 請填入你的日曆 ID
CALENDAR_ID = '你的日曆ID@group.calendar.google.com'
# ==========================================

SCOPES = ['https://www.googleapis.com/auth/calendar']

def clean_title(text):
    """清洗書名：移除特殊符號以利比對"""
    return re.sub(r'[^\w\s\u4e00-\u9fff]', '', text).strip()

def get_kobo_books():
    """抓取 Kobo 整週特價書單"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    now = datetime.datetime.now()
    year, week, _ = now.isocalendar()
    url = f"https://www.kobo.com/zh/blog/weekly-dd99-{year}-w{week:02d}"
    
    books = []
    print(f"🔍 正在檢查 Kobo 週蟬聯: {url}")
    try:
        time.sleep(random.uniform(2, 4))
        resp = scraper.get(url, timeout=20)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            blocks = soup.select('.book-block')
            for block in blocks:
                search_text = ""
                for node in block.find_all_previous(limit=10):
                    search_text += node.get_text()
                    if node.get('class') and 'book-block' in node.get('class'): break
                
                date_match = re.search(r'(\d{1,2})/(\d{1,2})', search_text)
                if date_match:
                    book_date = datetime.date(year, int(date_match.group(1)), int(date_match.group(2))).isoformat()
                    title = clean_title(block.select_one('h2 > .title').get_text())
                    author = block.select_one('h2 > .author').get_text(strip=True).replace('由 ', '').replace('◎著', '')
                    link = block.select_one('.book-block__link')['href']
                    if not link.startswith('http'): link = "https://www.kobo.com" + link
                    
                    books.append({
                        'summary': f"Kobo 99: {title}",
                        'description': f"作者：{author}\n傳送門：{link}\n(系統自動同步)",
                        'date': book_date
                    })
    except Exception as e:
        print(f"❌ Kobo 抓取失敗: {e}")
    return books

def get_pubu_books():
    """使用精準選擇器抓取 Pubu 99 選書"""
    scraper = cloudscraper.create_scraper(browser={'browser': 'chrome','platform': 'windows','desktop': True})
    url = "https://www.pubu.com.tw/campaign/event/pubu99select"
    
    books = []
    print(f"🔍 正在檢查 Pubu 99: {url}")
    try:
        time.sleep(random.uniform(2, 4))
        resp = scraper.get(url, timeout=30)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            book_blocks = soup.select('.in_book')
            current_year = datetime.datetime.now().year
            
            for block in book_blocks:
                link_tag = block.select_one('.container h2 a')
                desc_tag = block.select_one('.descript')
                
                if link_tag and desc_tag:
                    title = clean_title(link_tag.get_text())
                    link = link_tag.get('href', '')
                    if not link.startswith('http'): link = "https://www.pubu.com.tw" + link
                    
                    date_match = re.search(r'(\d{1,2})/(\d{1,2})', desc_tag.get_text())
                    if date_match:
                        book_date = datetime.date(current_year, int(date_match.group(1)), int(date_match.group(2))).isoformat()
                        books.append({
                            'summary': f"Pubu 99: {title}",
                            'description': f"來源：Pubu 99 選書\n連結：{link}\n(系統自動同步)",
                            'date': book_date
                        })
    except Exception as e:
        print(f"❌ Pubu 抓取失敗: {e}")
    return books

def get_calendar_service():
    """管理 Google API 憑證"""
    creds = None
    base_path = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(base_path, 'token.json')
    cred_file = os.path.join(base_path, 'credentials.json')

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(cred_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token: token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def is_event_exists(service, date, summary):
    """嚴格比對日期與標題，防止重複"""
    t_start, t_end = f"{date}T00:00:00Z", f"{date}T23:59:59Z"
    try:
        events = service.events().list(
            calendarId=CALENDAR_ID, 
            timeMin=t_start, 
            timeMax=t_end, 
            singleEvents=True
        ).execute().get('items', [])
        return any(event.get('summary', '').strip() == summary.strip() for event in events)
    except: return False

def sync_all():
    """同步所有來源書單"""
    all_books = get_kobo_books() + get_pubu_books()
    if not all_books:
        print("📭 沒有發現任何書單。")
        return

    try:
        service = get_calendar_service()
        print(f"📅 開始同步至 Google 行事曆...")
        for book in all_books:
            if is_event_exists(service, book['date'], book['summary']):
                print(f"⏭️ 跳過已存在: {book['date']} - {book['summary']}")
                continue
            
            # 設定結束日期 (開始日 +1)
            end_date = (datetime.date.fromisoformat(book['date']) + datetime.timedelta(days=1)).isoformat()
            
            event = {
                'summary': book['summary'],
                'description': book['description'],
                'start': {'date': book['date']},
                'end': {'date': end_date},
                'colorId': '5' if 'Kobo' in book['summary'] else '11', # Kobo 黃色, Pubu 紅色
                'transparency': 'transparent',
            }
            service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
            print(f"✅ 同步成功: {book['date']} - {book['summary']}")
            time.sleep(0.5)
        print("🎉 全部同步任務執行完畢！")
    except Exception as e:
        print(f"❌ 行事曆同步錯誤: {e}")

if __name__ == "__main__":
    sync_all()