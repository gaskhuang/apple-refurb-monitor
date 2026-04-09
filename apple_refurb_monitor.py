#!/usr/bin/env python3
"""
Apple 台灣整修品 Mac 即時監控
- 每小時爬取 https://www.apple.com/tw/shop/refurbished/mac
- 比對上次快照，偵測新上架 / 已下架商品
- 有變動才寄送 email 通知
- 記錄每次變動時間，分析 Apple 更新規律
"""

import requests
import json
import re
import os
import sys
import base64
import smtplib
import subprocess
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from collections import Counter

REFURB_URL = "https://www.apple.com/tw/shop/refurbished/mac"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "X-Apple-Store-Front": "446-1,32",  # 台灣 Apple Store front ID
}
COOKIES = {
    "geo": "TW",  # 強制台灣地區，避免 GitHub Actions 美國 IP 取得不完整庫存
}

# CI 環境偵測 — GitHub Actions 會設定 GITHUB_ACTIONS=true
IS_CI = os.environ.get("GITHUB_ACTIONS") == "true"

# 狀態檔案路徑
if IS_CI:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR = os.path.join(SCRIPT_DIR, "state")
else:
    DATA_DIR = os.path.expanduser("~/data")

STATE_FILE = os.path.join(DATA_DIR, "apple_refurb_state.json")
CHANGE_LOG_FILE = os.path.join(DATA_DIR, "apple_refurb_changelog.json")
REPORT_DIR = os.path.expanduser("~/reports") if not IS_CI else os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
TO_EMAIL = os.environ.get("TO_EMAIL", "")

# Apple 台灣官方原價對照表
# key: (model, screen, ram, storage) — model 使用 Apple API 回傳的格式 (無連字符)
ORIGINAL_PRICES = {
    # iMac M4 (24 吋)
    ("imac", "24inch", "16gb", "256gb"): {"price": 49900, "note": "iMac M4 10核心 16GB/256GB"},
    ("imac", "24inch", "16gb", "512gb"): {"price": 56900, "note": "iMac M4 10核心 16GB/512GB"},
    ("imac", "24inch", "24gb", "256gb"): {"price": 56900, "note": "iMac M4 10核心 24GB/256GB"},
    ("imac", "24inch", "24gb", "512gb"): {"price": 63900, "note": "iMac M4 10核心 24GB/512GB"},
    ("imac", "24inch", "24gb", "1tb"):   {"price": 70900, "note": "iMac M4 10核心 24GB/1TB"},
    ("imac", "24inch", "32gb", "512gb"): {"price": 70900, "note": "iMac M4 10核心 32GB/512GB"},
    ("imac", "24inch", "32gb", "1tb"):   {"price": 77900, "note": "iMac M4 10核心 32GB/1TB"},
    ("imac", "24inch", "32gb", "2tb"):   {"price": 91900, "note": "iMac M4 10核心 32GB/2TB"},
    # MacBook Air M4 (13 吋)
    ("macbookair", "13inch", "16gb", "256gb"):  {"price": 35900, "note": "MacBook Air 13 M4 16GB/256GB"},
    ("macbookair", "13inch", "16gb", "512gb"):  {"price": 41900, "note": "MacBook Air 13 M4 16GB/512GB"},
    ("macbookair", "13inch", "24gb", "256gb"):  {"price": 41900, "note": "MacBook Air 13 M4 24GB/256GB"},
    ("macbookair", "13inch", "24gb", "512gb"):  {"price": 47900, "note": "MacBook Air 13 M4 24GB/512GB"},
    ("macbookair", "13inch", "32gb", "512gb"):  {"price": 53900, "note": "MacBook Air 13 M4 32GB/512GB"},
    ("macbookair", "13inch", "32gb", "1tb"):    {"price": 59900, "note": "MacBook Air 13 M4 32GB/1TB"},
    ("macbookair", "13inch", "32gb", "2tb"):    {"price": 71900, "note": "MacBook Air 13 M4 32GB/2TB"},
    # MacBook Air M4 (15 吋)
    ("macbookair", "15inch", "16gb", "256gb"):  {"price": 41900, "note": "MacBook Air 15 M4 16GB/256GB"},
    ("macbookair", "15inch", "16gb", "512gb"):  {"price": 47900, "note": "MacBook Air 15 M4 16GB/512GB"},
    ("macbookair", "15inch", "16gb", "1tb"):    {"price": 53900, "note": "MacBook Air 15 M4 16GB/1TB"},
    ("macbookair", "15inch", "24gb", "256gb"):  {"price": 47900, "note": "MacBook Air 15 M4 24GB/256GB"},
    ("macbookair", "15inch", "24gb", "512gb"):  {"price": 53900, "note": "MacBook Air 15 M4 24GB/512GB"},
    ("macbookair", "15inch", "32gb", "512gb"):  {"price": 59900, "note": "MacBook Air 15 M4 32GB/512GB"},
    ("macbookair", "15inch", "32gb", "1tb"):    {"price": 65900, "note": "MacBook Air 15 M4 32GB/1TB"},
    ("macbookair", "15inch", "32gb", "2tb"):    {"price": 77900, "note": "MacBook Air 15 M4 32GB/2TB"},
    # MacBook Pro M4 (14 吋)
    ("macbookpro", "14inch", "16gb", "512gb"):  {"price": 54900, "note": "MacBook Pro 14 M4 16GB/512GB"},
    ("macbookpro", "14inch", "16gb", "1tb"):    {"price": 60900, "note": "MacBook Pro 14 M4 16GB/1TB"},
    ("macbookpro", "14inch", "24gb", "512gb"):  {"price": 64900, "note": "MacBook Pro 14 M4 Pro 24GB/512GB"},
    ("macbookpro", "14inch", "24gb", "1tb"):    {"price": 74900, "note": "MacBook Pro 14 M4 Pro 24GB/1TB"},
    ("macbookpro", "14inch", "48gb", "512gb"):  {"price": 109900, "note": "MacBook Pro 14 M4 Max 48GB/512GB"},
    ("macbookpro", "14inch", "48gb", "1tb"):    {"price": 119900, "note": "MacBook Pro 14 M4 Max 48GB/1TB"},
    # MacBook Pro M4 (16 吋)
    ("macbookpro", "16inch", "24gb", "512gb"):  {"price": 84900, "note": "MacBook Pro 16 M4 Pro 24GB/512GB"},
    ("macbookpro", "16inch", "36gb", "512gb"):  {"price": 104900, "note": "MacBook Pro 16 M4 Pro 36GB/512GB"},
    ("macbookpro", "16inch", "48gb", "512gb"):  {"price": 119900, "note": "MacBook Pro 16 M4 Max 48GB/512GB"},
    ("macbookpro", "16inch", "48gb", "1tb"):    {"price": 129900, "note": "MacBook Pro 16 M4 Max 48GB/1TB"},
    # MacBook Pro M3 Pro (14 吋) — 舊款整修品
    ("macbookpro", "14inch", "18gb", "512gb"):  {"price": 64900, "note": "MacBook Pro 14 M3 Pro 18GB/512GB"},
    # Mac mini M4
    ("macmini", "", "16gb", "256gb"):  {"price": 18900, "note": "Mac mini M4 16GB/256GB"},
    ("macmini", "", "16gb", "512gb"):  {"price": 24900, "note": "Mac mini M4 16GB/512GB"},
    ("macmini", "", "24gb", "512gb"):  {"price": 34900, "note": "Mac mini M4 Pro 24GB/512GB"},
    ("macmini", "", "24gb", "1tb"):    {"price": 44900, "note": "Mac mini M4 Pro 24GB/1TB"},
    ("macmini", "", "48gb", "512gb"):  {"price": 54900, "note": "Mac mini M4 Pro 48GB/512GB"},
    # Mac Studio
    ("macstudio", "", "32gb", "512gb"):   {"price": 63900, "note": "Mac Studio M4 Max 32GB/512GB"},
    ("macstudio", "", "64gb", "1tb"):     {"price": 94900, "note": "Mac Studio M4 Max 64GB/1TB"},
    ("macstudio", "", "96gb", "1tb"):     {"price": 119900, "note": "Mac Studio M4 Max 96GB/1TB"},
    ("macstudio", "", "128gb", "1tb"):    {"price": 129900, "note": "Mac Studio M4 Ultra 128GB/1TB"},
    ("macstudio", "", "192gb", "1tb"):    {"price": 189900, "note": "Mac Studio M4 Ultra 192GB/1TB"},
    # Mac Studio M3 Ultra — 舊款整修品
    ("macstudio", "", "192gb", "2tb"):    {"price": 219900, "note": "Mac Studio M3 Ultra 192GB/2TB"},
}
NANO_TEXTURE_PREMIUM = 7000

# 搜尋結果快取，避免重複查詢
_price_search_cache = {}


def search_original_price(title, model, ram, storage):
    """用 DuckDuckGo 搜尋 Apple 台灣官網真實定價"""
    cache_key = (model, ram, storage)
    if cache_key in _price_search_cache:
        return _price_search_cache[cache_key]

    # 先試 Apple 台灣官網搜尋
    price = _search_apple_tw(title, ram, storage)

    # Apple 官網沒找到再試 DuckDuckGo
    if not price:
        price = _search_duckduckgo(title)

    _price_search_cache[cache_key] = price
    return price


def _search_apple_tw(title, ram, storage):
    """直接搜尋 Apple 台灣商店，找原始定價"""
    try:
        # 用 Apple 台灣搜尋 API 找商品
        query = title.replace(" ", "+")
        url = f"https://www.apple.com/tw/search/{query}?tab=overview"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code != 200:
            return None

        # 找所有 NT$ 開頭的價格
        prices = re.findall(r'NT\$\s*([\d,]+)', r.text)
        valid = [int(p.replace(",", "")) for p in prices if int(p.replace(",", "")) >= 15000]
        if valid:
            # 回傳最常出現的價格（最可信）
            return Counter(valid).most_common(1)[0][0]
    except Exception as e:
        print(f"  Apple TW 搜尋失敗: {e}")
    return None


def _search_duckduckgo(title):
    """用 DuckDuckGo HTML 介面搜尋 Apple 台灣定價"""
    try:
        query = f"{title} Apple 台灣 定價 NT$ site:apple.com"
        url = "https://html.duckduckgo.com/html/"
        r = requests.post(
            url,
            data={"q": query},
            headers={**HEADERS, "Content-Type": "application/x-www-form-urlencoded"},
            timeout=15
        )
        if r.status_code != 200:
            return None

        # 找所有 NT$ 價格
        prices = re.findall(r'NT\$\s*([\d,]+)', r.text)
        valid = [int(p.replace(",", "")) for p in prices if int(p.replace(",", "")) >= 15000]
        if valid:
            return Counter(valid).most_common(1)[0][0]

        time.sleep(1)  # 避免被 rate limit
    except Exception as e:
        print(f"  DuckDuckGo 搜尋失敗: {e}")
    return None


def fetch_refurbished_products():
    """從 Apple 整修品頁面抓取所有 Mac 產品"""
    r = requests.get(REFURB_URL, headers=HEADERS, cookies=COOKIES, timeout=30)
    r.raise_for_status()

    matches = re.findall(
        r"window\.REFURB_GRID_BOOTSTRAP\s*=\s*(\{.*?\});", r.text, re.DOTALL
    )
    if not matches:
        raise ValueError("找不到 REFURB_GRID_BOOTSTRAP 資料")

    data = json.loads(matches[0])
    tiles = data.get("tiles", [])
    products = {}

    for tile in tiles:
        title = tile.get("title", "")
        price_info = tile.get("price", {})
        current = price_info.get("currentPrice", {})
        raw_amount = float(current.get("raw_amount", 0))
        display_price = current.get("amount", "")
        filters = tile.get("filters", {}).get("dimensions", {})
        detail_url = tile.get("productDetailsUrl", "")
        part_number = tile.get("partNumber", "")

        model = filters.get("refurbClearModel", "unknown")
        ram = filters.get("tsMemorySize", "")
        storage = filters.get("dimensionCapacity", "")
        color = filters.get("dimensionColor", "")
        year = filters.get("dimensionRelYear", "")
        screen = filters.get("dimensionScreensize", "")

        is_nano = "奈米紋理" in title or "nano" in title.lower()
        lookup_key = (model, screen, ram, storage)
        original_info = ORIGINAL_PRICES.get(lookup_key)

        if original_info:
            original_price = original_info["price"]
            price_source = "官方定價"
            if is_nano:
                original_price += NANO_TEXTURE_PREMIUM
        else:
            # 嘗試從網路搜尋真實定價
            print(f"  查詢網路定價: {title}")
            found_price = search_original_price(title, model, ram, storage)
            if found_price:
                original_price = found_price
                price_source = "網路查詢"
                print(f"    → 找到定價 NT${found_price:,}")
            else:
                # 完全找不到，標記為未知（不亂估算）
                original_price = 0
                price_source = "無法查詢"
                print(f"    → 無法查詢定價")

        if original_price > 0:
            savings = original_price - raw_amount
            savings_pct = (savings / original_price * 100) if original_price > 0 else 0
        else:
            savings = 0
            savings_pct = 0

        products[part_number] = {
            "title": title,
            "refurb_price": int(raw_amount),
            "refurb_display": display_price,
            "original_price": int(original_price),
            "savings": int(savings),
            "savings_pct": round(savings_pct, 1),
            "model": model,
            "ram": ram,
            "storage": storage,
            "color": color,
            "year": year,
            "screen": screen,
            "is_nano": is_nano,
            "price_source": price_source,
            "part_number": part_number,
            "detail_url": f"https://www.apple.com{detail_url.split('?')[0]}" if detail_url else "",
        }

    return products


def load_state():
    """讀取上次的商品快照"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"products": {}, "last_check": None, "last_change": None}


def save_state(state):
    """儲存目前的商品快照"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_changelog():
    """讀取變動紀錄"""
    if os.path.exists(CHANGE_LOG_FILE):
        with open(CHANGE_LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_changelog(changelog):
    """儲存變動紀錄"""
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CHANGE_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(changelog, f, ensure_ascii=False, indent=2)


def detect_changes(old_products, new_products):
    """比對新舊商品，找出變動"""
    old_keys = set(old_products.keys())
    new_keys = set(new_products.keys())

    added = new_keys - old_keys
    removed = old_keys - new_keys

    price_changed = []
    for key in old_keys & new_keys:
        if old_products[key]["refurb_price"] != new_products[key]["refurb_price"]:
            price_changed.append({
                "part_number": key,
                "title": new_products[key]["title"],
                "old_price": old_products[key]["refurb_price"],
                "new_price": new_products[key]["refurb_price"],
            })

    return {
        "added": [new_products[k] for k in added],
        "removed": [old_products[k] for k in removed],
        "price_changed": price_changed,
        "has_changes": len(added) > 0 or len(removed) > 0 or len(price_changed) > 0,
    }


def color_zh(color):
    mapping = {
        "silver": "銀色", "green": "綠色", "blue": "藍色",
        "pink": "粉紅色", "orange": "橙色", "purple": "紫色",
        "yellow": "黃色", "black": "太空黑色", "midnight": "午夜色",
        "starlight": "星光色", "gold": "金色",
    }
    return mapping.get(color, color)


def generate_change_email(changes, all_products, changelog):
    """產生變動通知 email (HTML)"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(all_products)

    added = changes["added"]
    removed = changes["removed"]
    price_changed = changes["price_changed"]

    summary_parts = []
    if added:
        summary_parts.append(f"新上架 {len(added)} 件")
    if removed:
        summary_parts.append(f"已下架 {len(removed)} 件")
    if price_changed:
        summary_parts.append(f"價格變動 {len(price_changed)} 件")
    summary_text = " | ".join(summary_parts)

    # 新上架區塊
    added_html = ""
    if added:
        added_rows = ""
        for p in sorted(added, key=lambda x: x["savings"], reverse=True):
            nano_badge = ' <span style="background:#ff9800;color:white;padding:1px 6px;border-radius:4px;font-size:11px;">奈米紋理</span>' if p["is_nano"] else ""
            source_badge = f' <span style="background:#9e9e9e;color:white;padding:1px 5px;border-radius:3px;font-size:10px;">{p["price_source"]}</span>'
            if p["original_price"] > 0:
                price_col = f'<span style="text-decoration:line-through;color:#999;">NT${p["original_price"]:,}</span><br><strong style="color:#e53935;font-size:16px;">NT${p["refurb_price"]:,}</strong>'
                savings_col = f'<span style="background:#4caf50;color:white;padding:4px 10px;border-radius:12px;font-weight:bold;">省 NT${p["savings"]:,}</span><br><span style="color:#4caf50;font-size:12px;">({p["savings_pct"]}% off)</span>'
            else:
                price_col = f'<strong style="color:#e53935;font-size:16px;">NT${p["refurb_price"]:,}</strong>'
                savings_col = '<span style="color:#999;font-size:12px;">定價未知</span>'

            added_rows += f"""
            <tr>
                <td style="padding:10px;border-bottom:1px solid #eee;">
                    <strong>{p['title']}</strong>{nano_badge}{source_badge}<br>
                    <span style="color:#666;font-size:12px;">{p['screen']} | {p['ram'].upper()} | {p['storage'].upper()} | {color_zh(p['color'])}</span>
                </td>
                <td style="padding:10px;border-bottom:1px solid #eee;text-align:right;white-space:nowrap;">{price_col}</td>
                <td style="padding:10px;border-bottom:1px solid #eee;text-align:center;">{savings_col}</td>
            </tr>"""

        added_html = f"""
        <div style="margin-bottom:20px;">
            <h2 style="color:#2e7d32;font-size:18px;margin:0 0 12px;">NEW 新上架 ({len(added)} 件)</h2>
            <div style="background:white;border-radius:8px;overflow:hidden;border:2px solid #4caf50;">
                <table style="width:100%;border-collapse:collapse;">
                    <thead><tr style="background:#e8f5e9;">
                        <th style="padding:10px;text-align:left;color:#2e7d32;">商品</th>
                        <th style="padding:10px;text-align:right;color:#2e7d32;">價格</th>
                        <th style="padding:10px;text-align:center;color:#2e7d32;">省下</th>
                    </tr></thead>
                    <tbody>{added_rows}</tbody>
                </table>
            </div>
        </div>"""

    # 已下架區塊
    removed_html = ""
    if removed:
        removed_items = ""
        for p in removed:
            removed_items += f"""
            <div style="padding:8px 12px;border-bottom:1px solid #eee;color:#999;">
                <span style="text-decoration:line-through;">{p['title']}</span>
                <span style="float:right;">NT${p['refurb_price']:,}</span>
            </div>"""

        removed_html = f"""
        <div style="margin-bottom:20px;">
            <h2 style="color:#c62828;font-size:18px;margin:0 0 12px;">SOLD 已下架 ({len(removed)} 件)</h2>
            <div style="background:#fff5f5;border-radius:8px;overflow:hidden;border:1px solid #ef9a9a;">
                {removed_items}
            </div>
        </div>"""

    # 價格變動區塊
    price_html = ""
    if price_changed:
        price_items = ""
        for p in price_changed:
            diff = p["new_price"] - p["old_price"]
            arrow = "↓" if diff < 0 else "↑"
            color = "#4caf50" if diff < 0 else "#e53935"
            price_items += f"""
            <div style="padding:8px 12px;border-bottom:1px solid #eee;">
                <strong>{p['title']}</strong><br>
                <span>NT${p['old_price']:,} → <strong style="color:{color};">NT${p['new_price']:,}</strong> ({arrow} NT${abs(diff):,})</span>
            </div>"""

        price_html = f"""
        <div style="margin-bottom:20px;">
            <h2 style="color:#e65100;font-size:18px;margin:0 0 12px;">PRICE 價格變動 ({len(price_changed)} 件)</h2>
            <div style="background:#fff8e1;border-radius:8px;overflow:hidden;border:1px solid #ffcc80;">
                {price_items}
            </div>
        </div>"""

    # 更新規律分析
    pattern_html = ""
    if len(changelog) >= 3:
        hours = [datetime.fromisoformat(c["time"]).hour for c in changelog[-20:]]
        hour_counts = {}
        for h in hours:
            hour_counts[h] = hour_counts.get(h, 0) + 1
        top_hours = sorted(hour_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        pattern_text = "、".join([f"{h}:00 ({c}次)" for h, c in top_hours])

        weekdays = [datetime.fromisoformat(c["time"]).strftime("%A") for c in changelog[-20:]]
        day_counts = {}
        for d in weekdays:
            day_counts[d] = day_counts.get(d, 0) + 1
        top_days = sorted(day_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        day_text = "、".join([f"{d} ({c}次)" for d, c in top_days])

        pattern_html = f"""
        <div style="margin-bottom:20px;padding:12px;background:#e3f2fd;border-radius:8px;font-size:13px;">
            <strong>Apple 更新規律分析</strong> (根據 {len(changelog)} 次變動紀錄)<br>
            <span>常見更新時段：{pattern_text}</span><br>
            <span>常見更新星期：{day_text}</span>
        </div>"""

    # 目前全部商品清單
    all_rows = ""
    for i, p in enumerate(sorted(all_products.values(), key=lambda x: x["savings"], reverse=True), 1):
        bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"
        nano_badge = ' <span style="background:#ff9800;color:white;padding:1px 4px;border-radius:3px;font-size:10px;">奈米</span>' if p["is_nano"] else ""
        if p["original_price"] > 0:
            price_cell = f'<span style="text-decoration:line-through;color:#bbb;font-size:11px;">NT${p["original_price"]:,}</span><br><strong style="color:#e53935;">NT${p["refurb_price"]:,}</strong>'
            savings_cell = f'-NT${p["savings"]:,}'
        else:
            price_cell = f'<strong style="color:#e53935;">NT${p["refurb_price"]:,}</strong>'
            savings_cell = "—"

        all_rows += f"""
        <tr style="background:{bg};">
            <td style="padding:6px 10px;border-bottom:1px solid #eee;font-size:13px;">
                {p['title']}{nano_badge}<br>
                <span style="color:#999;font-size:11px;">{p['ram'].upper()} | {p['storage'].upper()} | {color_zh(p['color'])}</span>
            </td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:right;font-size:13px;white-space:nowrap;">{price_cell}</td>
            <td style="padding:6px 10px;border-bottom:1px solid #eee;text-align:center;font-size:12px;color:#4caf50;font-weight:bold;">{savings_cell}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:800px;margin:0 auto;padding:20px;background:#f5f5f5;">

<div style="background:linear-gradient(135deg,#0071e3,#34c759);padding:24px;border-radius:12px;margin-bottom:20px;">
    <h1 style="margin:0;font-size:22px;color:#ffffff;">Apple 整修品 Mac 變動通知</h1>
    <p style="margin:8px 0 0;color:#e0f0ff;font-size:14px;">{now} | {summary_text} | 目前共 {total} 件</p>
</div>

{added_html}
{removed_html}
{price_html}
{pattern_html}

<details style="margin-bottom:20px;">
    <summary style="cursor:pointer;font-size:16px;font-weight:bold;color:#333;padding:12px;background:white;border-radius:8px;">
        目前全部商品清單 ({total} 件)
    </summary>
    <div style="background:white;border-radius:0 0 8px 8px;overflow:hidden;">
        <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#eee;">
                <th style="padding:8px;text-align:left;font-size:12px;">商品</th>
                <th style="padding:8px;text-align:right;font-size:12px;">價格</th>
                <th style="padding:8px;text-align:center;font-size:12px;">省下</th>
            </tr></thead>
            <tbody>{all_rows}</tbody>
        </table>
    </div>
</details>

<div style="text-align:center;color:#999;font-size:11px;">
    <p>資料來源：<a href="{REFURB_URL}" style="color:#1976d2;">Apple 台灣整修品商店</a></p>
    <p>每小時自動偵測 | 有變動才通知 | OpenClaw Agent</p>
</div>

</body>
</html>"""
    return html, summary_text


def send_email_smtp(html_body, subject):
    """透過 Gmail SMTP 寄送 HTML email（GitHub Actions 用）"""
    smtp_user = os.environ.get("GMAIL_USER")
    smtp_pass = os.environ.get("GMAIL_APP_PASSWORD")

    if not smtp_user or not smtp_pass:
        print("  SMTP 憑證未設定，跳過寄信")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = smtp_user
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, TO_EMAIL, msg.as_string())
        print(f"  SMTP Email 寄送成功！→ {TO_EMAIL}")
        return True
    except Exception as e:
        print(f"  SMTP Email 寄送失敗: {e}")
        return False


def send_email_gws(html_body, subject):
    """透過 gws CLI 寄送 HTML email（本機用）"""
    msg = MIMEMultipart("alternative")
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload = json.dumps({"raw": raw})

    result = subprocess.run(
        ["gws", "gmail", "users", "messages", "send",
         "--params", '{"userId": "me"}', "--json", payload],
        capture_output=True, text=True
    )

    if '"SENT"' in result.stdout:
        msg_id = json.loads(result.stdout).get("id", "unknown")
        print(f"  gws Email 寄送成功! ID: {msg_id}")
        return True
    else:
        print(f"  gws Email 寄送失敗: {result.stdout} {result.stderr}")
        return False


def send_email(html_body, subject):
    """自動選擇寄信方式：CI 用 SMTP，本機用 gws"""
    if IS_CI or os.environ.get("GMAIL_APP_PASSWORD"):
        return send_email_smtp(html_body, subject)
    else:
        return send_email_gws(html_body, subject)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M:%S")

    print(f"[{now.strftime('%H:%M:%S')}] 開始爬取 Apple 整修品...")
    print(f"  環境: {'GitHub Actions (CI)' if IS_CI else '本機'}")

    try:
        current_products = fetch_refurbished_products()
    except Exception as e:
        print(f"ERROR: 爬取失敗 - {e}")
        sys.exit(1)

    print(f"[{now.strftime('%H:%M:%S')}] 找到 {len(current_products)} 件整修品")

    state = load_state()
    old_products = state.get("products", {})
    is_first_run = state.get("last_check") is None

    changes = detect_changes(old_products, current_products)

    if changes["has_changes"] or is_first_run:
        state["products"] = current_products
        state["last_check"] = now_str
        state["last_change"] = now_str
        save_state(state)
    else:
        # 無變動時不更新 state 檔案，避免不必要的 git commit
        pass

    if is_first_run:
        print(f"[{now.strftime('%H:%M:%S')}] 首次執行，記錄初始狀態 ({len(current_products)} 件商品)")
        print("  不寄送通知 (等待下次變動)")
        changelog = load_changelog()
        changelog.append({
            "time": now.isoformat(),
            "type": "init",
            "total": len(current_products),
            "added": len(current_products),
            "removed": 0,
        })
        save_changelog(changelog)
        return

    if not changes["has_changes"]:
        print(f"[{now.strftime('%H:%M:%S')}] 無變動，跳過通知")
        last_change = state.get("last_change", "未知")
        print(f"  上次變動: {last_change}")
        return

    print(f"[{now.strftime('%H:%M:%S')}] 偵測到變動!")
    print(f"  新上架: {len(changes['added'])} 件")
    for p in changes["added"]:
        savings_str = f"省 NT${p['savings']:,}" if p["savings"] > 0 else "定價未知"
        print(f"    + {p['title']} → NT${p['refurb_price']:,} ({savings_str})")
    print(f"  已下架: {len(changes['removed'])} 件")
    for p in changes["removed"]:
        print(f"    - {p['title']}")
    print(f"  價格變動: {len(changes['price_changed'])} 件")
    for p in changes["price_changed"]:
        print(f"    ~ {p['title']}: NT${p['old_price']:,} → NT${p['new_price']:,}")

    changelog = load_changelog()
    changelog.append({
        "time": now.isoformat(),
        "type": "change",
        "total": len(current_products),
        "added": len(changes["added"]),
        "removed": len(changes["removed"]),
        "price_changed": len(changes["price_changed"]),
        "added_items": [p["part_number"] for p in changes["added"]],
        "removed_items": [p["part_number"] for p in changes["removed"]],
    })
    save_changelog(changelog)

    html, summary = generate_change_email(changes, current_products, changelog)

    ts = now.strftime("%Y%m%d_%H%M")
    report_path = os.path.join(REPORT_DIR, f"apple_refurb_change_{ts}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  報告已儲存: {report_path}")

    subject = f"Apple 整修品變動通知 ({now.strftime('%m/%d %H:%M')}) - {summary}"
    send_email(html, subject)


if __name__ == "__main__":
    main()
