#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA AMeDAS hourly data downloader (obsdl).

This module downloads hourly AMeDAS observations from the JMA obsdl service and
emits per-station yearly CSVs in a 33-column GWO-compatible layout. The output
is read-compatible with the existing GWO loaders (e.g.
``metforce/io/jma_gwo.py``'s ``open_gwo_hourly``) by filling unobserved
elements with NaN and ``RMK=0`` ("observation not created").

Differences from :mod:`gwo_amd.jma_obsdl_downloader` (SYNOP/官署):

- Station IDs are ``aXXXX`` (4-digit zero-padded AMeDAS code), not ``s47XXX``.
- The obsdl AMeDAS CSV does **not** include the ``phenomenon_absent``
  ("該当現象なし") column for precipitation/sunshine — JMA documents that
  flag as SYNOP-only. The CSV therefore has 36 columns (1 datetime + 35 data),
  vs 38 for SYNOP.
- We use the per-station kansoku flag string (from ``amedas_stations.yaml``) to
  decide which elements are *physically* observed. For elements the station
  does not measure, we set value=NaN and RMK=0 directly, regardless of what
  obsdl returns. This avoids accidentally treating "instrument absent" as
  "nighttime non-observation" for sunshine/solar.

Usage::

    jma-obsdl-amd --year 2020 --bbox 138.889 33.972 141.528 36.250
    jma-obsdl-amd --year 2020 --station a0371
    jma-obsdl-amd --list-stations --bbox 138.889 33.972 141.528 36.250
"""

from __future__ import annotations

import argparse
import importlib.resources as pkg_resources
import json
import sys
import time
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pandas as pd
import yaml

from gwo_amd.jma_obsdl_downloader import (
    HOURLY_ELEMENT_IDS,
    WIND_DIR_MAP,
    JMAObsdlDownloader,
)

PACKAGE_AMEDAS_CATALOG = ("gwo_amd.data", "amedas_stations.yaml")

# Element order matches the request order, which determines the column layout
# in the AMeDAS CSV response. Each element occupies 3 columns (value, quality,
# homogeneity) — except wind which occupies 5 (speed, q, direction, q, h) —
# and AMeDAS does NOT add the phenomenon_absent column for precipitation or
# sunshine the way SYNOP does.
AMD_ELEMENT_ORDER = [
    "local_pressure",
    "sea_pressure",
    "precipitation",
    "temperature",
    "dew_point",
    "vapor_pressure",
    "humidity",
    "wind",
    "sunshine",
    "solar_radiation",
    "cloud_cover",
]

# Column index (0-based) of each element's *value* column in the AMeDAS CSV.
# Differs from SYNOP because there is no phenomenon_absent column for
# precipitation (would be col 8 in SYNOP) and sunshine (col 29 in SYNOP).
AMD_COL = {
    "datetime": 0,
    "local_pressure": 1,    # 1-3
    "sea_pressure": 4,      # 4-6
    "precipitation": 7,     # 7-9   (SYNOP would be 7-10)
    "temperature": 10,      # 10-12
    "dew_point": 13,        # 13-15
    "vapor_pressure": 16,   # 16-18
    "humidity": 19,         # 19-21
    "wind": 22,             # 22-26 (5 cols: speed, q, dir, q, h)
    "sunshine": 27,         # 27-29 (SYNOP would be 28-31)
    "solar_radiation": 30,  # 30-32
    "cloud_cover": 33,      # 33-35
}
AMD_TOTAL_COLS = 36

# kansoku flag positions controlling element availability.
# Kansoku 6-char string positions:
#   0 rain, 1 wind, 2 temp, 3 sunshine, 4 snow, 5 other (RH/pressure/dew/solar)
KANSOKU_BIT = {
    "precipitation": 0,
    "wind": 1,
    "temperature": 2,
    "sunshine": 3,
    # "other"-bit = pressure/humidity/dew/vapor/solar
    "local_pressure": 5,
    "sea_pressure": 5,
    "dew_point": 5,
    "vapor_pressure": 5,
    "humidity": 5,
    "solar_radiation": 5,
    # cloud_cover is NEVER observed by AMeDAS — fixed False below.
}


def _kansoku_observes(kansoku: str, element: str) -> bool:
    """Return True if the station's kansoku flags imply this element is observed.

    "1" = observed, "2" = estimated (treated as observed for our purposes), "0"
    = not observed. AMeDAS does not include cloud cover in any kansoku flag, so
    cloud is always False.
    """
    if element == "cloud_cover":
        return False
    if not kansoku or len(kansoku) < 6:
        return False
    bit = KANSOKU_BIT.get(element)
    if bit is None:
        return False
    return kansoku[bit] in ("1", "2")


def load_amedas_catalog(config_path: Optional[str | Path] = None) -> Tuple[dict, Path]:
    """Load amedas_stations.yaml and key entries by their slug (lower-case stid).

    Returns (catalog_dict, source_path).
    """
    if config_path:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"AMeDAS station catalog not found: {path}")
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        source = path
    else:
        package, resource = PACKAGE_AMEDAS_CATALOG
        catalog_resource = pkg_resources.files(package).joinpath(resource)
        with catalog_resource.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        source = Path(f"package://{package}/{resource}")

    stations = data.get("stations", {}) or {}
    return {key.lower(): info for key, info in stations.items()}, source


def filter_by_bbox(
    catalog: dict,
    west: float,
    south: float,
    east: float,
    north: float,
    *,
    include_categories: Optional[Sequence[str]] = None,
    include_terminated: bool = False,
) -> dict:
    """Filter a catalog dict to entries inside [west, east] × [south, north].

    Parameters
    ----------
    include_categories
        If given, only stations in these categories are kept (e.g.
        ``("kan", "shi", "san")`` to skip rainfall-only stations).
    include_terminated
        If False (default), stations marked ``terminated: True`` are dropped.
    """
    out: dict = {}
    for key, info in catalog.items():
        lat = info.get("latitude")
        lon = info.get("longitude")
        if lat is None or lon is None:
            continue
        if not (west <= lon <= east and south <= lat <= north):
            continue
        if not include_terminated and info.get("terminated", False):
            continue
        if include_categories is not None and info.get("category") not in include_categories:
            continue
        out[key] = info
    return out


# ---------------------------------------------------------------------------
# AMeDAS row → GWO row converter
# ---------------------------------------------------------------------------


class JMAObsdlAmdConverter:
    """Convert AMeDAS hourly obsdl CSV rows into the 33-column GWO layout.

    The 33-column GWO format (no header) is:

      0: station_id
      1: station_name (Japanese)
      2: station_id (duplicate)
      3-6: year, month, day, hour (1..24)
      7-8 : local_pressure, RMK
      9-10: sea_pressure,   RMK
      11-12: temperature,   RMK
      13-14: vapor_pressure, RMK
      15-16: humidity,      RMK
      17-18: wind_dir,      RMK
      19-20: wind_speed,    RMK
      21-22: cloud,         RMK   (always NaN/RMK=0 for AMeDAS)
      23-24: weather,       RMK   (always None/RMK=2)
      25-26: dew_point,     RMK
      27-28: sunshine,      RMK
      29-30: solar,         RMK
      31-32: precipitation, RMK

    Numeric scaling matches the legacy GWO (×10 for pressure/temp/wind/sunshine
    in 0.1 units, ×100 for solar in 0.01 MJ/m²).
    """

    def __init__(self, downloader: Optional[JMAObsdlDownloader] = None):
        self.downloader = downloader or JMAObsdlDownloader(delay=1.0)

    @staticmethod
    def _parse_value(val, scale: int = 1) -> Optional[float]:
        """Parse a numeric obsdl value, applying integer scaling.

        Handles the same JMA trace notations as the SYNOP path: ``0+`` (trace),
        ``10-`` (slightly less than 10).
        """
        if pd.isna(val) or val == "" or val == "--":
            return None
        try:
            val_str = str(val).strip()
            if val_str.endswith("+"):
                val_str = val_str[:-1]
            elif (
                len(val_str) > 1
                and val_str.endswith("-")
                and val_str[:-1].replace(".", "").isdigit()
            ):
                val_str = val_str[:-1]
            v = float(val_str)
            return round(v * scale)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _quality_to_rmk(quality, *, observed_by_station: bool = True) -> int:
        """Map an obsdl quality code to a GWO RMK code.

        If the station does *not* observe this element at all (per its kansoku
        flags), force RMK=0 ("observation not created"). Otherwise apply the
        same map as the SYNOP path:

          obsdl 8 → 8 (normal)
          obsdl 5 → 5 (quasi-normal)
          obsdl 4 → 5 (insufficient)
          obsdl 2 → 5 (questionable)
          obsdl 1 → 1 (missing)
          obsdl 0 → 2 (not observed: e.g. nighttime for sunshine/solar)
        """
        if not observed_by_station:
            return 0
        try:
            q = int(quality) if quality not in (None, "", "nan") else 0
        except (ValueError, TypeError):
            q = 0
        return {8: 8, 5: 5, 4: 5, 2: 5, 1: 1, 0: 2}.get(q, 8)

    def convert_to_gwo(
        self,
        df: pd.DataFrame,
        station_metadata: dict,
    ) -> Tuple[pd.DataFrame, dict]:
        """Convert an AMeDAS obsdl DataFrame to the 33-column GWO layout."""
        kansoku = station_metadata.get("kansoku", "000000")
        station_id = str(station_metadata.get("station_id"))
        name_jp = station_metadata.get("name_jp", "")

        observes = {
            elem: _kansoku_observes(kansoku, elem) for elem in AMD_ELEMENT_ORDER
        }

        stats = {
            "total_rows": 0,
            "temperature_missing": 0,
            "humidity_missing": 0,
            "wind_missing": 0,
            "precip_missing": 0,
            "precip_no_phenomenon": 0,
            "sunshine_not_observed": 0,
            "solar_not_observed": 0,
        }

        rows = []
        for _, raw in df.iterrows():
            converted = self._convert_row(raw, station_id, name_jp, observes, stats)
            if converted is not None:
                rows.append(converted)
                stats["total_rows"] += 1

        if not rows:
            return pd.DataFrame(), stats

        gwo_df = pd.DataFrame(rows)
        gwo_df = self._finalize_dtypes(gwo_df)
        return gwo_df, stats

    def _convert_row(
        self,
        row: pd.Series,
        station_id: str,
        name_jp: str,
        observes: dict,
        stats: dict,
    ) -> Optional[list]:
        # Datetime
        dt_str = str(row.iloc[AMD_COL["datetime"]])
        try:
            dt = datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(dt_str, "%Y/%m/%d %H:%M")
            except ValueError:
                return None
        # GWO encodes midnight as hour 24 of the previous day.
        if dt.hour == 0:
            prev = dt - timedelta(days=1)
            year, month, day, hour = prev.year, prev.month, prev.day, 24
        else:
            year, month, day, hour = dt.year, dt.month, dt.day, dt.hour

        def cell(idx):
            return row.iloc[idx] if idx < len(row) else ""

        # ---- Pressure ----
        local_p_obs = observes["local_pressure"]
        local_p = self._parse_value(cell(AMD_COL["local_pressure"]), 10)
        local_p_q = cell(AMD_COL["local_pressure"] + 1)
        local_p_rmk = self._quality_to_rmk(local_p_q, observed_by_station=local_p_obs)

        sea_p_obs = observes["sea_pressure"]
        sea_p = self._parse_value(cell(AMD_COL["sea_pressure"]), 10)
        sea_p_q = cell(AMD_COL["sea_pressure"] + 1)
        sea_p_rmk = self._quality_to_rmk(sea_p_q, observed_by_station=sea_p_obs)

        # ---- Precipitation (no phenomenon_absent column on AMeDAS) ----
        precip_obs = observes["precipitation"]
        precip = self._parse_value(cell(AMD_COL["precipitation"]), 10)
        precip_q = cell(AMD_COL["precipitation"] + 1)
        precip_rmk = self._quality_to_rmk(precip_q, observed_by_station=precip_obs)
        # Heuristic: AMeDAS lacks the explicit "phenomenon-absent" flag, but a
        # value of 0.0 with quality=8 unambiguously means "observed, no rain".
        # Promote to RMK=6 to mirror the SYNOP path's semantics.
        if precip_obs and precip_rmk == 8 and precip == 0:
            precip_rmk = 6
            stats["precip_no_phenomenon"] += 1
        elif precip_obs and precip_rmk == 1:
            stats["precip_missing"] += 1

        # ---- Temperature ----
        temp_obs = observes["temperature"]
        temp = self._parse_value(cell(AMD_COL["temperature"]), 10)
        temp_q = cell(AMD_COL["temperature"] + 1)
        temp_rmk = self._quality_to_rmk(temp_q, observed_by_station=temp_obs)
        if temp_obs and temp_rmk == 1:
            stats["temperature_missing"] += 1

        # ---- Dew point / vapor / humidity ----
        dew_obs = observes["dew_point"]
        dew = self._parse_value(cell(AMD_COL["dew_point"]), 10)
        dew_q = cell(AMD_COL["dew_point"] + 1)
        dew_rmk = self._quality_to_rmk(dew_q, observed_by_station=dew_obs)

        vap_obs = observes["vapor_pressure"]
        vap = self._parse_value(cell(AMD_COL["vapor_pressure"]), 10)
        vap_q = cell(AMD_COL["vapor_pressure"] + 1)
        vap_rmk = self._quality_to_rmk(vap_q, observed_by_station=vap_obs)

        rh_obs = observes["humidity"]
        rh = self._parse_value(cell(AMD_COL["humidity"]), 1)
        rh_q = cell(AMD_COL["humidity"] + 1)
        rh_rmk = self._quality_to_rmk(rh_q, observed_by_station=rh_obs)
        if rh_obs and rh_rmk == 1:
            stats["humidity_missing"] += 1

        # ---- Wind (5 cols: speed, q, dir, q, h) ----
        wind_obs = observes["wind"]
        ws = self._parse_value(cell(AMD_COL["wind"]), 10)
        ws_q = cell(AMD_COL["wind"] + 1)
        ws_rmk = self._quality_to_rmk(ws_q, observed_by_station=wind_obs)
        wd_jp = cell(AMD_COL["wind"] + 2)
        wd_q = cell(AMD_COL["wind"] + 3)
        wd_rmk = self._quality_to_rmk(wd_q, observed_by_station=wind_obs)
        wd = WIND_DIR_MAP.get(str(wd_jp).strip(), 0) if (
            not pd.isna(wd_jp) and str(wd_jp).strip()
        ) else 0
        if wind_obs and ws_rmk == 1:
            stats["wind_missing"] += 1

        # ---- Sunshine / solar ----
        sun_obs = observes["sunshine"]
        sun = self._parse_value(cell(AMD_COL["sunshine"]), 10)
        sun_q = cell(AMD_COL["sunshine"] + 1)
        sun_rmk = self._quality_to_rmk(sun_q, observed_by_station=sun_obs)

        sol_obs = observes["solar_radiation"]
        sol = self._parse_value(cell(AMD_COL["solar_radiation"]), 100)
        sol_q = cell(AMD_COL["solar_radiation"] + 1)
        sol_rmk = self._quality_to_rmk(sol_q, observed_by_station=sol_obs)

        # ---- Cloud (always not observed by AMeDAS) ----
        cloud_rmk = 0
        cloud = None

        def mask_missing(value, rmk):
            return None if rmk in (0, 1) else value

        # Sunshine/solar at observed stations: treat RMK=2 (nighttime) as
        # explicit zero — same convention as the SYNOP path. At unobserved
        # stations leave value=NaN (RMK=0).
        sunshine_value = (
            0 if (sun_obs and sun_rmk == 2)
            else mask_missing(sun, sun_rmk)
        )
        if sun_obs and sun_rmk == 2:
            stats["sunshine_not_observed"] += 1
        solar_value = (
            0 if (sol_obs and sol_rmk == 2)
            else mask_missing(sol, sol_rmk)
        )
        if sol_obs and sol_rmk == 2:
            stats["solar_not_observed"] += 1
        # Precipitation: RMK=6 → explicit zero ("no phenomenon").
        precip_value = (
            0 if precip_rmk == 6
            else mask_missing(precip, precip_rmk)
        )

        return [
            station_id,                              # 0
            name_jp,                                 # 1
            station_id,                              # 2
            year,                                    # 3
            month,                                   # 4
            day,                                     # 5
            hour,                                    # 6
            mask_missing(local_p, local_p_rmk),      # 7
            local_p_rmk,                             # 8
            mask_missing(sea_p, sea_p_rmk),          # 9
            sea_p_rmk,                               # 10
            mask_missing(temp, temp_rmk),            # 11
            temp_rmk,                                # 12
            mask_missing(vap, vap_rmk),              # 13
            vap_rmk,                                 # 14
            mask_missing(rh, rh_rmk),                # 15
            rh_rmk,                                  # 16
            mask_missing(wd, wd_rmk),                # 17
            wd_rmk,                                  # 18
            mask_missing(ws, ws_rmk),                # 19
            ws_rmk,                                  # 20
            cloud,                                   # 21
            cloud_rmk,                               # 22
            None,                                    # 23 weather (not available)
            2,                                       # 24 weather RMK
            mask_missing(dew, dew_rmk),              # 25
            dew_rmk,                                 # 26
            sunshine_value,                          # 27
            sun_rmk,                                 # 28
            solar_value,                             # 29
            sol_rmk,                                 # 30
            precip_value,                            # 31
            precip_rmk,                              # 32
        ]

    @staticmethod
    def _finalize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
        for col in [3, 4, 5, 6]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        nullable_cols = [7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31]
        for col in nullable_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        rmk_cols = [8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]
        for col in rmk_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
        return df


# ---------------------------------------------------------------------------
# High-level workflow
# ---------------------------------------------------------------------------


class JMAObsdlAmdYearDownloader:
    """End-to-end yearly AMeDAS downloader."""

    def __init__(self, delay: float = 1.0):
        self.downloader = JMAObsdlDownloader(delay=delay)
        self.converter = JMAObsdlAmdConverter(self.downloader)
        self.delay = delay

    def _build_amedas_params(
        self,
        stid: str,
        start: date,
        end: date,
    ) -> dict:
        """Same shape as the SYNOP params, but constrained to AMeDAS elements
        and with a single AMeDAS station ID."""
        elements = [[HOURLY_ELEMENT_IDS[e], ""] for e in AMD_ELEMENT_ORDER]
        ymd = [
            str(start.year), str(end.year),
            str(start.month), str(end.month),
            str(start.day), str(end.day),
        ]
        return {
            "stationNumList": json.dumps([stid]),
            "aggrgPeriod": "9",  # hourly
            "elementNumList": json.dumps(elements),
            "interAnnualType": "1",
            "ymdList": json.dumps(ymd),
            "optionNumList": json.dumps([]),
            "downloadFlag": "true",
            "rmkFlag": "1",
            "disconnectFlag": "1",  # ignored by AMeDAS but keeps SYNOP parity
            "csvFlag": "1",
            "kijiFlag": "0",
            "youbiFlag": "0",
            "fukenFlag": "0",
            "jikantaiFlag": "0",
            "jikantaiList": json.dumps([]),
            "ymdLiteral": "1",
        }

    def _download_period(
        self, stid: str, start: date, end: date
    ) -> Optional[pd.DataFrame]:
        params = self._build_amedas_params(stid, start, end)
        # Reuse the generic POST/decode/parse from JMAObsdlDownloader, which
        # accepts arbitrary params via _build_download_params; here we pass our
        # AMeDAS-specific params directly.
        try:
            resp = self.downloader.session.post(
                "https://www.data.jma.go.jp/risk/obsdl/show/table",
                data=params,
                timeout=self.downloader.timeout,
            )
            resp.raise_for_status()
            try:
                content = resp.content.decode("cp932")
            except UnicodeDecodeError:
                content = resp.content.decode("utf-8", errors="replace")
            if not content.strip() or "データがありません" in content:
                return None
            if "メンテナンス" in content:
                raise RuntimeError("JMA obsdl service is under maintenance")
            return self.downloader._parse_csv_content(content)
        except Exception as e:
            print(f"    [WARN] AMeDAS request failed for {stid}: {e}")
            return None

    def download_year(
        self,
        station_info: dict,
        year: int,
        output_dir: Path,
    ) -> Optional[Path]:
        stid = station_info["stid"]
        name_jp = station_info.get("name_jp", stid)
        slug = stid  # AMeDAS slug equals stid

        out_path = Path(output_dir) / slug
        out_path.mkdir(parents=True, exist_ok=True)
        target = out_path / f"{slug}{year}.csv"

        print(f"\n{'=' * 60}")
        print(f"AMeDAS {stid} / {name_jp} ({year}) → {target}")
        print(f"  category={station_info.get('category')} kansoku={station_info.get('kansoku')}")
        print(f"  bbox=({station_info.get('latitude')}, {station_info.get('longitude')})")

        try:
            self.downloader._init_session()
        except Exception as e:
            print(f"  [ERROR] session init failed: {e}")
            return None

        all_data: List[pd.DataFrame] = []
        for month in range(1, 13):
            _, last_day = monthrange(year, month)
            start = date(year, month, 1)
            end = date(year, month, last_day)
            print(f"  {year}/{month:02d} (1-{last_day})...", end=" ", flush=True)
            df = self._download_period(stid, start, end)
            if df is not None and len(df) > 0:
                all_data.append(df)
                print(f"OK ({len(df)} rows)")
            else:
                print("no data")
            time.sleep(self.delay)

        if not all_data:
            print(f"  [ERROR] no data for {stid} {year}")
            return None

        combined = pd.concat(all_data, ignore_index=True)
        # Pad column count if obsdl returned fewer columns than expected
        # (shouldn't happen, but guard against it).
        if combined.shape[1] < AMD_TOTAL_COLS:
            for missing in range(combined.shape[1], AMD_TOTAL_COLS):
                combined[missing] = ""
            combined = combined.reindex(columns=range(AMD_TOTAL_COLS))

        # The obsdl 'station_id' field for AMeDAS is the 4-digit code; we
        # forward it (as integer) into the GWO 'station_id' slot.
        try:
            station_id_int = int(stid.lstrip("a"))
        except ValueError:
            station_id_int = 999
        metadata = {
            "name_jp": name_jp,
            "station_id": station_id_int,
            "kansoku": station_info.get("kansoku", "000000"),
        }
        gwo_df, stats = self.converter.convert_to_gwo(combined, metadata)
        if len(gwo_df) == 0:
            print(f"  [ERROR] conversion produced 0 rows for {stid} {year}")
            return None

        gwo_df.to_csv(target, header=False, index=False, encoding="utf-8")
        self._print_report(stats, station_info, year)
        return target

    @staticmethod
    def _print_report(stats: dict, station_info: dict, year: int) -> None:
        total = stats.get("total_rows", 0)
        if total == 0:
            return
        print(f"\n  Saved {total} hourly rows for {station_info['stid']} {year}")
        print(f"  Quality summary (out of {total}):")
        ordered = [
            ("temperature_missing", "temperature missing"),
            ("humidity_missing", "humidity missing"),
            ("wind_missing", "wind missing"),
            ("precip_missing", "precipitation missing"),
            ("precip_no_phenomenon", "precip no-phenomenon (RMK=6)"),
            ("sunshine_not_observed", "sunshine RMK=2 (nighttime)"),
            ("solar_not_observed", "solar RMK=2 (nighttime)"),
        ]
        for key, label in ordered:
            n = stats.get(key, 0)
            if n:
                pct = 100.0 * n / total
                print(f"    {label}: {n} ({pct:.1f}%)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _print_station_table(stations: dict, source: Path, *, limit: Optional[int] = None) -> None:
    if not stations:
        print(f"No AMeDAS stations matched (source: {source})")
        return
    print(f"AMeDAS station catalog ({len(stations)} matched) — source: {source}")
    header = (
        f"{'stid':<7} {'name_jp':<10} {'prec':>4} "
        f"{'cat':<5} {'lat':>7} {'lon':>8} {'kansoku':<8}"
    )
    print(header)
    print("-" * len(header))
    keys = sorted(stations)
    if limit:
        keys = keys[:limit]
    for k in keys:
        s = stations[k]
        print(
            f"{s.get('stid', k):<7} {s.get('name_jp', ''):<10} "
            f"{str(s.get('prec_no', '')):>4} {s.get('category', ''):<5} "
            f"{s.get('latitude'):>7.3f} {s.get('longitude'):>8.3f} "
            f"{s.get('kansoku', ''):<8}"
        )


def _resolve_station_set(
    args: argparse.Namespace, catalog: dict
) -> dict:
    """Pick the requested subset of the catalog given CLI arguments."""
    selected: dict = {}

    if args.bbox:
        west, south, east, north = args.bbox
        cats = (
            None
            if args.include_rain_only
            else ("kan", "shi", "san", "other")
        )
        selected = filter_by_bbox(
            catalog,
            west, south, east, north,
            include_categories=cats,
            include_terminated=args.include_terminated,
        )

    if args.station:
        for stn_key in args.station:
            key = stn_key.lower()
            if key in catalog:
                selected[key] = catalog[key]
            else:
                # Allow the user to pass either the slug ("a0371") or just the
                # numeric tail ("0371", "371").
                stripped = key.lstrip("a")
                # Try padded forms
                for padded in (
                    f"a{stripped.zfill(4)}",
                    f"a{stripped.zfill(5)}",
                ):
                    if padded in catalog:
                        selected[padded] = catalog[padded]
                        break
                else:
                    print(f"  [WARN] unknown station '{stn_key}' (not in catalog)")

    if args.all_stations:
        if not args.bbox:
            selected.update(catalog)
        # bbox + all_stations is treated as bbox-only (don't expand the world).

    if args.max_stations:
        keys_sorted = sorted(selected)[: args.max_stations]
        selected = {k: selected[k] for k in keys_sorted}

    return selected


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Download JMA AMeDAS hourly data via obsdl, output GWO-compatible "
            "33-column CSVs (one file per station per year)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download every AMeDAS station inside the Tokyo Bay bbox for 2020
  jma-obsdl-amd --year 2020 \\
      --bbox 138.889 33.972 141.528 36.250 --output ./amd_data

  # One station, one year
  jma-obsdl-amd --year 2020 --station a0371

  # Multiple years
  jma-obsdl-amd --year 2019 2020 2021 \\
      --bbox 138.889 33.972 141.528 36.250

  # Just list catalog entries inside a bbox (no download)
  jma-obsdl-amd --list-stations \\
      --bbox 138.889 33.972 141.528 36.250

Output schema:
  amd_data/{stid}/{stid}{year}.csv
  33-column GWO-compatible CSV, no header. Unobserved AMeDAS elements get
  value=NaN, RMK=0 (observation not created).
""",
    )
    parser.add_argument("--year", type=int, nargs="+",
                        help="Target year(s).")
    parser.add_argument("--station", type=str, nargs="+",
                        help="AMeDAS station slug(s), e.g. a0371.")
    parser.add_argument("--bbox", type=float, nargs=4,
                        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
                        help="Bounding box filter (W S E N) in decimal degrees.")
    parser.add_argument("--all-stations", action="store_true",
                        help="Include all stations in the catalog (use with care).")
    parser.add_argument("--include-rain-only", action="store_true",
                        help="Include rain-only ('ame') and snow-only ('yuki') "
                             "stations (default: skip — only kan/shi/san/other).")
    parser.add_argument("--include-terminated", action="store_true",
                        help="Include terminated stations.")
    parser.add_argument("--max-stations", type=int, default=None,
                        help="Cap on the number of stations to download.")
    parser.add_argument("--output", type=Path, default=Path("amd_data"),
                        help="Output directory (default: ./amd_data).")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="Delay between obsdl requests (default: 1.0s, "
                             "minimum 0.5s).")
    parser.add_argument("--stations-config", type=str, default=None,
                        help="Path to a custom amedas_stations.yaml.")
    parser.add_argument("--list-stations", action="store_true",
                        help="List stations matching the filter and exit.")
    args = parser.parse_args()

    catalog, source = load_amedas_catalog(args.stations_config)
    selected = _resolve_station_set(args, catalog)

    if args.list_stations:
        _print_station_table(selected, source)
        return

    if not args.year:
        parser.error("--year is required (use --list-stations to inspect catalog).")
    if not selected:
        parser.error(
            "No stations selected. Provide --station, --bbox, or --all-stations."
        )

    yd = JMAObsdlAmdYearDownloader(delay=args.delay)
    succeeded: List[Path] = []
    failed: List[Tuple[str, int]] = []

    for stn_key in sorted(selected):
        info = selected[stn_key]
        for year in args.year:
            try:
                result = yd.download_year(info, year, args.output)
                if result:
                    succeeded.append(result)
                else:
                    failed.append((stn_key, year))
            except Exception as e:
                print(f"  [ERROR] {stn_key} {year}: {e}")
                failed.append((stn_key, year))

    print()
    print(f"Done. {len(succeeded)} succeeded, {len(failed)} failed.")
    if failed:
        for stn_key, year in failed:
            print(f"  FAILED: {stn_key} {year}")
        sys.exit(1)


if __name__ == "__main__":
    main()
