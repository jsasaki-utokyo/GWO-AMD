#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA obsdl Weather Data Downloader

Downloads historical hourly weather data from JMA's obsdl service
(過去の気象データ・ダウンロード) with accurate quality information for GWO format conversion.

Features:
- Structured quality information (not symbol-based parsing)
- Accurate RMK code generation (distinguishes RMK=2 vs RMK=6)
- Direct GWO format output (33 columns, no header)

Reference:
- https://www.data.jma.go.jp/risk/obsdl/index.php
- https://www.data.jma.go.jp/risk/obsdl/top/help3

Usage:
    python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo
    python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo --output ./gwo_data
"""

import argparse
import json
import sys
import time
from calendar import monthrange
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from gwo_amd.jma_weather_downloader import (
    load_station_catalog,
    print_special_remarks,
    print_station_list,
)

# obsdl service URLs
OBSDL_BASE_URL = "https://www.data.jma.go.jp/risk/obsdl"
OBSDL_INDEX_URL = f"{OBSDL_BASE_URL}/index.php"
OBSDL_TABLE_URL = f"{OBSDL_BASE_URL}/show/table"

# Wind direction mapping: Japanese text to GWO code (1-16)
# GWO: 0=calm, 1=NNE, 2=NE, 3=ENE, 4=E, 5=ESE, 6=SE, 7=SSE, 8=S,
#      9=SSW, 10=SW, 11=WSW, 12=W, 13=WNW, 14=NW, 15=NNW, 16=N
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
}

# Element IDs for obsdl hourly data download
# Discovered from the obsdl element selection API
HOURLY_ELEMENT_IDS = {
    "local_pressure": "601",  # 現地気圧 (hPa)
    "sea_pressure": "602",  # 海面気圧 (hPa)
    "precipitation": "101",  # 降水量 (mm)
    "temperature": "201",  # 気温 (°C)
    "dew_point": "612",  # 露点温度 (°C)
    "vapor_pressure": "604",  # 蒸気圧 (hPa)
    "humidity": "605",  # 相対湿度 (%)
    "wind": "301",  # 風向・風速 (m/s, direction)
    "sunshine": "401",  # 日照時間 (hours)
    "solar_radiation": "610",  # 全天日射量 (MJ/m²)
    "cloud_cover": "607",  # 雲量 (10分比)
}

# Elements required for GWO format (order matters for CSV parsing)
GWO_REQUIRED_ELEMENTS = [
    "local_pressure",  # Cols 2-4: value, quality, homogeneity
    "sea_pressure",  # Cols 5-7: value, quality, homogeneity
    "precipitation",  # Cols 8-11: value, phenomenon_absent, quality, homogeneity
    "temperature",  # Cols 12-14: value, quality, homogeneity
    "dew_point",  # Cols 15-17: value, quality, homogeneity
    "vapor_pressure",  # Cols 18-20: value, quality, homogeneity
    "humidity",  # Cols 21-23: value, quality, homogeneity
    "wind",  # Cols 24-28: speed, quality, direction(JP), quality, homogeneity
    "sunshine",  # Cols 29-32: value, phenomenon_absent, quality, homogeneity
    "solar_radiation",  # Cols 33-35: value, quality, homogeneity
    "cloud_cover",  # Cols 36-38: value, quality, homogeneity
]


class JMAObsdlDownloader:
    """Downloads weather data from JMA obsdl service."""

    def __init__(self, delay: float = 1.0, timeout: int = 120):
        """
        Initialize with request delay for rate limiting.

        Parameters
        ----------
        delay : float
            Delay between requests in seconds (default 1.0, minimum 0.5)
        timeout : int
            Request timeout in seconds (default 120)
        """
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "*/*",
                "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
            }
        )
        self.delay = max(delay, 0.5)  # Enforce minimum delay
        self.timeout = timeout

    def _init_session(self):
        """Access obsdl index page to initialize session cookies."""
        try:
            resp = self.session.get(OBSDL_INDEX_URL, timeout=self.timeout)
            resp.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"Failed to connect to obsdl service: {e}") from e

    def _build_download_params(
        self,
        station_id: str,
        start_date: date,
        end_date: date,
    ) -> dict:
        """
        Build POST parameters for CSV download.

        Parameters
        ----------
        station_id : str
            Station ID with 's' prefix (e.g., "s47662" for Tokyo)
        start_date : date
            Start date
        end_date : date
            End date

        Returns
        -------
        dict
            POST parameters for obsdl download
        """
        # Build element list
        element_list = [[HOURLY_ELEMENT_IDS[elem], ""] for elem in GWO_REQUIRED_ELEMENTS]

        # Build ymdList as JSON array
        # Format: [start_year, end_year, start_month, end_month, start_day, end_day]
        ymd_list = [
            str(start_date.year),
            str(end_date.year),
            str(start_date.month),
            str(end_date.month),
            str(start_date.day),
            str(end_date.day),
        ]

        params = {
            "stationNumList": json.dumps([station_id]),
            "aggrgPeriod": "9",  # 9 = hourly data
            "elementNumList": json.dumps(element_list),
            "interAnnualType": "1",
            "ymdList": json.dumps(ymd_list),
            "optionNumList": json.dumps([]),
            "downloadFlag": "true",  # Request CSV download
            "rmkFlag": "1",  # Include quality information
            "disconnectFlag": "1",  # Include phenomenon-absent info
            "csvFlag": "1",  # Numeric CSV format
            "kijiFlag": "0",
            "youbiFlag": "0",
            "fukenFlag": "0",
            "jikantaiFlag": "0",
            "jikantaiList": json.dumps([]),
            "ymdLiteral": "1",  # Date literal format
        }

        return params

    def download_period_data(
        self, station_id: str, start_date: date, end_date: date
    ) -> pd.DataFrame | None:
        """
        Download data for a date range.

        Parameters
        ----------
        station_id : str
            Station ID with 's' prefix (e.g., "s47662" for Tokyo)
        start_date : date
            Start date
        end_date : date
            End date

        Returns
        -------
        pd.DataFrame or None
            Downloaded data as DataFrame, or None if download failed
        """
        params = self._build_download_params(station_id, start_date, end_date)

        try:
            resp = self.session.post(
                OBSDL_TABLE_URL,
                data=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()

            # Check content type
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" in content_type and "charset=UTF-8" in content_type:
                # Likely an error page
                if "エラー" in resp.text or "<html" in resp.text[:100]:
                    print("    [WARN] Server returned error page")
                    return None

            # Check for maintenance
            if "メンテナンス" in resp.text:
                raise RuntimeError("JMA obsdl service is under maintenance")

            # Decode content (obsdl returns cp932/Shift-JIS)
            try:
                content = resp.content.decode("cp932")
            except UnicodeDecodeError:
                try:
                    content = resp.content.decode("shift-jis")
                except UnicodeDecodeError:
                    content = resp.content.decode("utf-8", errors="replace")

            # Parse CSV
            if not content.strip() or "データがありません" in content:
                return None

            df = self._parse_csv_content(content)
            return df

        except requests.exceptions.RequestException as e:
            print(f"    [WARN] Request failed: {e}")
            return None

    def _parse_csv_content(self, content: str) -> pd.DataFrame | None:
        """
        Parse CSV content from obsdl response.

        CSV structure:
        - Row 0: Download timestamp
        - Row 1: Empty
        - Row 2: Station name header
        - Row 3: Element name header
        - Row 4: Sub-element header (wind direction, etc.)
        - Row 5: Quality/phenomenon-absent info header
        - Row 6+: Data rows

        Parameters
        ----------
        content : str
            CSV content as string

        Returns
        -------
        pd.DataFrame or None
            Parsed data
        """
        lines = content.strip().split("\n")

        # Skip header rows (6 rows)
        data_start = 6
        if len(lines) <= data_start:
            return None

        # Parse data rows
        data_rows = []
        for line in lines[data_start:]:
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) > 1:
                data_rows.append(parts)

        if not data_rows:
            return None

        # Create DataFrame with raw data
        df = pd.DataFrame(data_rows)

        return df

    def _convert_quality_to_rmk(
        self,
        quality: str | int,
        phenomenon_absent: str | int | None = None,
    ) -> int:
        """
        Convert obsdl quality info to GWO RMK code.

        This is the key improvement over etrn scraping:
        - obsdl provides explicit quality codes
        - obsdl provides explicit phenomenon-absent flags
        - Allows accurate distinction between RMK=2 (not observed) and RMK=6 (no phenomenon)

        Parameters
        ----------
        quality : str or int
            obsdl quality value (8, 5, 4, 2, 1, 0)
        phenomenon_absent : str or int, optional
            1 if no phenomenon (e.g., no rain), 0 if phenomenon exists

        Returns
        -------
        int
            GWO RMK code (0-9)
        """
        # Convert to int
        try:
            quality = int(quality) if quality not in (None, "", "nan") else 0
        except (ValueError, TypeError):
            quality = 0

        try:
            phen = int(phenomenon_absent) if phenomenon_absent not in (None, "", "nan") else 0
        except (ValueError, TypeError):
            phen = 0

        # Check for phenomenon-absent override (RMK=6)
        # This is the critical improvement: distinguish RMK=2 from RMK=6
        if phen == 1 and quality == 8:
            return 6  # 該当現象なし (no phenomenon occurred)

        # Standard quality mapping
        # obsdl quality → GWO RMK
        rmk_map = {
            8: 8,  # 正常値 → 正常な観測値
            5: 5,  # 準正常値 → 推定値を含む
            4: 5,  # 資料不足値 → 推定値を含む
            2: 5,  # 疑問値 → 推定値を含む
            1: 1,  # 欠測 → 欠測
            0: 2,  # 統計対象外 → 観測していない
        }
        return rmk_map.get(quality, 8)

    def convert_to_gwo(self, df: pd.DataFrame, station_metadata: dict) -> tuple[pd.DataFrame, dict]:
        """
        Convert obsdl DataFrame to GWO format (33 columns).

        GWO format columns:
        0-2: station_id, station_name, station_id
        3-6: year, month, day, hour
        7-8: local_pressure, rmk
        9-10: sea_pressure, rmk
        11-12: temperature, rmk
        13-14: vapor_pressure, rmk
        15-16: humidity, rmk
        17-18: wind_dir, rmk
        19-20: wind_speed, rmk
        21-22: cloud, rmk
        23-24: weather, rmk (always 0/2 - not available)
        25-26: dew_point, rmk
        27-28: sunshine, rmk
        29-30: solar, rmk
        31-32: precip, rmk

        Parameters
        ----------
        df : pd.DataFrame
            DataFrame from obsdl download
        station_metadata : dict
            Station metadata with name/id information

        Returns
        -------
        tuple[pd.DataFrame, dict]
            (GWO-formatted DataFrame, statistics dict)
        """
        station_name_en = station_metadata.get("name_en", "station")
        station_name_jp = station_metadata.get("name_jp", station_name_en)
        station_id = str(station_metadata.get("station_id", "999"))

        gwo_rows = []
        stats = {
            "total_rows": 0,
            "pressure_missing": 0,
            "temperature_missing": 0,
            "humidity_missing": 0,
            "wind_missing": 0,
            "sunshine_not_observed": 0,
            "solar_not_observed": 0,
            "precip_no_phenomenon": 0,
            "cloud_interpolated": 0,
        }

        # Process each row
        for idx, row in df.iterrows():
            try:
                gwo_row = self._convert_row_to_gwo(row, station_id, station_name_jp, stats)
                if gwo_row:
                    gwo_rows.append(gwo_row)
                    stats["total_rows"] += 1
            except Exception as e:
                print(f"    [WARN] Skipping row {idx}: {e}")
                continue

        if not gwo_rows:
            return pd.DataFrame(), stats

        gwo_df = pd.DataFrame(gwo_rows)

        # Apply cloud cover interpolation
        gwo_df = self._apply_cloud_interpolation(gwo_df, stats)

        # Ensure proper dtypes
        gwo_df = self._finalize_gwo_dtypes(gwo_df)

        return gwo_df, stats

    def _convert_row_to_gwo(
        self, row: pd.Series, station_id: str, station_name_jp: str, stats: dict
    ) -> list | None:
        """
        Convert a single obsdl row to GWO format.

        obsdl CSV column structure (38 columns total):
        0: datetime
        1-3: local_pressure (value, quality, homogeneity)
        4-6: sea_pressure (value, quality, homogeneity)
        7-10: precipitation (value, phenomenon_absent, quality, homogeneity)
        11-13: temperature (value, quality, homogeneity)
        14-16: dew_point (value, quality, homogeneity)
        17-19: vapor_pressure (value, quality, homogeneity)
        20-22: humidity (value, quality, homogeneity)
        23-27: wind (speed, quality, direction_jp, quality, homogeneity)
        28-31: sunshine (value, phenomenon_absent, quality, homogeneity)
        32-34: solar_radiation (value, quality, homogeneity)
        35-37: cloud_cover (value, quality, homogeneity)

        Parameters
        ----------
        row : pd.Series
            Row from obsdl DataFrame
        station_id : str
            Station ID
        station_name_jp : str
            Japanese station name
        stats : dict
            Statistics to update

        Returns
        -------
        list or None
            GWO format row (33 elements) or None if failed
        """
        # Parse datetime (column 0)
        datetime_str = str(row.iloc[0])
        try:
            # Format: "2024/1/1 1:00:00"
            dt = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(datetime_str, "%Y/%m/%d %H:%M")
            except ValueError:
                return None

        year = dt.year
        month = dt.month
        day = dt.day
        # GWO uses 1-24 for hours (24:00 = next day 00:00)
        hour = dt.hour if dt.hour > 0 else 24

        def parse_value(val, scale=1):
            """Parse numeric value and scale it."""
            if pd.isna(val) or val == "" or val == "--":
                return None
            try:
                v = float(str(val).strip())
                return round(v * scale)
            except ValueError:
                return None

        def get_wind_dir_code(direction_jp):
            """Convert Japanese wind direction to GWO code."""
            if pd.isna(direction_jp) or direction_jp == "":
                return 0
            return WIND_DIR_MAP.get(str(direction_jp).strip(), 0)

        # Extract values with column indices
        # Local pressure: cols 1-3
        local_pressure = parse_value(row.iloc[1], 10)  # ×10 for 0.1hPa
        local_pressure_quality = row.iloc[2] if len(row) > 2 else 8
        local_pressure_rmk = self._convert_quality_to_rmk(local_pressure_quality)

        # Sea pressure: cols 4-6
        sea_pressure = parse_value(row.iloc[4], 10)
        sea_pressure_quality = row.iloc[5] if len(row) > 5 else 8
        sea_pressure_rmk = self._convert_quality_to_rmk(sea_pressure_quality)

        # Precipitation: cols 7-10 (has phenomenon_absent)
        precip = parse_value(row.iloc[7], 10)  # ×10 for 0.1mm
        precip_phenomenon = row.iloc[8] if len(row) > 8 else 0
        precip_quality = row.iloc[9] if len(row) > 9 else 8
        precip_rmk = self._convert_quality_to_rmk(precip_quality, precip_phenomenon)
        if precip_rmk == 6:
            stats["precip_no_phenomenon"] += 1

        # Temperature: cols 11-13
        temperature = parse_value(row.iloc[11], 10)  # ×10 for 0.1°C
        temp_quality = row.iloc[12] if len(row) > 12 else 8
        temp_rmk = self._convert_quality_to_rmk(temp_quality)
        if temp_rmk == 1:
            stats["temperature_missing"] += 1

        # Dew point: cols 14-16
        dew_point = parse_value(row.iloc[14], 10)
        dew_point_quality = row.iloc[15] if len(row) > 15 else 8
        dew_point_rmk = self._convert_quality_to_rmk(dew_point_quality)

        # Vapor pressure: cols 17-19
        vapor_pressure = parse_value(row.iloc[17], 10)
        vapor_quality = row.iloc[18] if len(row) > 18 else 8
        vapor_rmk = self._convert_quality_to_rmk(vapor_quality)

        # Humidity: cols 20-22
        humidity = parse_value(row.iloc[20], 1)  # No scaling
        humidity_quality = row.iloc[21] if len(row) > 21 else 8
        humidity_rmk = self._convert_quality_to_rmk(humidity_quality)
        if humidity_rmk == 1:
            stats["humidity_missing"] += 1

        # Wind: cols 23-27 (speed, quality, direction_jp, quality, homogeneity)
        wind_speed = parse_value(row.iloc[23], 10)  # ×10 for 0.1m/s
        wind_speed_quality = row.iloc[24] if len(row) > 24 else 8
        wind_speed_rmk = self._convert_quality_to_rmk(wind_speed_quality)
        wind_dir_jp = row.iloc[25] if len(row) > 25 else ""
        wind_dir = get_wind_dir_code(wind_dir_jp)
        wind_dir_quality = row.iloc[26] if len(row) > 26 else 8
        wind_dir_rmk = self._convert_quality_to_rmk(wind_dir_quality)
        if wind_speed_rmk == 1:
            stats["wind_missing"] += 1

        # Sunshine: cols 28-31 (has phenomenon_absent)
        sunshine = parse_value(row.iloc[28], 10)  # ×10 for 0.1h
        sunshine_phenomenon = row.iloc[29] if len(row) > 29 else 0
        sunshine_quality = row.iloc[30] if len(row) > 30 else 8
        sunshine_rmk = self._convert_quality_to_rmk(sunshine_quality, sunshine_phenomenon)
        if sunshine_rmk in (2, 6):  # Not observed or no phenomenon
            stats["sunshine_not_observed"] += 1

        # Solar radiation: cols 32-34
        solar = parse_value(row.iloc[32], 100)  # ×100 for 0.01MJ/m²
        solar_quality = row.iloc[33] if len(row) > 33 else 8
        solar_rmk = self._convert_quality_to_rmk(solar_quality)
        if solar_rmk == 2:
            stats["solar_not_observed"] += 1

        # Cloud cover: cols 35-37
        cloud = parse_value(row.iloc[35], 1)  # No scaling (0-10)
        cloud_quality = row.iloc[36] if len(row) > 36 else 8
        cloud_rmk = self._convert_quality_to_rmk(cloud_quality)

        # Handle missing values - set to None for truly missing data (RMK=0,1)
        def mask_missing(value, rmk):
            """Set value to None only for truly missing data (RMK=0 or RMK=1)."""
            return None if rmk in (0, 1) else value

        # Determine explicit zero values for physically meaningful cases:
        # - Sunshine: RMK=2 (nighttime) → 0 hours of sunshine
        # - Solar: RMK=2 (nighttime) → 0 W/m²
        # - Precipitation: RMK=6 (no phenomenon) → 0 mm
        # These are NOT missing data - they are valid zero values.
        sunshine_value = 0 if sunshine_rmk in (2, 6) else mask_missing(sunshine, sunshine_rmk)
        solar_value = 0 if solar_rmk == 2 else mask_missing(solar, solar_rmk)
        precip_value = 0 if precip_rmk == 6 else mask_missing(precip, precip_rmk)

        # Build GWO row (33 columns)
        gwo_row = [
            station_id,  # 0: Station ID
            station_name_jp,  # 1: Station name
            station_id,  # 2: Station ID2
            year,  # 3: Year
            month,  # 4: Month
            day,  # 5: Day
            hour,  # 6: Hour (1-24)
            mask_missing(local_pressure, local_pressure_rmk),  # 7: Local pressure
            local_pressure_rmk,  # 8: Local pressure RMK
            mask_missing(sea_pressure, sea_pressure_rmk),  # 9: Sea pressure
            sea_pressure_rmk,  # 10: Sea pressure RMK
            mask_missing(temperature, temp_rmk),  # 11: Temperature
            temp_rmk,  # 12: Temperature RMK
            mask_missing(vapor_pressure, vapor_rmk),  # 13: Vapor pressure
            vapor_rmk,  # 14: Vapor pressure RMK
            mask_missing(humidity, humidity_rmk),  # 15: Humidity
            humidity_rmk,  # 16: Humidity RMK
            mask_missing(wind_dir, wind_dir_rmk),  # 17: Wind direction
            wind_dir_rmk,  # 18: Wind direction RMK
            mask_missing(wind_speed, wind_speed_rmk),  # 19: Wind speed
            wind_speed_rmk,  # 20: Wind speed RMK
            cloud,  # 21: Cloud cover (will be interpolated)
            cloud_rmk,  # 22: Cloud RMK
            None,  # 23: Weather (not available from JMA)
            2,  # 24: Weather RMK (always 2 = not observed)
            mask_missing(dew_point, dew_point_rmk),  # 25: Dew point
            dew_point_rmk,  # 26: Dew point RMK
            sunshine_value,  # 27: Sunshine (0 for nighttime RMK=2)
            sunshine_rmk,  # 28: Sunshine RMK
            solar_value,  # 29: Solar (0 for nighttime RMK=2)
            solar_rmk,  # 30: Solar RMK
            precip_value,  # 31: Precipitation (0 for no phenomenon RMK=6)
            precip_rmk,  # 32: Precipitation RMK
        ]

        return gwo_row

    def _apply_cloud_interpolation(self, df: pd.DataFrame, stats: dict) -> pd.DataFrame:
        """
        Apply cloud cover interpolation to GWO DataFrame.

        Cloud cover is only observed at 3-hour intervals (03, 06, 09, 12, 15, 18, 21).
        Linearly interpolate values for other hours.

        Parameters
        ----------
        df : pd.DataFrame
            GWO format DataFrame
        stats : dict
            Statistics dict to update

        Returns
        -------
        pd.DataFrame
            DataFrame with interpolated cloud cover
        """
        if len(df) == 0:
            return df

        # Cloud column is index 21, RMK is 22
        cloud_col = 21
        cloud_rmk_col = 22
        hour_col = 6

        # Observation hours for cloud cover
        obs_hours = {3, 6, 9, 12, 15, 18, 21}

        # Convert cloud to numeric and interpolate
        cloud_series = pd.to_numeric(df[cloud_col], errors="coerce")
        cloud_interp = (
            cloud_series.interpolate(method="linear").round().clip(0, 10).fillna(0).astype(int)
        )
        df[cloud_col] = cloud_interp

        # Update RMK for interpolated values
        hours = df[hour_col].astype(int)
        # Handle hour 24 -> 0 for comparison
        hours_mod = hours.replace(24, 0)
        interpolated_mask = ~hours_mod.isin(obs_hours)
        df.loc[interpolated_mask, cloud_rmk_col] = 2
        stats["cloud_interpolated"] = interpolated_mask.sum()

        return df

    def _finalize_gwo_dtypes(self, df: pd.DataFrame) -> pd.DataFrame:
        """Ensure proper data types for GWO format output."""
        # Year, month, day, hour (cols 3-6) - int
        for col in [3, 4, 5, 6]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        # Nullable data columns - Int64
        nullable_cols = [7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31]
        for col in nullable_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

        # RMK columns - int
        rmk_cols = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]
        for col in rmk_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(8).astype(int)

        return df


class JMAObsdlGWOConverter:
    """
    High-level converter that downloads from obsdl and outputs GWO format.

    This class handles the full workflow:
    1. Session management
    2. Monthly data download
    3. Parsing and conversion to GWO format
    4. File output
    """

    def __init__(self, delay: float = 1.0):
        """
        Initialize converter.

        Parameters
        ----------
        delay : float
            Delay between requests in seconds
        """
        self.downloader = JMAObsdlDownloader(delay=delay)
        self.delay = delay

    def download_year_gwo(
        self,
        station_key: str,
        year: int,
        output_dir: str = "gwo_data",
        station_catalog: dict | None = None,
    ) -> Path | None:
        """
        Download one year of data and save as GWO format CSV.

        Parameters
        ----------
        station_key : str
            Station key from stations.yaml (case-insensitive)
        year : int
            Target year
        output_dir : str
            Output directory path
        station_catalog : dict, optional
            Pre-loaded station catalog

        Returns
        -------
        Path or None
            Path to output file, or None if failed
        """
        # Load catalog if not provided
        if station_catalog is None:
            station_catalog, _ = load_station_catalog()

        # Lookup station
        station_key_lower = station_key.lower()
        if station_key_lower not in station_catalog:
            raise ValueError(f"Unknown station: {station_key}")

        station_info = station_catalog[station_key_lower]
        station_name_en = station_info.get("name_en", station_key)
        station_name_jp = station_info.get("name_jp", station_name_en)
        # obsdl uses station ID with 's' prefix
        block_no = str(station_info.get("block_no", ""))
        station_id = f"s{block_no}"

        # Prepare output directory
        output_path = Path(output_dir) / station_name_en
        output_path.mkdir(parents=True, exist_ok=True)

        print(f"\n{'=' * 60}")
        print(f"Downloading from obsdl: {station_name_jp} / {station_name_en} ({year})")
        print(f"Station ID: {station_id} (block_no: {block_no})")
        print(f"Output: {output_path}")
        print("Format: GWO (33 columns, no header)")
        print(f"{'=' * 60}\n")

        # Initialize session
        print("  Initializing obsdl session...")
        try:
            self.downloader._init_session()
            print("    Session initialized successfully")
        except Exception as e:
            print(f"    [ERROR] Failed to initialize session: {e}")
            return None

        # Download each month separately to avoid timeout
        all_data = []
        for month in range(1, 13):
            _, last_day = monthrange(year, month)
            start_date = date(year, month, 1)
            end_date = date(year, month, last_day)

            print(f"  Downloading {year}/{month:02d} (1-{last_day})...")

            try:
                df = self.downloader.download_period_data(station_id, start_date, end_date)
                if df is not None and len(df) > 0:
                    all_data.append(df)
                    print(f"    [{year}/{month:02d}] OK (rows: {len(df)})")
                else:
                    print(f"    [{year}/{month:02d}] No data")

                # Rate limiting
                time.sleep(self.delay)

            except Exception as e:
                print(f"    [{year}/{month:02d}] WARN: {e}")
                time.sleep(self.delay)
                continue

        if not all_data:
            print(f"\n[ERROR] No data downloaded for {station_name_en} ({year})")
            return None

        # Combine monthly data
        combined_df = pd.concat(all_data, ignore_index=True)
        print(f"\n  Total raw rows: {len(combined_df)}")

        # Convert to GWO format
        print("  Converting to GWO format...")
        metadata = {
            "name_en": station_name_en,
            "name_jp": station_name_jp,
            "station_id": station_info.get("station_id", "999"),
        }

        gwo_df, stats = self.downloader.convert_to_gwo(combined_df, metadata)

        if len(gwo_df) == 0:
            print(f"\n[ERROR] Conversion failed for {station_name_en} ({year})")
            return None

        # Save to file
        output_file = output_path / f"{station_name_en}{year}.csv"
        gwo_df.to_csv(output_file, header=False, index=False, encoding="utf-8")

        print(f"\n{'=' * 60}")
        print(f"SUCCESS: Data saved to {output_file}")
        print(f"Total rows: {len(gwo_df)}")
        self._print_stats(stats)
        print(f"{'=' * 60}\n")

        return output_file

    def _print_stats(self, stats: dict):
        """Print data quality statistics."""
        if not stats or stats["total_rows"] == 0:
            return

        total = stats["total_rows"]
        print("\nData Quality Report:")

        # Core parameters
        core_issues = []
        if stats.get("pressure_missing", 0) > 0:
            pct = stats["pressure_missing"] * 100 / total
            n = stats["pressure_missing"]
            core_issues.append(f"  Pressure: {n}/{total} missing ({pct:.1f}%)")
        if stats.get("temperature_missing", 0) > 0:
            pct = stats["temperature_missing"] * 100 / total
            n = stats["temperature_missing"]
            core_issues.append(f"  Temperature: {n}/{total} missing ({pct:.1f}%)")
        if stats.get("humidity_missing", 0) > 0:
            pct = stats["humidity_missing"] * 100 / total
            n = stats["humidity_missing"]
            core_issues.append(f"  Humidity: {n}/{total} missing ({pct:.1f}%)")

        if core_issues:
            print("  Core Parameters (unexpected missing):")
            for msg in core_issues:
                print(msg)

        # Optional parameters with explicit zero values
        print("  Optional Parameters (explicit zeros, not missing):")
        if stats.get("sunshine_not_observed", 0) > 0:
            pct = stats["sunshine_not_observed"] * 100 / total
            print(
                f"    Sunshine: {stats['sunshine_not_observed']}/{total} "
                f"nighttime (RMK=2, value=0) ({pct:.1f}%)"
            )
        if stats.get("solar_not_observed", 0) > 0:
            pct = stats["solar_not_observed"] * 100 / total
            print(
                f"    Solar radiation: {stats['solar_not_observed']}/{total} "
                f"nighttime (RMK=2, value=0) ({pct:.1f}%)"
            )
        if stats.get("precip_no_phenomenon", 0) > 0:
            pct = stats["precip_no_phenomenon"] * 100 / total
            print(
                f"    Precipitation: {stats['precip_no_phenomenon']}/{total} "
                f"no phenomenon (RMK=6, value=0) ({pct:.1f}%)"
            )

        # Cloud interpolation
        if stats.get("cloud_interpolated", 0) > 0:
            pct = stats["cloud_interpolated"] * 100 / total
            observed = total - stats["cloud_interpolated"]
            obs_pct = observed * 100 / total
            print(
                f"    Cloud cover: {observed}/{total} observed ({obs_pct:.1f}%), rest interpolated"
            )


def download_yearly_gwo(
    station_key: str,
    year: int,
    output_dir: str = "gwo_data",
    delay: float = 1.0,
) -> Path | None:
    """
    Download one year of data and save as GWO format CSV.

    This is the main entry point for downloading GWO-formatted data.

    Parameters
    ----------
    station_key : str
        Station key from stations.yaml (e.g., 'tokyo')
    year : int
        Target year
    output_dir : str
        Output directory path
    delay : float
        Request delay in seconds

    Returns
    -------
    Path or None
        Path to output file, or None if failed
    """
    converter = JMAObsdlGWOConverter(delay=delay)
    return converter.download_year_gwo(station_key, year, output_dir)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Download JMA weather data from obsdl service (GWO format)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download Tokyo 2023 data in GWO format
  python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo

  # Download multiple years
  python -m gwo_amd.jma_obsdl_downloader --year 2020 2021 2022 2023 --station osaka

  # Download multiple stations
  python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo osaka nagoya

  # Specify output directory
  python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo --output ./converted

  # List available stations
  python -m gwo_amd.jma_obsdl_downloader --list-stations

Advantages over etrn downloader:
  - Accurate RMK=6 (no phenomenon) vs RMK=2 (not observed) distinction
  - Structured quality information (no symbol parsing required)
  - Better compatibility with legacy GWO database

Output structure:
  {output_dir}/{StationName}/{StationName}{Year}.csv
  Example: gwo_data/Tokyo/Tokyo2023.csv

Format: GWO (33 columns, no header, scaled values with RMK codes)
        """,
    )

    parser.add_argument(
        "--year",
        type=int,
        nargs="+",
        help="Target year(s) to download (required unless --list-stations)",
    )

    parser.add_argument(
        "--station",
        type=str,
        nargs="+",
        help="Station key(s) from stations.yaml (case-insensitive)",
    )

    parser.add_argument(
        "--stations-config",
        type=str,
        help="Path to custom stations.yaml file",
    )

    parser.add_argument(
        "--list-stations",
        action="store_true",
        help="List available stations and exit",
    )

    parser.add_argument(
        "--output",
        type=str,
        default="gwo_data",
        help="Output directory (default: gwo_data)",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between requests in seconds (default: 1.0, minimum: 0.5)",
    )

    args = parser.parse_args()

    # Load station catalog
    station_catalog, catalog_path = load_station_catalog(args.stations_config)

    if args.list_stations:
        print_station_list(station_catalog, catalog_path)
        return

    # Validate arguments
    if not args.year:
        parser.error("--year is required (use --list-stations to list available stations)")

    if not args.station:
        parser.error("--station is required")

    # Validate stations
    for station in args.station:
        if station.lower() not in station_catalog:
            print(
                f"Error: Unknown station '{station}'. "
                f"Use --list-stations to see available stations."
            )
            sys.exit(1)

    # Download data
    converter = JMAObsdlGWOConverter(delay=args.delay)

    for station in args.station:
        station_info = station_catalog[station.lower()]
        name_jp = station_info.get("name_jp", station)
        name_en = station_info.get("name_en", station)
        print(f"\n{'#' * 20} {name_jp} / {name_en} {'#' * 20}")

        for year in args.year:
            # Print relevant remarks
            print_special_remarks(station_info, year)

            try:
                result = converter.download_year_gwo(station, year, args.output, station_catalog)
                if result:
                    print(f"  -> Saved: {result}")
            except Exception as e:
                print(f"\n[ERROR] Failed to download {station} ({year}): {e}\n")
                continue


if __name__ == "__main__":
    main()
