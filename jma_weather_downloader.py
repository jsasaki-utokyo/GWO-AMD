#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA Weather Data Downloader
気象庁の過去の気象データ（etrn）サービスから時別値をCSVでダウンロードするツール

Usage:
    python jma_weather_downloader.py --year 2023 --station tokyo
    python jma_weather_downloader.py --year 2023 --station tokyo --prec_no 44 --block_no 47662
"""

import argparse
import datetime as dt
import time
from pathlib import Path
from calendar import monthrange
import requests
import pandas as pd
from io import StringIO

# 気象庁 etrn サービスのベースURL
# 時別値（hourly data）のエンドポイント
ETRN_BASE_URL = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"

# 主要観測地点の定義
# prec_no: 都道府県番号, block_no: 観測地点番号
STATIONS = {
    "tokyo": {
        "name": "東京",
        "prec_no": "44",
        "block_no": "47662"
    },
    "yokohama": {
        "name": "横浜",
        "prec_no": "46",
        "block_no": "47670"
    },
    "chiba": {
        "name": "千葉",
        "prec_no": "45",
        "block_no": "47682"
    },
    "osaka": {
        "name": "大阪",
        "prec_no": "62",
        "block_no": "47772"
    },
    "nagoya": {
        "name": "名古屋",
        "prec_no": "51",
        "block_no": "47636"
    },
    "fukuoka": {
        "name": "福岡",
        "prec_no": "82",
        "block_no": "47807"
    },
    "sapporo": {
        "name": "札幌",
        "prec_no": "14",
        "block_no": "47412"
    },
}


def download_daily_hourly_data(prec_no, block_no, year, month, day, timeout=30, retry=3):
    """
    気象庁のetrn サービスから1日分の時別値データをHTMLテーブルとしてダウンロード

    Parameters
    ----------
    prec_no : str
        都道府県番号
    block_no : str
        観測地点番号
    year : int
        年
    month : int
        月
    day : int
        日
    timeout : int
        タイムアウト時間（秒）
    retry : int
        リトライ回数

    Returns
    -------
    pd.DataFrame
        時別値データ
    """
    params = {
        "prec_no": prec_no,
        "block_no": block_no,
        "year": year,
        "month": month,
        "day": day,
        "view": "p1"  # データ表示モード
    }

    for attempt in range(retry):
        try:
            response = requests.get(ETRN_BASE_URL, params=params, timeout=timeout)
            response.raise_for_status()

            # pandas read_html でHTMLテーブルをパース
            # response.text を使用してエンコーディングの問題を回避
            dfs = pd.read_html(StringIO(response.text))

            if len(dfs) == 0:
                raise ValueError(f"No table found for {year}/{month}/{day}")

            # 最初のテーブルがデータテーブル
            df = dfs[0]

            # 日付情報を追加
            df['年'] = year
            df['月'] = month
            df['日'] = day

            return df

        except requests.exceptions.RequestException as e:
            if attempt < retry - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"[WARN] Request failed (attempt {attempt + 1}/{retry}): {e}")
                print(f"       Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                raise Exception(f"Failed to download data after {retry} attempts: {e}")
        except Exception as e:
            raise Exception(f"Error parsing data for {year}/{month}/{day}: {e}")


def download_yearly_data(prec_no, block_no, station_name, year, output_dir, delay=1.0):
    """
    指定された年の全月データをダウンロードして結合

    Parameters
    ----------
    prec_no : str
        都道府県番号
    block_no : str
        観測地点番号
    station_name : str
        観測地点名
    year : int
        年
    output_dir : str or Path
        出力ディレクトリ
    delay : float
        リクエスト間の待機時間（秒）気象庁サーバーへの負荷軽減のため
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_data = []

    print(f"\n{'='*60}")
    print(f"Downloading: {station_name} ({year})")
    print(f"Parameters: prec_no={prec_no}, block_no={block_no}")
    print(f"{'='*60}\n")

    # 1月から12月まで順次ダウンロード
    for month in range(1, 13):
        # 各月の日数を取得
        days_in_month = monthrange(year, month)[1]

        print(f"  Downloading {year}/{month:02d} (1-{days_in_month})...")

        month_data = []

        # 各日のデータをダウンロード
        for day in range(1, days_in_month + 1):
            try:
                df = download_daily_hourly_data(prec_no, block_no, year, month, day)

                if df is not None and len(df) > 0:
                    month_data.append(df)

                # サーバーへの負荷軽減のため待機（日ごと）
                time.sleep(delay)

            except Exception as e:
                print(f"    [WARN] {year}/{month:02d}/{day:02d}: {e}")
                continue

        # 月のデータを結合
        if month_data:
            month_df = pd.concat(month_data, ignore_index=True)
            all_data.append(month_df)
            print(f"    [{year}/{month:02d}] OK (rows: {len(month_df)})")
        else:
            print(f"    [{year}/{month:02d}] WARN (No data)")

    # 全月のデータを結合
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)

        # ファイル名の生成
        output_file = output_dir / f"{station_name}_{year}_hourly.csv"

        # CSV出力
        combined_df.to_csv(output_file, index=False, encoding="utf-8-sig")

        print(f"\n{'='*60}")
        print(f"SUCCESS: Data saved to {output_file}")
        print(f"Total rows: {len(combined_df)}")
        print(f"{'='*60}\n")

        return output_file
    else:
        print(f"\n{'='*60}")
        print(f"ERROR: No data downloaded for {station_name} ({year})")
        print(f"{'='*60}\n")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="気象庁の過去の気象データ（時別値）をダウンロード",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 東京の2023年データをダウンロード
  python jma_weather_downloader.py --year 2023 --station tokyo

  # 大阪の2020-2023年のデータをダウンロード
  python jma_weather_downloader.py --year 2020 2021 2022 2023 --station osaka

  # カスタム観測地点（都道府県番号と地点番号を指定）
  python jma_weather_downloader.py --year 2023 --prec_no 44 --block_no 47662 --name 東京

Available stations:
  tokyo, yokohama, chiba, osaka, nagoya, fukuoka, sapporo
        """
    )

    parser.add_argument(
        "--year",
        type=int,
        nargs="+",
        required=True,
        help="ダウンロード対象の年（複数指定可能）"
    )

    parser.add_argument(
        "--station",
        type=str,
        choices=list(STATIONS.keys()),
        help=f"観測地点名（{', '.join(STATIONS.keys())}）"
    )

    parser.add_argument(
        "--prec_no",
        type=str,
        help="都道府県番号（カスタム観測地点の場合）"
    )

    parser.add_argument(
        "--block_no",
        type=str,
        help="観測地点番号（カスタム観測地点の場合）"
    )

    parser.add_argument(
        "--name",
        type=str,
        help="観測地点名（カスタム観測地点の場合）"
    )

    parser.add_argument(
        "--output",
        type=str,
        default="jma_data",
        help="出力ディレクトリ（デフォルト: jma_data）"
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="リクエスト間の待機時間（秒）デフォルト: 1.0"
    )

    args = parser.parse_args()

    # 観測地点の設定
    if args.station:
        station_info = STATIONS[args.station]
        prec_no = station_info["prec_no"]
        block_no = station_info["block_no"]
        station_name = station_info["name"]
    elif args.prec_no and args.block_no and args.name:
        prec_no = args.prec_no
        block_no = args.block_no
        station_name = args.name
    else:
        parser.error("--station または (--prec_no, --block_no, --name) のセットを指定してください")

    # 各年についてダウンロード
    for year in args.year:
        try:
            download_yearly_data(
                prec_no=prec_no,
                block_no=block_no,
                station_name=station_name,
                year=year,
                output_dir=args.output,
                delay=args.delay
            )
        except Exception as e:
            print(f"\n[ERROR] Failed to download {station_name} ({year}): {e}\n")
            continue


if __name__ == "__main__":
    main()
