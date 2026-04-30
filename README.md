# **Kobo 每日 99 自動同步工具 (Kobo-99-Calendar-Sync)**

這是一個自動化 Python 腳本，能自動從 Kobo 官方網誌抓取「每週 99 元」特價書單，並將其精確地同步到你的 Google 行事曆中。

## **🌟 功能亮點**

* **全週自動同步**：一次執行即可抓取整週的特價資訊，並按日期填入行事曆。  
* **重複檢查機制**：具備嚴格的標題比對功能，重複執行腳本也不會產生重複事件。  
* **Cloudflare 繞過**：集成 cloudscraper，有效應對官方網誌的機器人防護。  
* **純淨書名解析**：自動清洗書名中的特殊字元與標點，確保在各種裝置上完美顯示。  
* **支援全天事件**：以全天行程方式呈現，不干擾你原有的作息排程。

## **🛠️ 安裝需求**

* Python 3.8+  
* Google Cloud Console 專案與相關憑證 (credentials.json)  
* 安裝必要套件：  
  `pip install cloudscraper beautifulsoup4 google-api-python-client google-auth-httplib2 google-auth-oauthlib`

## **🚀 快速開始**

### **1\. 取得 Google API 憑證**

1. 前往 Google Cloud Console 建立新專案。  
2. 啟用 **Google Calendar API**。  
3. 在「OAuth 同意畫面」設定測試使用者（填入你自己的 Gmail）。  
4. 在「憑證」建立一個 **OAuth 用戶端 ID**（類型選「電腦版應用程式」）。  
5. 下載 JSON 並重新命名為 credentials.json，放入專案目錄。

### **2\. 設定日曆 ID**

在腳本檔案中，找到 CALENDAR\_ID 變數，填入你的 Google 日曆 ID（可在 Google 日曆設定中的「整合日曆」區塊找到）。

### **3\. 首次執行**

第一次執行時會自動開啟瀏覽器要求授權：  
`python main.py`  
授權後，目錄下會生成 token.json，之後執行皆無需手動登入。

## **📅 NAS 自動化部署 (Synology)**

如果你想在 NAS 上每天自動運行：

1. 將 main.py、credentials.json、token.json 上傳到 NAS 資料夾。  
2. 開啟 **「控制台」 \> 「任務排程器」**。  
3. 新增一個「使用者定義的指令碼」：  
   * **帳號**：選擇你的使用者。  
   * **排程**：建議設定為「每天」。  
   * **執行指令**（範例路徑）：  
     `python3 /volume1/scripts/kobo99/main.py >> /volume1/scripts/kobo99/log.txt 2>&1`

## **📝 備註**

* 本腳本僅供個人學習與使用，請勿用於大規模抓取。  
* 書單資訊來源為 Kobo 台灣官方網誌。