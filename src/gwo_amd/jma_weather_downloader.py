#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA Weather Data Downloader
気象庁の過去の気象データ（etrn）サービスから時別値をCSVでダウンロードするツール

Usage:
    python -m gwo_amd.jma_weather_downloader --year 2023 --station tokyo
    python -m gwo_amd.jma_weather_downloader --year 2023 --station tokyo \
        --prec_no 44 --block_no 47662
"""

import argparse
import datetime as dt
import importlib.resources as pkg_resources
import sys
import time
from calendar import monthrange
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yaml

# 気象庁 etrn サービスのベースURL
# 時別値（hourly data）のエンドポイント
ETRN_BASE_URL = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"

PACKAGE_CATALOG_RESOURCE = ("gwo_amd.data", "stations.yaml")


def load_station_catalog(config_path=None):
    """Load stations.yaml and normalize keys (lowercase)."""
    if config_path:
        path = Path(config_path)
        if not path.exists():
            print(f"Warning: Station catalog not found at {path}")
            return {}, path
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            print(f"Warning: Failed to load station catalog ({path}): {exc}")
            return {}, path
        catalog_source = path
    else:
        package, resource = PACKAGE_CATALOG_RESOURCE
        try:
            catalog_resource = pkg_resources.files(package).joinpath(resource)
            with catalog_resource.open("r", encoding="utf-8") as handle:
                data = yaml.safe_load(handle) or {}
            catalog_source = Path(f"package://{package}/{resource}")
        except FileNotFoundError:
            print(f"Warning: Station catalog resource not found ({package}/{resource})")
            return {}, Path(f"package://{package}/{resource}")
        except Exception as exc:
            print(f"Warning: Failed to load station catalog resource: {exc}")
            return {}, Path(f"package://{package}/{resource}")

    stations = data.get("stations", {})
    normalized = {}
    for key, info in stations.items():
        normalized[key.lower()] = info
    return normalized, catalog_source


def _parse_iso_date(value):
    if not value:
        return None
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def collect_relevant_remarks(station_metadata, year):
    if not station_metadata or not station_metadata.get("remarks"):
        return []

    year_start = dt.date(year, 1, 1)
    year_end = dt.date(year, 12, 31)
    remarks = []
    seen = set()

    for remark in station_metadata["remarks"]:
        note = (remark.get("note") or "").strip()
        if not note:
            continue
        start_label = remark.get("start_date")
        end_label = remark.get("end_date")
        start_bound = _parse_iso_date(start_label) or dt.date(1900, 1, 1)
        end_bound = _parse_iso_date(end_label) or dt.date(9999, 12, 31)
        if start_bound <= year_end and end_bound >= year_start:
            key = (note, start_label, end_label)
            if key in seen:
                continue
            seen.add(key)
            remarks.append(
                {
                    "note": note,
                    "start_label": start_label or "unknown",
                    "end_label": end_label or "present",
                    "source": remark.get("source", "smaster.index"),
                }
            )
    return remarks


def print_special_remarks(station_metadata, year):
    remarks = collect_relevant_remarks(station_metadata, year)
    if not remarks:
        return

    station_label = station_metadata.get("name_en", "station")
    print(f"[info] Special remarks for {station_label} ({year}):")
    for remark in remarks:
        print(
            f"  - [{remark['start_label']} – {remark['end_label']}] "
            f"{remark['note']} ({remark['source']})"
        )


def print_station_list(catalog, catalog_path):
    if not catalog:
        print(f"No stations found in {catalog_path}")
        return

    header = f"{'Key':<20} {'JP Name':<10} {'Prefecture':<14} {'prec':>5} {'block':>7} {'id':>5}"
    print(f"Station catalog ({len(catalog)} entries) from {catalog_path}:")
    print(header)
    print("-" * len(header))
    for key in sorted(catalog):
        info = catalog[key]
        print(
            f"{key:<20} "
            f"{info.get('name_jp', ''):<10} "
            f"{info.get('prefecture_jp', ''):<14} "
            f"{str(info.get('prec_no', '')):>5} "
            f"{str(info.get('block_no', '')):>7} "
            f"{str(info.get('station_id', '')):>5}"
        )


# Wind direction mapping for GWO format conversion
WIND_DIR_MAP = {
    "北": 16,
    "北北東": 1,
    "北東": 2,
    "東北東": 3,
    "東": 4,
    "東南東": 5,
    "南東": 6,
    "南南東": 7,
    "南": 8,
    "南南西": 9,
    "南西": 10,
    "西南西": 11,
    "西": 12,
    "西北西": 13,
    "北西": 14,
    "北北西": 15,
    "静穏": 0,
    "Calm": 0,
}


def convert_to_gwo_format(df_jma, station_metadata):
    """
    Convert JMA DataFrame to GWO format (33 columns, no header)

    Parameters
    ----------
    df_jma : pd.DataFrame
        DataFrame from JMA (with headers)
    station_metadata : dict
        Station metadata containing name/id information

    Returns
    -------
    pd.DataFrame
        GWO-formatted DataFrame
    """
    station_name_en = station_metadata.get("name_en", "station")
    station_name_jp = station_metadata.get("name_jp", station_name_en)
    station_id = str(station_metadata.get("station_id", "999"))

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

            # Helper functions for parsing JMA data with quality symbols
            # See: https://www.data.jma.go.jp/risk/obsdl/top/help3
            def parse_value_and_quality(val):
                """
                Parse JMA value with quality symbol and return (value, quality_code).

                Quality symbols:
                - )  : quasi-normal (some missing data, ~80% present) → RMK=5
                - ]  : insufficient data (gaps exceed tolerance) → RMK=5
                - #  : questionable value → RMK=5
                - -- : no phenomenon occurred (e.g., no rain) → value=0, RMK=8
                - /// or × : missing/invalid data → value=None, RMK=1
                - (blank) : not an observation item → value=None, RMK=2
                """
                if pd.isna(val) or val == "":
                    return None, 2  # Not observed

                val_str = str(val).strip()

                # Check for missing data symbols
                if val_str in ["///", "×"]:
                    return None, 1  # Missing data

                # Check for no phenomenon
                if val_str == "--":
                    return 0, 2  # No phenomenon (not observed, value=0)

                # Check for quality symbols (remove them but track quality)
                quality_code = 8  # Normal by default
                cleaned_val = val_str

                if ")" in val_str:
                    quality_code = 5  # Quasi-normal (contains estimated values)
                    cleaned_val = val_str.replace(")", "").strip()
                elif "]" in val_str:
                    quality_code = 5  # Insufficient data
                    cleaned_val = val_str.replace("]", "").strip()
                elif "#" in val_str:
                    quality_code = 5  # Questionable value
                    cleaned_val = val_str.replace("#", "").strip()

                # Parse numeric value
                try:
                    # Handle negative sign variants
                    cleaned_val = cleaned_val.replace("−", "-")
                    value = float(cleaned_val)
                    return value, quality_code
                except ValueError:
                    return None, 1  # Parse error, treat as missing

            def to_float_with_quality(val):
                """Parse value and return (value, quality_code)."""
                return parse_value_and_quality(val)

            def to_int_scaled_with_quality(val, scale=10):
                """Parse value, scale it, and return (scaled_int, quality_code)."""
                value, quality = parse_value_and_quality(val)
                if value is not None:
                    # Use round() instead of int() to match original GWO conversion
                    # This avoids ±1 rounding errors due to floating point precision
                    return round(value * scale), quality
                return None, quality

            # Parse wind direction with quality
            def wind_dir_code_with_quality(text):
                """Parse wind direction text and return (code, quality)."""
                if pd.isna(text) or text == "":
                    return 0, 2  # Not observed

                text_str = str(text).strip()

                # Remove quality symbols
                quality = 8
                for symbol in [")", "]", "#"]:
                    if symbol in text_str:
                        quality = 5
                        text_str = text_str.replace(symbol, "").strip()

                if text_str == "--" or text_str == "":
                    return 0, 2  # No phenomenon / calm

                # Map Japanese direction to code
                code = WIND_DIR_MAP.get(text_str, 0)
                return code, quality if code > 0 else 2

            # Parse cloud cover with quality
            def parse_cloud_with_quality(cloud_str):
                """Parse cloud cover and return (value, quality)."""
                if pd.isna(cloud_str) or cloud_str == "":
                    return None, 2  # Not observed

                cloud_str = str(cloud_str).strip()

                if cloud_str in ["--", "///", "×"]:
                    return None, 2  # Not observed

                # Remove quality symbols and +/- indicators
                quality = 8
                for symbol in [")", "]", "#"]:
                    if symbol in cloud_str:
                        quality = 5
                        cloud_str = cloud_str.replace(symbol, "").strip()

                try:
                    # Remove +/- indicators (e.g., "10-" means "less than 10")
                    cloud_str = cloud_str.replace("+", "").replace("-", "").replace("−", "")
                    val = float(cloud_str)
                    return int(val) if 0 <= val <= 10 else None, quality
                except ValueError:
                    return None, 2

            # Extract values with quality codes (positions based on JMA format)
            local_pressure, local_pressure_rmk = to_int_scaled_with_quality(row.iloc[1], 10)
            sea_pressure, sea_pressure_rmk = to_int_scaled_with_quality(row.iloc[2], 10)
            temp, temp_rmk = to_int_scaled_with_quality(row.iloc[4], 10)
            dew_point, dew_point_rmk = to_int_scaled_with_quality(row.iloc[5], 10)
            vapor_pressure, vapor_pressure_rmk = to_int_scaled_with_quality(row.iloc[6], 10)
            humidity, humidity_rmk = to_int_scaled_with_quality(row.iloc[7], 1)  # % (no scaling)
            wind_speed, wind_speed_rmk = to_int_scaled_with_quality(row.iloc[8], 10)
            wind_dir, wind_dir_rmk = wind_dir_code_with_quality(row.iloc[9])
            if wind_dir_rmk == 2:
                wind_dir = None
            if wind_speed_rmk == 2:
                wind_speed = None

            sunshine, sunshine_rmk = (
                to_int_scaled_with_quality(row.iloc[10], 10) if len(row) > 10 else (None, 2)
            )
            solar, solar_rmk = (
                to_int_scaled_with_quality(row.iloc[11], 100) if len(row) > 11 else (None, 2)
            )
            precip, precip_rmk = (
                to_int_scaled_with_quality(row.iloc[3], 10) if len(row) > 3 else (None, 2)
            )
            cloud, cloud_rmk = (
                parse_cloud_with_quality(row.iloc[15]) if len(row) > 15 else (None, 2)
            )

            # Build GWO row (33 columns)
            gwo_row = [
                station_id,
                station_name_jp,
                station_id,  # 1-3
                year,
                month,
                day,
                hour,  # 4-7
                local_pressure,
                local_pressure_rmk,  # 8-9
                sea_pressure,
                sea_pressure_rmk,  # 10-11
                temp,
                temp_rmk,  # 12-13
                vapor_pressure,
                vapor_pressure_rmk,  # 14-15
                humidity,
                humidity_rmk,  # 16-17
                wind_dir,
                wind_dir_rmk,  # 18-19
                wind_speed,
                wind_speed_rmk,  # 20-21
                cloud,
                cloud_rmk,  # 22-23
                0,
                2,  # 24-25 (weather code not available)
                dew_point,
                dew_point_rmk,  # 26-27
                sunshine,
                sunshine_rmk,  # 28-29
                solar,
                solar_rmk,  # 30-31
                precip,
                precip_rmk,  # 32-33
            ]

            gwo_rows.append(gwo_row)

        except Exception as e:
            print(f"Warning: Skipping row {idx}: {e}")
            continue

    gwo_df = pd.DataFrame(gwo_rows)

    # Interpolate cloud cover
    if len(gwo_df) > 0:
        gwo_df[21] = (
            gwo_df[21]
            .replace({None: np.nan})
            .interpolate(method="linear")
            .round()
            .clip(0, 10)
            .fillna(0)
            .astype(int)
        )
        # Update RMK for interpolated values (keep as 2 if originally not observed)
        # Actually, keep cloud RMK as 2 since original data didn't have it

    # Replace None with 0 for missing data columns (sunshine, solar, precip)
    # Columns 27, 29, 31 are sunshine, solar, precip values
    for col in [27, 29, 31]:
        gwo_df[col] = gwo_df[col].fillna(0)

    # Ensure integer types for all numeric columns
    int_columns = [
        0,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        32,
    ]
    for col in int_columns:
        if col in gwo_df.columns:
            gwo_df[col] = gwo_df[col].fillna(0).astype(int)

    # Calculate missing value statistics
    # Missing values are indicated by RMK code = 1 (missing) or 2 (not observed)
    total_rows = len(gwo_df)

    # Count original cloud observations (before interpolation)
    cloud_original_missing = sum(
        1
        for _, row in df_jma.iterrows()
        if len(row) > 15 and (pd.isna(row.iloc[15]) or str(row.iloc[15]).strip() in ("", "--"))
    )

    # RMK column mapping (0-indexed):
    # Col 9 (idx 8): Local pressure RMK, Col 11 (idx 10): Sea pressure RMK
    # Col 13 (idx 12): Temperature RMK, Col 15 (idx 14): Vapor pressure RMK
    # Col 17 (idx 16): Humidity RMK, Col 19 (idx 18): Wind dir RMK
    # Col 21 (idx 20): Wind speed RMK, Col 23 (idx 22): Cloud RMK
    # Col 25 (idx 24): Weather RMK, Col 27 (idx 26): Dew point RMK
    # Col 29 (idx 28): Sunshine RMK, Col 31 (idx 30): Solar RMK
    # Col 33 (idx 32): Precipitation RMK

    stats = {
        "total_rows": total_rows,
        "pressure": (gwo_df[8] == 1).sum(),  # RMK=1 means missing
        "temperature": (gwo_df[12] == 1).sum(),
        "humidity": (gwo_df[16] == 1).sum(),
        "wind_speed": (gwo_df[20] == 1).sum(),
        "dew_point": (gwo_df[26] == 1).sum(),
        "sunshine": (gwo_df[28] == 2).sum(),  # RMK=2 means not observed
        "solar": (gwo_df[30] == 2).sum(),
        "precipitation": (gwo_df[32] == 2).sum(),
        "cloud_original": cloud_original_missing,
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
        "view": "p1",  # データ表示モード
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
            df["年"] = year
            df["月"] = month
            df["日"] = day

            return df

        except requests.exceptions.RequestException as e:
            if attempt < retry - 1:
                wait_time = 2**attempt  # Exponential backoff
                print(f"[WARN] Request failed (attempt {attempt + 1}/{retry}): {e}")
                print(f"       Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                msg = f"Failed to download data after {retry} attempts: {e}"
                raise RuntimeError(msg) from e
        except Exception as e:
            msg = f"Error parsing data for {year}/{month}/{day}: {e}"
            raise RuntimeError(msg) from e


def download_yearly_data(
    prec_no,
    block_no,
    station_name,
    station_name_en,
    year,
    output_dir,
    delay=1.0,
    gwo_format=False,
    station_metadata=None,
):
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
    station_metadata : dict, optional
        station_id や remarks などの追加情報
    """
    output_dir = Path(output_dir)

    # GWO互換のディレクトリ構造: {output_dir}/{StationName}/
    station_dir = output_dir / station_name_en
    station_dir.mkdir(parents=True, exist_ok=True)

    all_data = []

    print(f"\n{'=' * 60}")
    print(f"Downloading: {station_name} / {station_name_en} ({year})")
    print(f"Parameters: prec_no={prec_no}, block_no={block_no}")
    print(f"Output: {station_dir}")
    print(f"Format: {'GWO (33 columns, no header)' if gwo_format else 'JMA (with headers)'}")
    print(f"{'=' * 60}\n")

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
            metadata = station_metadata or {
                "name_en": station_name_en,
                "name_jp": station_name,
                "station_id": "999",
                "remarks": [],
            }
            combined_df, missing_stats = convert_to_gwo_format(combined_df, metadata)
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

        print(f"\n{'=' * 60}")
        print(f"SUCCESS: Data saved to {output_file}")
        print(f"Total rows: {len(combined_df)}")
        if gwo_format:
            print("Format: GWO (33 columns, cloud cover interpolated)")

            # Display missing value statistics
            if missing_stats:
                print("\nData Quality Report:")
                total = missing_stats["total_rows"]

                # Core parameters (should have very few missing)
                core_missing = []
                if missing_stats["pressure"] > 0:
                    pct = missing_stats["pressure"] * 100 / total
                    core_missing.append(
                        f"  Pressure: {missing_stats['pressure']}/{total} missing ({pct:.1f}%)"
                    )
                if missing_stats["temperature"] > 0:
                    pct = missing_stats["temperature"] * 100 / total
                    temp_msg = (
                        f"  Temperature: {missing_stats['temperature']}/{total} "
                        f"missing ({pct:.1f}%)"
                    )
                    core_missing.append(temp_msg)
                if missing_stats["humidity"] > 0:
                    pct = missing_stats["humidity"] * 100 / total
                    core_missing.append(
                        f"  Humidity: {missing_stats['humidity']}/{total} missing ({pct:.1f}%)"
                    )

                if core_missing:
                    print("  Core Parameters (unexpected missing):")
                    for msg in core_missing:
                        print(msg)

                # Optional parameters (may have missing values)
                print("  Optional Parameters:")
                sun_pct = missing_stats["sunshine"] * 100 / total
                solar_pct = missing_stats["solar"] * 100 / total
                precip_pct = missing_stats["precipitation"] * 100 / total
                print(
                    f"  Sunshine: {missing_stats['sunshine']}/{total} not observed ({sun_pct:.1f}%)"
                )
                print(
                    f"  Solar radiation: {missing_stats['solar']}/{total} "
                    f"not observed ({solar_pct:.1f}%)"
                )
                print(
                    f"  Precipitation: {missing_stats['precipitation']}/{total} "
                    f"not observed ({precip_pct:.1f}%)"
                )

                # Cloud cover interpolation report
                cloud_orig_missing = missing_stats["cloud_original"]
                cloud_coverage = (total - cloud_orig_missing) * 100 / total
                observed = total - cloud_orig_missing
                print(
                    f"  Cloud cover: {observed}/{total} observed "
                    f"({cloud_coverage:.1f}%), rest interpolated"
                )

        print(f"{'=' * 60}\n")

        return output_file
    else:
        print(f"\n{'=' * 60}")
        print(f"ERROR: No data downloaded for {station_name} ({year})")
        print(f"{'=' * 60}\n")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="気象庁の過去の気象データ（時別値）をダウンロード",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 東京の2023年データをダウンロード（JMA形式: jma_data/Tokyo/Tokyo2023.csv）
  python -m gwo_amd.jma_weather_downloader --year 2023 --station tokyo

  # 東京の2021年データをGWO形式に変換してダウンロード（33列、雲量補間あり）
  python -m gwo_amd.jma_weather_downloader --year 2021 --station tokyo --gwo-format

  # 大阪の2020-2023年のデータをダウンロード
  python -m gwo_amd.jma_weather_downloader --year 2020 2021 2022 2023 --station osaka

  # カスタム観測地点（都道府県番号と地点番号を指定）
  python -m gwo_amd.jma_weather_downloader --year 2023 --prec_no 44 --block_no 47662 \
      --name 東京 --name_en Tokyo

  # 出力ディレクトリを指定してGWO形式に変換
  # （$DATA_DIR/met/JMA_DataBase/GWO/Hourly に直接コピー可能）
  python -m gwo_amd.jma_weather_downloader --year 2023 --station tokyo \
      --output ./download --gwo-format

Output structure:
  {output_dir}/{StationName}/{StationName}{Year}.csv
  Example: jma_data/Tokyo/Tokyo2023.csv

  JMA format (default): 20 columns with headers, direct values (hPa, °C, m/s)
  GWO format (--gwo-format): 33 columns, no headers, scaled values (×0.1), with RMK codes

Use --list-stations to inspect all catalog keys defined in stations.yaml.
        """,
    )

    parser.add_argument("--year", type=int, nargs="+", help="ダウンロード対象の年（複数指定可能）")

    parser.add_argument(
        "--station",
        type=str,
        nargs="+",
        help="観測地点名（stations.yamlのキー）。複数指定で一括ダウンロード可（case-insensitive）",
    )

    parser.add_argument(
        "--stations-config",
        type=str,
        help="stations.yamlのカスタムパス（デフォルト: このスクリプトと同じ場所）",
    )

    parser.add_argument("--list-stations", action="store_true", help="観測地点の一覧を表示して終了")

    parser.add_argument("--prec_no", type=str, help="都道府県番号（カスタム観測地点の場合）")

    parser.add_argument("--block_no", type=str, help="観測地点番号（カスタム観測地点の場合）")

    parser.add_argument("--name", type=str, help="観測地点名（カスタム観測地点の場合、日本語）")

    parser.add_argument(
        "--name_en",
        type=str,
        help="観測地点名（カスタム観測地点の場合、英語、ディレクトリ名とファイル名に使用）",
    )

    parser.add_argument(
        "--output", type=str, default="jma_data", help="出力ディレクトリ（デフォルト: jma_data）"
    )

    parser.add_argument(
        "--delay", type=float, default=1.0, help="リクエスト間の待機時間（秒）デフォルト: 1.0"
    )

    parser.add_argument(
        "--gwo-format",
        action="store_true",
        help=(
            "GWO形式に変換（33列、ヘッダーなし、雲量補間あり）"
            "Convert to GWO format (33 columns, no header, with cloud cover interpolation)"
        ),
    )

    args = parser.parse_args()

    station_catalog, catalog_path = load_station_catalog(args.stations_config)
    if args.list_stations:
        print_station_list(station_catalog, catalog_path)
        return

    if not args.year:
        parser.error("--year は必須です（--list-stations で一覧表示のみ実行可能）")

    # 観測地点の設定（複数対応）
    station_jobs = []
    if args.station:
        if args.prec_no or args.block_no or args.name or args.name_en:
            parser.error("--station と (--prec_no, --block_no, --name) は同時に指定できません")

        for station_arg in args.station:
            station_key = station_arg.lower()
            if station_key not in station_catalog:
                print(
                    f"Error: Unknown station '{station_arg}'. "
                    f"Use --list-stations to inspect available keys ({catalog_path})."
                )
                sys.exit(1)

            station_info = station_catalog[station_key]
            station_name_en = station_info.get("name_en", station_arg)
            station_name_local = station_info.get("name_jp", station_name_en)
            station_jobs.append(
                {
                    "prec_no": str(station_info["prec_no"]),
                    "block_no": str(station_info["block_no"]),
                    "station_name": station_name_local,
                    "station_name_en": station_name_en,
                    "metadata": {
                        "name_en": station_name_en,
                        "name_jp": station_name_local,
                        "station_id": str(station_info.get("station_id", "999")),
                        "remarks": station_info.get("remarks", []),
                    },
                }
            )
    elif args.prec_no and args.block_no and args.name:
        station_jobs.append(
            {
                "prec_no": args.prec_no,
                "block_no": args.block_no,
                "station_name": args.name,
                "station_name_en": args.name_en if args.name_en else args.name,
                "metadata": {
                    "name_en": args.name_en if args.name_en else args.name,
                    "name_jp": args.name,
                    "station_id": "999",
                    "remarks": [],
                },
            }
        )
    else:
        parser.error("--station または (--prec_no, --block_no, --name) のセットを指定してください")

    # 各ステーション・各年についてダウンロード
    for job in station_jobs:
        station_name = job["station_name"]
        station_name_en = job["station_name_en"]
        print(f"\n{'#' * 20} {station_name} / {station_name_en} {'#' * 20}")
        for year in args.year:
            print_special_remarks(job["metadata"], year)
            try:
                download_yearly_data(
                    prec_no=job["prec_no"],
                    block_no=job["block_no"],
                    station_name=station_name,
                    station_name_en=station_name_en,
                    year=year,
                    output_dir=args.output,
                    delay=args.delay,
                    gwo_format=args.gwo_format,
                    station_metadata=job["metadata"],
                )
            except Exception as e:
                print(f"\n[ERROR] Failed to download {station_name} ({year}): {e}\n")
                continue


if __name__ == "__main__":
    main()
