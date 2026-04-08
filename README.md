# Apple 台灣整修品 Mac 監控

自動監控 [Apple 台灣整修品商店](https://www.apple.com/tw/shop/refurbished/mac)，偵測新上架、已下架、價格變動，即時寄送 Email 通知。

## 功能

- 每小時自動爬取 Apple 台灣整修品 Mac 頁面
- 比對上次快照，偵測新上架 / 已下架 / 價格變動
- 有變動才寄送 HTML 格式 Email 通知（含原價對照、省下金額）
- 記錄每次變動，分析 Apple 更新時段規律
- 支援 GitHub Actions 自動排程 + 本機手動執行

## 通知範例

Email 包含：
- 新上架商品清單（含原價、整修價、省下金額與折扣百分比）
- 已下架商品清單
- 價格變動商品清單
- Apple 更新規律分析（常見更新時段、星期）
- 目前全部商品總覽

## 設定 GitHub Actions

### 1. Fork 此 repo

### 2. 設定 Secrets

到 repo 的 **Settings → Secrets and variables → Actions**，新增以下 secrets：

| Secret | 說明 |
|--------|------|
| `GMAIL_USER` | Gmail 帳號（例如 `yourname@gmail.com`） |
| `GMAIL_APP_PASSWORD` | Gmail 應用程式密碼（非帳號密碼） |
| `TO_EMAIL` | 收件人 Email |

### 3. 取得 Gmail 應用程式密碼

1. 前往 [Google 帳號安全性](https://myaccount.google.com/security)
2. 啟用兩步驟驗證
3. 搜尋「應用程式密碼」，建立一組新的應用程式密碼
4. 將產生的 16 碼密碼填入 `GMAIL_APP_PASSWORD`

### 4. 啟用 Workflow

到 repo 的 **Actions** 頁籤，啟用 `Apple 整修品監控` workflow。

設定完成後會每小時整點自動執行，也可以手動觸發（workflow_dispatch）。

## 本機執行

```bash
pip install -r requirements.txt
python apple_refurb_monitor.py
```

本機環境會使用 `gws` CLI 寄信（需自行安裝設定），或設定環境變數 `GMAIL_APP_PASSWORD` 走 SMTP。

## 專案結構

```
├── apple_refurb_monitor.py   # 主程式（爬蟲、比對、寄信）
├── apple_refurb_daily.sh     # 本機 cron 用 shell script
├── requirements.txt          # Python 依賴
├── state/                    # 商品快照與變動紀錄
│   ├── apple_refurb_state.json
│   └── apple_refurb_changelog.json
└── .github/workflows/
    └── apple_refurb.yml      # GitHub Actions 排程設定
```

## 原價對照表

內建 Apple 台灣官方定價對照，涵蓋：

- iMac M4（24 吋）
- MacBook Air M4（13 吋 / 15 吋）
- MacBook Pro M4（14 吋 / 16 吋）
- MacBook Pro M3 Pro（14 吋，舊款整修品）
- Mac mini M4
- Mac Studio M4 Max / M4 Ultra / M3 Ultra

未收錄的規格會嘗試從 Apple 官網和 DuckDuckGo 搜尋定價。
