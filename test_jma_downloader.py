#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA Downloader Test Script
1日分のデータのみをダウンロードしてテスト
"""

import pandas as pd
import requests

# 東京、2023年1月1日のデータを取得
url = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"
params = {
    "prec_no": "44",
    "block_no": "47662",
    "year": "2023",
    "month": "1",
    "day": "1",
    "view": "p1"
}

print("Testing JMA data download...")
print(f"URL: {url}")
print(f"Params: {params}")
print()

try:
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    print(f"Response status: {response.status_code}")
    print(f"Response encoding: {response.encoding}")
    print()

    # pandas read_html でテーブルをパース
    # エンコーディングを自動検出させる
    dfs = pd.read_html(response.text)

    print(f"Number of tables found: {len(dfs)}")
    print()

    if len(dfs) > 0:
        df = dfs[0]
        print(f"First table shape: {df.shape}")
        print(f"First table columns: {df.columns.tolist()}")
        print()
        print("First few rows:")
        print(df.head(10))
        print()

        # CSV保存
        output_file = "test_tokyo_2023_01_01.csv"
        df.to_csv(output_file, index=False, encoding="utf-8-sig")
        print(f"Data saved to: {output_file}")
    else:
        print("ERROR: No tables found")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
