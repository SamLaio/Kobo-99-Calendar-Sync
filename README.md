# 📚 電子書 99 元特價自動同步工具 (E-Book-99-Sync)

這是一個專為電子書愛好者開發的自動化 Python 腳本。它能自動抓取 **Kobo (每週 99)** 與 **Pubu (精選 99)** 的特價書單，並將其精確地同步到你的 Google 行事曆中。

## **🌟 功能亮點**

*   **雙平台整合同步**：
    *   **Kobo**：自動抓取官方網誌的每週蟬聯特價書單。[cite: 1]
    *   **Pubu**：精準解析 Pubu 99 選書頁面，獲取全月特價清單。[cite: 1]
*   **視覺化標記**：
    *   🟡 **Kobo** 事件自動設為黃色 (`colorId: 5`)。[cite: 1]
    *   🔴 **Pubu** 事件自動設為番茄紅 (`colorId: 11`)。[cite: 1]
*   **智慧去重機制**：透過嚴格的書名清洗與日期比對，確保行事曆中不會出現重複的事件。[cite: 1]
*   **Cloudflare 繞過**：使用 `cloudscraper` 模擬真實瀏覽器行為，穩定抓取數據。[cite: 1]
*   **精準選擇器解析**：針對 Pubu 的特殊結構（`.in_book` 容器），實作了精準的 CSS 選擇器解析，確保抓取內容無雜訊。[cite: 1]

## **🛠️ 安裝需求**

*   **Python 3.8+**
*   **Google Cloud Console 憑證** (`credentials.json`)[cite: 1]
*   **必要套件安裝**：
    ```bash
    pip install cloudscraper beautifulsoup4 google-api-python-client google-auth-httplib2 google-auth-oauthlib
    ```

## **🚀 快速開始**

### **1. 準備 Google API 憑證**
1.  前往 [Google Cloud Console](https://console.cloud.google.com/) 建立專案。[cite: 1]
2.  啟用 **Google Calendar API**。[cite: 1]
3.  在「憑證」頁面建立一個 **OAuth 用戶端 ID**（類型：電腦版應用程式）。[cite: 1]
4.  下載 JSON 檔案並重新命名為 `credentials.json`，放入腳本目錄。[cite: 1]

### **2. 設定日曆 ID**
在腳本中修改 `CALENDAR_ID` 變數：
```python
CALENDAR_ID = '你的日曆ID@group.calendar.google.com'
```

### **3. 首次執行授權**
第一次執行時會開啟瀏覽器要求授權 Google 日曆權限：
```bash
python main.py
```
授權後產生的 `token.json` 將供日後自動化使用。[cite: 1]

## **📅 NAS 自動化部署 (Synology)**

1.  將 `main.py`、`credentials.json`、`token.json` 上傳至 NAS 資料夾（如 `/volume1/scripts/kobo_pubu/`）。[cite: 1]
2.  進入 **「控制台」 > 「任務排程器」**。[cite: 1]
3.  新增「使用者定義的指令碼」：
    *   **排程**：建議設定為每日凌晨 03:00 執行。[cite: 1]
    *   **指令範例**：
        ```bash
        python3 /volume1/scripts/kobo_pubu/main.py >> /volume1/scripts/kobo_pubu/log.txt 2>&1
        ```

## **📝 說明與限制**

*   **書名清洗**：腳本會自動移除書名中的特殊符號，以提升行事曆比對的準確度。[cite: 1]
*   **日期過濾**：自動從網頁文字中提取 `MM/DD` 格式日期，排除「限定」、「下架」等無關字眼。[cite: 1]
*   **免責聲明**：本工具僅供個人學術研究與讀書筆記使用，請尊重平台版權。[cite: 1]
```
