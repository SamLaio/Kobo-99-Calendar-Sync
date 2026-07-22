# E-Book 特價自動同步工具

抓取 Kobo、Pubu、誠品線上的電子書特價清單，並同步成 Google Calendar 全天事件。

## 功能

- Kobo 每週 99 元書單
- Pubu 99 元精選/即時特價
- 誠品活動頁特價書單，預設抓 `CU202501-00235`
- 以書籍連結和清理後標題避免重複建立事件
- 依來源設定 Google Calendar 顏色：
  - Kobo: `colorId=5`
  - Pubu: `colorId=10`
  - 誠品: `colorId=11`
- 單站測試工具可輸出 TSV 到 `test/`

## 檔案

- `main.py`: 正式同步到 Google Calendar
- `kobo.py`: Kobo 單站抓取測試
- `pubu.py`: Pubu 單站抓取測試
- `eslite.py`: 誠品單站抓取測試
- `requirements.txt`: Python 套件

## 安裝

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Google Calendar 設定

1. 到 Google Cloud Console 啟用 Google Calendar API。
2. 建立 OAuth Desktop App 憑證。
3. 下載後命名為 `credentials.json`，放在專案根目錄。
4. 設定日曆 ID 環境變數。

PowerShell:

```powershell
$env:CALENDAR_ID="your_calendar_id@group.calendar.google.com"
python main.py
```

Linux/macOS:

```bash
CALENDAR_ID="your_calendar_id@group.calendar.google.com" python main.py
```

首次執行會開瀏覽器授權，成功後產生 `token.json`。`credentials.json`、`token.json` 已加入 `.gitignore`，不要提交。

## 誠品活動設定

預設只抓：

```text
CU202501-00235
```

要改抓其他誠品活動頁，用 `ESLITE_EXHIBITS` 覆蓋，多個用逗號分隔：

```powershell
$env:ESLITE_EXHIBITS="CU202501-00235,CU202502-00120"
$env:CALENDAR_ID="your_calendar_id@group.calendar.google.com"
python main.py
```

也可以填完整 URL：

```powershell
$env:ESLITE_EXHIBITS="https://www.eslite.com/exhibitions/CU202501-00235"
```

## 單站測試

這些指令不會寫入 Google Calendar，只會抓資料並輸出 TSV。若 `-o` 只給檔名，輸出會自動放到 `test/`。

```bash
python kobo.py -o kobo_test.tsv
python pubu.py -o pubu_test.tsv
python eslite.py -o eslite_test.tsv
```

誠品可指定活動頁：

```bash
python eslite.py https://www.eslite.com/exhibitions/CU202501-00235 -o eslite_test.tsv
```

## 排程

建議每天跑一次。Linux cron 範例：

```cron
0 8 * * * cd /path/to/Kobo-99-Calendar-Sync && CALENDAR_ID="your_calendar_id@group.calendar.google.com" /path/to/.venv/bin/python main.py >> sync.log 2>&1
```

Windows 工作排程器可執行：

```powershell
cd D:\github\Kobo-99-Calendar-Sync
$env:CALENDAR_ID="your_calendar_id@group.calendar.google.com"
.\.venv\Scripts\python.exe main.py
```

## 注意

- Kobo 可能檢查 TLS 指紋，建議安裝並保留 `curl_cffi`。
- 誠品價格 API 一次查太多商品可能漏資料，程式固定每 10 筆查一次。
- 不要提交 `credentials.json`、`token.json`、`test/`、`*.log`。
