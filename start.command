#!/bin/bash
# 雙擊此檔案即可啟動後台
cd "$(dirname "$0")"

echo "======================================"
echo "  宏福苑聽證會網站 — 編輯後台"
echo "======================================"
echo ""

# 檢查 Python3
if ! command -v python3 &> /dev/null; then
    echo "❌ 找不到 Python3，請先安裝：https://www.python.org"
    read -p "按 Enter 關閉..."
    exit 1
fi

# 安裝依賴
echo "📦 檢查並安裝所需套件..."
pip3 install -q flask pdfplumber jinja2

echo ""
echo "✅ 啟動後台中..."
echo "   瀏覽器將自動開啟 http://localhost:5001"
echo "   關閉此視窗即可停止後台"
echo ""

python3 admin.py
