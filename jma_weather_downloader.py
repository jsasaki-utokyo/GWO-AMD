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
import numpy as np
from io import StringIO

# 気象庁 etrn サービスのベースURL
# 時別値（hourly data）のエンドポイント
ETRN_BASE_URL = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"

# 主要観測地点の定義
# prec_no: 都道府県番号, block_no: 観測地点番号
# name: 日本語名, name_en: 英語名（ディレクトリ名とファイル名に使用）
STATIONS = {
    "tokyo": {
        "name": "東京",
        "name_en": "Tokyo",
        "prec_no": "44",
        "block_no": "47662"
    },
    "yokohama": {
        "name": "横浜",
        "name_en": "Yokohama",
        "prec_no": "46",
        "block_no": "47670"
    },
    "chiba": {
        "name": "千葉",
        "name_en": "Chiba",
        "prec_no": "45",
        "block_no": "47682"
    },
    "osaka": {
        "name": "大阪",
        "name_en": "Osaka",
        "prec_no": "62",
        "block_no": "47772"
    },
    "nagoya": {
        "name": "名古屋",
        "name_en": "Nagoya",
        "prec_no": "51",
        "block_no": "47636"
    },
    "fukuoka": {
        "name": "福岡",
        "name_en": "Fukuoka",
        "prec_no": "82",
        "block_no": "47807"
    },
    "sapporo": {
        "name": "札幌",
        "name_en": "Sapporo",
        "prec_no": "14",
        "block_no": "47412"
    },
}

# Wind direction mapping for GWO format conversion
WIND_DIR_MAP = {
    '北': 16, '北北東': 1, '北東': 2, '東北東': 3,
    '東': 4, '東南東': 5, '南東': 6, '南南東': 7,
    '南': 8, '南南西': 9, '南西': 10, '西南西': 11,
    '西': 12, '西北西': 13, '北西': 14, '北北西': 15,
    '静穏': 0, 'Calm': 0,
}

# Station ID mapping for GWO format
STATION_ID_MAP = {
    'Tokyo': '662', 'Yokohama': '671', 'Chiba': '682',
    'Osaka': '772', 'Nagoya': '636', 'Fukuoka': '807', 'Sapporo': '412',
}


def convert_to_gwo_format(df_jma, station_name_en, station_name_jp):
    """
    Convert JMA DataFrame to GWO format (33 columns, no header)

    Parameters
    ----------
    df_jma : pd.DataFrame
        DataFrame from JMA (with headers)
    station_name_en : str
        English station name
    station_name_jp : str
        Japanese station name

    Returns
    -------
    pd.DataFrame
        GWO-formatted DataFrame
    """
    station_id = STATION_ID_MAP.get(station_name_en, '999')

    gwo_rows = []

    for idx, row in df_jma.iterrows():
        try:
            # Extract date/time (columns may vary, try different positions)
            year = int(row.iloc[-3]) if len(row) > 17 else None
            month = int(row.iloc[-2]) if len(row) > 18 else None
            day = int(row.iloc[-1]) if len(row) > 19 else None
            hour = int(row.iloc[0])

            if year is None or month is None or day is None:
                continue

            # Helper functions
            def to_float(val):
                if pd.isna(val) or val == '--' or val == '' or val == '×':
                    return None
                try:
                    return float(str(val).replace('−', '-'))
                except:
                    return None

            def to_int_scaled(val, scale=10):
                fval = to_float(val)
                return int(fval * scale) if fval is not None else None

            def rmk(val):
                return 8 if val is not None else 1

            # Parse wind direction
            def wind_dir_code(text):
                if pd.isna(text) or text == '--' or text == '':
                    return 0
                return WIND_DIR_MAP.get(str(text).strip(), 0)

            # Parse cloud cover
            def parse_cloud(cloud_str):
                if pd.isna(cloud_str) or cloud_str == '' or cloud_str == '--':
                    return None
                try:
                    cloud_str = str(cloud_str).replace('+', '').replace('-', '').replace('−', '')
                    val = float(cloud_str)
                    return int(val) if 0 <= val <= 10 else None
                except:
                    return None

            # Extract values (positions based on JMA format)
            local_pressure = to_int_scaled(row.iloc[1], 10)  # hPa -> 0.1hPa
            sea_pressure = to_int_scaled(row.iloc[2], 10)
            temp = to_int_scaled(row.iloc[4], 10)  # °C -> 0.1°C
            dew_point = to_int_scaled(row.iloc[5], 10)
            vapor_pressure = to_int_scaled(row.iloc[6], 10)
            humidity = to_int_scaled(row.iloc[7], 1)  # % (no scaling)
            wind_speed = to_int_scaled(row.iloc[8], 10)  # m/s -> 0.1m/s
            wind_dir = wind_dir_code(row.iloc[9])
            sunshine = to_int_scaled(row.iloc[10], 10) if len(row) > 10 else None
            solar = to_int_scaled(row.iloc[11], 100) if len(row) > 11 else None  # MJ/m² -> 0.01MJ/m²
            precip = to_int_scaled(row.iloc[3], 10) if len(row) > 3 else None
            cloud = parse_cloud(row.iloc[15]) if len(row) > 15 else None

            # Build GWO row (33 columns)
            gwo_row = [
                station_id, station_name_jp, station_id,  # 1-3
                year, month, day, hour,  # 4-7
                local_pressure, rmk(local_pressure),  # 8-9
                sea_pressure, rmk(sea_pressure),  # 10-11
                temp, rmk(temp),  # 12-13
                vapor_pressure, rmk(vapor_pressure),  # 14-15
                humidity, rmk(humidity),  # 16-17
                wind_dir, rmk(wind_dir) if wind_dir > 0 else 1,  # 18-19
                wind_speed, rmk(wind_speed),  # 20-21
                cloud, 2 if cloud is None else 8,  # 22-23 (RMK=2 for not observed)
                0, 2,  # 24-25 (weather code not available)
                dew_point, rmk(dew_point),  # 26-27
                sunshine, 2 if sunshine is None else 8,  # 28-29
                solar, 2 if solar is None else 8,  # 30-31
                precip, 2 if precip is None else 8,  # 32-33 (RMK=2 for not observed)
            ]

            gwo_rows.append(gwo_row)

        except Exception as e:
            print(f"Warning: Skipping row {idx}: {e}")
            continue

    gwo_df = pd.DataFrame(gwo_rows)

    # Interpolate cloud cover
    if len(gwo_df) > 0:
        gwo_df[21] = gwo_df[21].replace({None: np.nan}).interpolate(method='linear').round().clip(0, 10).fillna(0).astype(int)
        # Update RMK for interpolated values (keep as 2 if originally not observed)
        # Actually, keep cloud RMK as 2 since original data didn't have it

    # Replace None with 0 for missing data columns (sunshine, solar, precip)
    # Columns 27, 29, 31 are sunshine, solar, precip values
    for col in [27, 29, 31]:
        gwo_df[col] = gwo_df[col].fillna(0)

    # Ensure integer types for all numeric columns
    int_columns = [0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]
    for col in int_columns:
        if col in gwo_df.columns:
            gwo_df[col] = gwo_df[col].fillna(0).astype(int)

    # Calculate missing value statistics
    # Missing values are indicated by RMK code = 1 (missing) or 2 (not observed)
    total_rows = len(gwo_df)

    # Count original cloud observations (before interpolation)
    cloud_original_missing = sum(1 for idx, row in df_jma.iterrows()
                                 if len(row) > 15 and (pd.isna(row.iloc[15]) or str(row.iloc[15]).strip() in ['', '--']))

    # RMK column mapping (0-indexed):
    # Col 9 (idx 8): Local pressure RMK, Col 11 (idx 10): Sea pressure RMK
    # Col 13 (idx 12): Temperature RMK, Col 15 (idx 14): Vapor pressure RMK
    # Col 17 (idx 16): Humidity RMK, Col 19 (idx 18): Wind dir RMK
    # Col 21 (idx 20): Wind speed RMK, Col 23 (idx 22): Cloud RMK
    # Col 25 (idx 24): Weather RMK, Col 27 (idx 26): Dew point RMK
    # Col 29 (idx 28): Sunshine RMK, Col 31 (idx 30): Solar RMK
    # Col 33 (idx 32): Precipitation RMK

    stats = {
        'total_rows': total_rows,
        'pressure': (gwo_df[8] == 1).sum(),  # RMK=1 means missing
        'temperature': (gwo_df[12] == 1).sum(),
        'humidity': (gwo_df[16] == 1).sum(),
        'wind_speed': (gwo_df[20] == 1).sum(),
        'dew_point': (gwo_df[26] == 1).sum(),
        'sunshine': (gwo_df[28] == 2).sum(),  # RMK=2 means not observed
        'solar': (gwo_df[30] == 2).sum(),
        'precipitation': (gwo_df[32] == 2).sum(),
        'cloud_original': cloud_original_missing,
    }

    return gwo_df, stats


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


def download_yearly_data(prec_no, block_no, station_name, station_name_en, year, output_dir, delay=1.0, gwo_format=False):
    """
    指定された年の全月データをダウンロードして結合
    GWO/AMD互換のディレクトリ構造で保存: {output_dir}/{StationName}/{StationName}{Year}.csv

    Parameters
    ----------
    prec_no : str
        都道府県番号
    block_no : str
        観測地点番号
    station_name : str
        観測地点名（日本語、表示用）
    station_name_en : str
        観測地点名（英語、ディレクトリ名とファイル名に使用）
    year : int
        年
    output_dir : str or Path
        出力ディレクトリ（ベースディレクトリ）
    delay : float
        リクエスト間の待機時間（秒）気象庁サーバーへの負荷軽減のため
    gwo_format : bool
        True の場合、GWO 形式（33列、ヘッダーなし）に変換して保存
    """
    output_dir = Path(output_dir)

    # GWO互換のディレクトリ構造: {output_dir}/{StationName}/
    station_dir = output_dir / station_name_en
    station_dir.mkdir(parents=True, exist_ok=True)

    all_data = []

    print(f"\n{'='*60}")
    print(f"Downloading: {station_name} / {station_name_en} ({year})")
    print(f"Parameters: prec_no={prec_no}, block_no={block_no}")
    print(f"Output: {station_dir}")
    print(f"Format: {'GWO (33 columns, no header)' if gwo_format else 'JMA (with headers)'}")
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

        # GWO形式に変換する場合
        missing_stats = None
        if gwo_format:
            print("Converting to GWO format (33 columns, no header)...")
            combined_df, missing_stats = convert_to_gwo_format(combined_df, station_name_en, station_name)
            encoding = "utf-8"  # GWO format uses UTF-8 without BOM
            header = False
            index = False
        else:
            encoding = "utf-8-sig"  # JMA format uses UTF-8 with BOM
            header = True
            index = False

        # GWO互換のファイル名: {StationName}{Year}.csv
        output_file = station_dir / f"{station_name_en}{year}.csv"

        # CSV出力
        combined_df.to_csv(output_file, header=header, index=index, encoding=encoding)

        print(f"\n{'='*60}")
        print(f"SUCCESS: Data saved to {output_file}")
        print(f"Total rows: {len(combined_df)}")
        if gwo_format:
            print(f"Format: GWO (33 columns, cloud cover interpolated)")

            # Display missing value statistics
            if missing_stats:
                print(f"\nData Quality Report:")
                total = missing_stats['total_rows']

                # Core parameters (should have very few missing)
                core_missing = []
                if missing_stats['pressure'] > 0:
                    core_missing.append(f"  Pressure: {missing_stats['pressure']}/{total} missing ({missing_stats['pressure']*100/total:.1f}%)")
                if missing_stats['temperature'] > 0:
                    core_missing.append(f"  Temperature: {missing_stats['temperature']}/{total} missing ({missing_stats['temperature']*100/total:.1f}%)")
                if missing_stats['humidity'] > 0:
                    core_missing.append(f"  Humidity: {missing_stats['humidity']}/{total} missing ({missing_stats['humidity']*100/total:.1f}%)")

                if core_missing:
                    print("  Core Parameters (unexpected missing):")
                    for msg in core_missing:
                        print(msg)

                # Optional parameters (may have missing values)
                print("  Optional Parameters:")
                print(f"  Sunshine: {missing_stats['sunshine']}/{total} not observed ({missing_stats['sunshine']*100/total:.1f}%)")
                print(f"  Solar radiation: {missing_stats['solar']}/{total} not observed ({missing_stats['solar']*100/total:.1f}%)")
                print(f"  Precipitation: {missing_stats['precipitation']}/{total} not observed ({missing_stats['precipitation']*100/total:.1f}%)")

                # Cloud cover interpolation report
                cloud_orig_missing = missing_stats['cloud_original']
                cloud_coverage = (total - cloud_orig_missing) * 100 / total
                print(f"  Cloud cover: {total - cloud_orig_missing}/{total} observed ({cloud_coverage:.1f}%), rest interpolated")

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
  # 東京の2023年データをダウンロード（JMA形式: jma_data/Tokyo/Tokyo2023.csv）
  python jma_weather_downloader.py --year 2023 --station tokyo

  # 東京の2021年データをGWO形式に変換してダウンロード（33列、雲量補間あり）
  python jma_weather_downloader.py --year 2021 --station tokyo --gwo-format

  # 大阪の2020-2023年のデータをダウンロード
  python jma_weather_downloader.py --year 2020 2021 2022 2023 --station osaka

  # カスタム観測地点（都道府県番号と地点番号を指定）
  python jma_weather_downloader.py --year 2023 --prec_no 44 --block_no 47662 --name 東京 --name_en Tokyo

  # 出力ディレクトリを指定してGWO形式に変換（$DATA_DIR/met/JMA_DataBase/GWO/Hourly に直接コピー可能）
  python jma_weather_downloader.py --year 2023 --station tokyo --output ./download --gwo-format

Output structure:
  {output_dir}/{StationName}/{StationName}{Year}.csv
  Example: jma_data/Tokyo/Tokyo2023.csv

  JMA format (default): 20 columns with headers, direct values (hPa, °C, m/s)
  GWO format (--gwo-format): 33 columns, no headers, scaled values (×0.1), with RMK codes

Available preset stations:
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
        help="観測地点名（カスタム観測地点の場合、日本語）"
    )

    parser.add_argument(
        "--name_en",
        type=str,
        help="観測地点名（カスタム観測地点の場合、英語、ディレクトリ名とファイル名に使用）"
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

    parser.add_argument(
        "--gwo-format",
        action="store_true",
        help="GWO形式に変換（33列、ヘッダーなし、雲量補間あり）Convert to GWO format (33 columns, no header, with cloud cover interpolation)"
    )

    args = parser.parse_args()

    # 観測地点の設定
    if args.station:
        station_info = STATIONS[args.station]
        prec_no = station_info["prec_no"]
        block_no = station_info["block_no"]
        station_name = station_info["name"]
        station_name_en = station_info["name_en"]
    elif args.prec_no and args.block_no and args.name:
        prec_no = args.prec_no
        block_no = args.block_no
        station_name = args.name
        # カスタム地点の場合、英語名が指定されていない場合は日本語名を使用
        station_name_en = args.name_en if args.name_en else args.name
    else:
        parser.error("--station または (--prec_no, --block_no, --name) のセットを指定してください")

    # 各年についてダウンロード
    for year in args.year:
        try:
            download_yearly_data(
                prec_no=prec_no,
                block_no=block_no,
                station_name=station_name,
                station_name_en=station_name_en,
                year=year,
                output_dir=args.output,
                delay=args.delay,
                gwo_format=args.gwo_format
            )
        except Exception as e:
            print(f"\n[ERROR] Failed to download {station_name} ({year}): {e}\n")
            continue


if __name__ == "__main__":
    main()
