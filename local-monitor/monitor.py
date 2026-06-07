#!/usr/bin/env python3
"""
Apple Taiwan Mac Refurbished Monitor
監控 apple.com/tw/shop/refurbished/mac 所有整修品庫存

用法:
    python3 monitor.py              # 持續監控（每 10 秒）
    python3 monitor.py --once       # 只查一次當前狀態
    python3 monitor.py --interval 30  # 自訂間隔（秒）

不需安裝任何套件，只用 Python 標準庫。
"""

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────────────────────────────

REFURB_URL     = "https://www.apple.com/tw/shop/refurbished/mac"
BUYABILITY_API = "https://www.apple.com/tw/shop/buyability-message"

# （選填）Telegram 通知：填入後有貨時同步發 Telegram 訊息
TELEGRAM_TOKEN   = ""   # 例: "123456789:ABCdef..."
TELEGRAM_CHAT_ID = ""   # 例: "987654321"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,*/*",
}

# 產品清單每幾次 check 刷新一次（避免太頻繁抓整頁）
PRODUCT_LIST_REFRESH_EVERY = 60

# ── 路徑 ──────────────────────────────────────────────────────────────────────

BASE_DIR    = Path(__file__).parent
STATUS_FILE = BASE_DIR / "status.json"
LOG_FILE    = BASE_DIR / "monitor.log"


# ── 工具 ──────────────────────────────────────────────────────────────────────

def log(msg: str, also_print: bool = True):
    ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    if also_print:
        print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def fetch(url: str, extra_headers: dict = None) -> str:
    h   = {**HEADERS, **(extra_headers or {})}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8")


# ── 資料取得 ──────────────────────────────────────────────────────────────────

def get_products() -> dict:
    """從整修品頁面抓所有產品（含名稱/價格/SKU）"""
    html     = fetch(REFURB_URL)
    products = {}

    # 從 schema.org ld+json 取名稱、價格
    for raw in re.findall(
        r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL
    ):
        try:
            d = json.loads(raw)
            if d.get("@type") == "Product" and "offers" in d:
                for offer in d["offers"]:
                    sku = offer.get("sku", "")
                    if sku:
                        products[sku] = {
                            "name":     d.get("name", sku).replace("\xa0", " "),
                            "price":    offer.get("price", 0),
                            "currency": offer.get("priceCurrency", "TWD"),
                        }
        except Exception:
            pass

    # fallback：直接從 partNumber 撈 SKU
    for sku in re.findall(r'"partNumber"\s*:\s*"([^"]+)"', html):
        if sku not in products:
            products[sku] = {"name": sku, "price": 0, "currency": "TWD"}

    return products


def check_buyability(skus: list) -> dict:
    """一次查詢所有 SKU 的即時庫存（Apple 官方 API）"""
    params = "&".join(
        f"parts.{i}={urllib.parse.quote(s)}" for i, s in enumerate(skus)
    )
    url  = f"{BUYABILITY_API}?{params}"
    resp = fetch(url, extra_headers={"Accept": "application/json"})
    data = json.loads(resp)
    sth  = data["body"]["content"]["buyabilityMessage"]["sth"]
    return {sku: info.get("isBuyable", False) for sku, info in sth.items()}


# ── 通知 ──────────────────────────────────────────────────────────────────────

def notify_macos(title: str, message: str):
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], capture_output=True)
    for _ in range(3):
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        time.sleep(0.5)


def notify_telegram(message: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        return
    import json as _json
    url  = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    body = _json.dumps({
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"Telegram 通知失敗: {e}", also_print=False)


def notify(title: str, message: str):
    notify_macos(title, message)
    notify_telegram(f"<b>{title}</b>\n{message}")


def open_product_page(sku: str):
    slug = sku.lower().replace("/", "")
    url  = f"https://www.apple.com/tw/shop/product/{slug}"
    subprocess.Popen(["open", url])


# ── 狀態持久化 ────────────────────────────────────────────────────────────────

def load_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_status(status: dict):
    STATUS_FILE.write_text(
        json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── 單次查詢（--once 模式）───────────────────────────────────────────────────

def run_once():
    print("正在抓取產品清單...")
    products = get_products()
    print(f"共找到 {len(products)} 個整修品，查詢庫存中...\n")

    buyability = check_buyability(list(products.keys()))

    available   = [(s, products[s]) for s, b in buyability.items() if b]
    unavailable = [(s, products[s]) for s, b in buyability.items() if not b]

    print(f"✅ 可購買（{len(available)} 個）:")
    for sku, p in sorted(available, key=lambda x: x[1]["price"]):
        print(f"  {sku}  {int(p['price']):>7,} TWD  {p['name'][:55]}")

    print(f"\n❌ 無庫存（{len(unavailable)} 個）:")
    for sku, p in sorted(unavailable, key=lambda x: x[1]["price"]):
        print(f"  {sku}  {int(p['price']):>7,} TWD  {p['name'][:55]}")


# ── 持續監控主循環 ────────────────────────────────────────────────────────────

def run_monitor(interval: int):
    log("=" * 60)
    log("Apple 整修品 Mac 全品項監控啟動")
    log(f"監控頁面 : {REFURB_URL}")
    log(f"檢查間隔 : {interval} 秒")
    log(f"日誌檔案 : {LOG_FILE}")
    log("=" * 60)

    prev_status = load_status()
    products    = {}
    check_count = 0

    while True:
        check_count += 1
        try:
            # 定期刷新產品清單
            if check_count == 1 or check_count % PRODUCT_LIST_REFRESH_EVERY == 0:
                log("更新產品清單...")
                products = get_products()
                log(f"共 {len(products)} 個整修品")

            buyability = check_buyability(list(products.keys()))

            available_count   = sum(1 for b in buyability.values() if b)
            unavailable_count = sum(1 for b in buyability.values() if not b)

            # 偵測狀態變化
            for sku, is_buyable in buyability.items():
                prev = prev_status.get(sku)
                p    = products.get(sku, {})
                name = p.get("name", sku)
                price    = int(p.get("price", 0))
                currency = p.get("currency", "TWD")
                short    = name[:45]

                if prev is None:
                    if is_buyable:
                        log(f"🆕 新品上架且可購買: {sku} | {price:,} {currency} | {short}")
                        notify("Apple 整修品 - 新品上架！",
                               f"{short}\n{price:,} {currency}\nSKU: {sku}")
                        open_product_page(sku)
                elif prev is False and is_buyable:
                    log(f"✅ 庫存恢復: {sku} | {price:,} {currency} | {short}")
                    notify("Apple 整修品 - 有貨！",
                           f"{short}\n{price:,} {currency}\nSKU: {sku}")
                    open_product_page(sku)
                elif prev is True and not is_buyable:
                    log(f"❌ 售完: {sku} | {short}")

            prev_status = dict(buyability)
            save_status(prev_status)

            # 每 10 次輸出摘要
            if check_count % 10 == 0:
                log(f"第 {check_count} 次 | ✅ {available_count} 可買 | ❌ {unavailable_count} 無庫存")
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                print(
                    f"\r[{ts}] #{check_count} | ✅ {available_count} 可買 | ❌ {unavailable_count} 無庫存   ",
                    end="", flush=True,
                )

        except KeyboardInterrupt:
            print()
            log("監控已手動停止")
            break
        except Exception as e:
            log(f"⚠️  錯誤（繼續監控）: {e}")

        time.sleep(interval)


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Apple Taiwan Mac 整修品庫存監控")
    parser.add_argument("--once",     action="store_true", help="只查一次後退出")
    parser.add_argument("--interval", type=int, default=10, help="檢查間隔（秒，預設 10）")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_monitor(args.interval)


if __name__ == "__main__":
    main()
