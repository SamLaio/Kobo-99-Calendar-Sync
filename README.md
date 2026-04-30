## 📚 E-Book 99 特價自動同步工具

這是一個自動化 Python 腳本，專門抓取 **Pubu** 與 **Kobo** 的 99 元限時特價書單，並自動同步至 **Google 日曆**。透過顏色區分與標題優化，讓你一眼掌握每日特價資訊。

### ✨ 主要功能
*   **多平台支援**：同時監控 Pubu 一日 99/即時 99 以及 Kobo 每週 99 書單。
*   **智能分類標籤**：
    *   `pubu一日99`：當日限定特價書籍。
    *   `pubu即時99`：即將下架的限時特價書籍（由區塊內的 `~` 符號自動判定）。
    *   `kobo99`：Kobo 每週更換的特價書單。
*   **視覺優化**：
    *   **自動去符號化**：移除標題中的《 》、[ ]、( ) 等符號，保持日曆介面整潔。
    *   **顏色區分**：Pubu 使用 **青綠色 (Basil)**，Kobo 使用 **藍色**。
*   **防重複機制**：採用「無符號純文字」比對技術，即使網頁標題微調或空格變動，也不會重複寫入日曆。

### 🛠️ 環境需求
*   Python 3.x
*   Google Calendar API 憑證 (`credentials.json`)
*   必要套件：
    ```bash
    pip install cloudscraper beautifulsoup4 google-api-python-client google-auth-oauthlib
    ```

### 🚀 安裝與設定
1.  **取得 Google API 憑證**：
    *   前往 [Google Cloud Console](https://console.cloud.google.com/)。
    *   啟用 Google Calendar API。
    *   下載 OAuth 2.0 憑證，並將其更名為 `credentials.json` 放置於腳本目錄。
2.  **設定日曆 ID**：
    *   在 `main.py` 中填入你的 `CALENDAR_ID`（通常是 Google 帳號或特定的日曆 ID）。
3.  **執行同步**：
```bash
    python main.py
```

* 首次執行會開啟瀏覽器進行身份驗證，成功後會生成 `token.json`。

### 📂 程式邏輯說明
*   **`clean_title_display`**：負責美化標題，移除礙眼的書名號與括號。
*   **`clean_for_compare`**：核心去重邏輯，將標題轉為純文字後比對 Google 日曆現有事件。
*   **`get_pubu_books`**：
    *   透過 `~` 或 `～` 符號判定是否為「即時（即將下架）」特價。
    *   自動處理 Pubu 的網址拼接問題，防止網址重複疊加。
*   **`get_kobo_books`**：
    *   自動計算當前週數並嘗試獲取正確的 Blog URL。
    *   具備回溯機制，確保能正確抓取日期區塊內的書籍。

### 📝 備註
*   本腳本建議配合 `crontab` 或 NAS 的任務排程器使用（建議每日執行一次）。
*   同步時會將「原始完整書名」存放在日曆事件的「說明」欄位中，方便備查。
