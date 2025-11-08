#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA Downloader Test - 1週間分のデータをダウンロード
"""

import pandas as pd
import requests
from io import StringIO
import time

# 東京、2023年1月1日-7日のデータを取得
base_url = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"
prec_no = "44"
block_no = "47662"
year = 2023
month = 1

all_data = []

print("="*60)
print("Testing JMA data download for 1 week (2023/01/01 - 01/07)")
print("="*60)
print()

for day in range(1, 8):  # 1-7日
    params = {
        "prec_no": prec_no,
        "block_no": block_no,
        "year": year,
        "month": month,
        "day": day,
        "view": "p1"
    }

    try:
        print(f"Downloading {year}/{month:02d}/{day:02d}...", end=" ")

        response = requests.get(base_url, params=params, timeout=30)
        response.raise_for_status()

        # HTMLテーブルをパース
        dfs = pd.read_html(StringIO(response.text))

        if len(dfs) > 0:
            df = dfs[0]
            # 日付情報を追加
            df['年'] = year
            df['月'] = month
            df['日'] = day
            all_data.append(df)
            print(f"OK (rows: {len(df)})")
        else:
            print("WARN (No data)")

        # サーバー負荷軽減のため待機
        time.sleep(1.0)

    except Exception as e:
        print(f"ERROR: {e}")
        continue

# 全日のデータを結合
if all_data:
    combined_df = pd.concat(all_data, ignore_index=True)

    # CSV保存
    output_file = "test_tokyo_2023_01_week1.csv"
    combined_df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print()
    print("="*60)
    print(f"SUCCESS: Data saved to {output_file}")
    print(f"Total rows: {len(combined_df)} (expected: ~168 rows for 7 days × 24 hours)")
    print(f"Columns: {len(combined_df.columns)}")
    print("="*60)
    print()
    print("First few rows:")
    print(combined_df.head())
    print()
    print("Data summary:")
    print(combined_df.info())
else:
    print("ERROR: No data downloaded")
