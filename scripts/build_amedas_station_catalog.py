#!/usr/bin/env python3
"""
Generate amedas_stations.yaml by scraping the JMA obsdl service.

For each prefecture (`prid`), the obsdl service returns an HTML fragment with
station markers. Each marker carries:

- ``stid``      — obsdl station ID. ``aXXXX`` for AMeDAS (4-digit zero-padded
  AMeDAS code), ``sXXXXX`` for SYNOP (``s`` + 5-digit WMO block number).
- ``stname``    — Japanese station name.
- ``prid``      — prefecture code.
- ``kansoku``   — 6-character flag string. Position semantics (matching the
  obsdl JS source):
      0: precipitation (``101``)
      1: wind (``301``)
      2: temperature (``201``)
      3: sunshine (``401``)
      4: snow (``501``/``503``)
      5: "other" — humidity/pressure/dew/vapor/solar (``605``/``601``/``602``/
         ``612``/``604``/``610``)
  Each character is ``0`` (not observed), ``1`` (observed), or ``2`` (estimated).

The HTML ``title`` attribute also includes latitude/longitude in the
``45度31.2分`` (degrees 度 / minutes 分) format which we parse to decimal.

This script writes a YAML catalog with **AMeDAS-only** entries (the SYNOP set is
already covered by ``stations.yaml``). Each entry includes the latitude and
longitude (decimal degrees), the original obsdl ``stid``, the prefecture code,
the kansoku flags, and a derived ``elements`` field listing which JMA element
IDs the station observes.

Usage::

    python scripts/build_amedas_station_catalog.py
    python scripts/build_amedas_station_catalog.py --prefectures 44 45 46
    python scripts/build_amedas_station_catalog.py --output custom.yaml
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import time
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, List

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "src" / "gwo_amd" / "data" / "amedas_stations.yaml"

OBSDL_INDEX_URL = "https://www.data.jma.go.jp/risk/obsdl/index.php"
OBSDL_STATION_URL = "https://www.data.jma.go.jp/risk/obsdl/top/station"

# Prefecture codes used by obsdl (prid). Excludes 99 (南極/Antarctica).
DEFAULT_PREFECTURES: List[str] = [
    "11", "12", "13", "14", "15", "16", "17", "18", "19", "20",
    "21", "22", "23", "24",
    "31", "32", "33", "34", "35", "36",
    "40", "41", "42", "43", "44", "45", "46",
    "48", "49", "50", "51", "52", "53", "54", "55", "56", "57",
    "60", "61", "62", "63", "64", "65", "66", "67", "68", "69",
    "71", "72", "73", "74",
    "81", "82", "83", "84", "85", "86", "87", "88",
    "91",
]

# kansoku position → JMA obsdl element IDs that the position covers.
KANSOKU_ELEMENT_MAP = {
    0: ["101"],                              # precipitation
    1: ["301"],                              # wind speed/direction
    2: ["201"],                              # temperature
    3: ["401"],                              # sunshine duration
    4: ["501", "503"],                       # snow depth, snowfall
    5: ["601", "602", "604", "605", "610",   # local/sea pressure, vapor,
         "612"],                             # humidity, solar, dew point
}

KANSOKU_LABELS = {
    0: "precipitation",
    1: "wind",
    2: "temperature",
    3: "sunshine",
    4: "snow",
    5: "other",
}

# Regex to extract station blocks. The wrapper div has the label/marker style
# and the inner div carries class="station ..." with the title and metadata
# inputs. We dedupe on stid to merge label+marker copies. The ``title``
# attribute spans multiple lines, so DOTALL is required.
STATION_RE = re.compile(
    r'class="station\b[^"]*"\s+title="(?P<title>[^"]+)"[^>]*>'
    r'\s*<input type="hidden" name="stid" value="(?P<stid>[^"]+)">'
    r'\s*<input type="hidden" name="stname" value="(?P<stname>[^"]+)">'
    r'\s*<input type="hidden" name="prid" value="(?P<prid>[^"]+)">'
    r'\s*<input type="hidden" name="kansoku" value="(?P<kansoku>[^"]+)">',
    re.DOTALL,
)

# NFKC normalization converts full-width "：" to ASCII ":". Match either.
LAT_RE = re.compile(r"北緯[:：]?\s*(\d+(?:\.\d+)?)度\s*(\d+(?:\.\d+)?)分")
LON_RE = re.compile(r"東経[:：]?\s*(\d+(?:\.\d+)?)度\s*(\d+(?:\.\d+)?)分")
ALT_RE = re.compile(r"標高[:：]?\s*(-?\d+(?:\.\d+)?)\s*m")
KANA_RE = re.compile(r"カナ\s*[:：]\s*(\S+)")


def deg_min_to_decimal(deg: float, minute: float) -> float:
    return round(deg + minute / 60.0, 4)


def fetch_prefecture(session: requests.Session, prec_no: str) -> str:
    """POST /risk/obsdl/top/station with pd=<prec_no>."""
    resp = session.post(
        OBSDL_STATION_URL,
        data={"pd": prec_no},
        timeout=60,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; GWO-AMD/0.1)",
        },
    )
    resp.raise_for_status()
    return resp.text


def parse_prefecture(html: str) -> List[Dict]:
    """Extract station metadata from a prefecture HTML fragment."""
    seen: set = set()
    stations: List[Dict] = []
    for match in STATION_RE.finditer(html):
        stid = match.group("stid")
        if stid in seen:
            continue
        seen.add(stid)
        title = match.group("title")
        title_norm = unicodedata.normalize("NFKC", title)
        lat_match = LAT_RE.search(title_norm)
        lon_match = LON_RE.search(title_norm)
        alt_match = ALT_RE.search(title_norm)
        kana_match = KANA_RE.search(title_norm)
        if not (lat_match and lon_match):
            continue
        latitude = deg_min_to_decimal(
            float(lat_match.group(1)), float(lat_match.group(2))
        )
        longitude = deg_min_to_decimal(
            float(lon_match.group(1)), float(lon_match.group(2))
        )
        altitude = float(alt_match.group(1)) if alt_match else None
        name_jp = unicodedata.normalize("NFKC", match.group("stname"))
        kana = kana_match.group(1) if kana_match else None
        kansoku = match.group("kansoku")
        terminated = "観測終了" in title_norm
        stations.append(
            {
                "stid": stid,
                "name_jp": name_jp,
                "name_kana": kana,
                "prec_no": match.group("prid"),
                "kansoku": kansoku,
                "latitude": latitude,
                "longitude": longitude,
                "altitude_m": altitude,
                "terminated": terminated,
            }
        )
    return stations


def kansoku_to_elements(kansoku: str) -> List[str]:
    """Return obsdl element IDs that the station observes (or estimates)."""
    if not kansoku or len(kansoku) < 6:
        return []
    elements: List[str] = []
    for pos, ids in KANSOKU_ELEMENT_MAP.items():
        flag = kansoku[pos]
        if flag in ("1", "2"):
            elements.extend(ids)
    return elements


def kansoku_to_class(kansoku: str) -> str:
    """Categorize the station based on its kansoku flags.

    Categories follow the ``ame_master.pdf`` 種類 column:

    - kan  : 官 — directly-observed sunshine (kansoku[3]=='1') AND humidity/
             pressure (kansoku[5]=='1'). Surface meteorological observation.
    - shi  : 四 — 4-element wired robot. rain+wind+temp+sunshine (the sunshine
             may be estimated, kansoku[3]=='2'), optionally with humidity.
    - san  : 三 — 3-element wired robot. rain+wind+temp only.
    - ame  : 雨 — rainfall only (optionally with snow depth).
    - yuki : 雪 — snow depth only.
    - other: anything else (atypical combinations).
    """
    if not kansoku or len(kansoku) < 6:
        return "unknown"
    rain = kansoku[0] in ("1", "2")
    wind = kansoku[1] in ("1", "2")
    temp = kansoku[2] in ("1", "2")
    sun_observed = kansoku[3] == "1"
    sun_any = kansoku[3] in ("1", "2")
    snow = kansoku[4] in ("1", "2")
    other = kansoku[5] in ("1", "2")

    if rain and wind and temp and sun_observed and other:
        return "kan"
    if rain and wind and temp and sun_any:
        return "shi"
    if rain and wind and temp and not sun_any and not other:
        return "san"
    if rain and not wind and not temp:
        return "ame"
    if snow and not rain and not wind and not temp:
        return "yuki"
    return "other"


def slugify(name: str, used: Dict[str, int]) -> str:
    """Produce a unique lowercase ASCII-style slug from the obsdl stid.

    AMeDAS station IDs already begin with ``a`` followed by digits, which makes
    a perfectly unique slug. We use it directly. SYNOP stations would use
    ``sXXXXX`` and we let the existing GWO catalog name them by Kname.
    """
    base = name.lower()
    if base in used:
        used[base] += 1
        return f"{base}-{used[base]}"
    used[base] = 0
    return base


def build_catalog(prefectures: Iterable[str], delay: float = 1.0) -> Dict:
    session = requests.Session()
    session.get(
        OBSDL_INDEX_URL,
        timeout=60,
        headers={"User-Agent": "Mozilla/5.0 (compatible; GWO-AMD/0.1)"},
    )

    stations_by_stid: Dict[str, Dict] = {}
    for prec_no in prefectures:
        print(f"  fetching prefecture pd={prec_no}...", flush=True)
        html = fetch_prefecture(session, prec_no)
        for st in parse_prefecture(html):
            # Catalog only AMeDAS entries; SYNOP lives in stations.yaml.
            if not st["stid"].startswith("a"):
                continue
            stations_by_stid[st["stid"]] = st
        time.sleep(max(delay, 0.5))

    used_slugs: Dict[str, int] = {}
    entries = []
    for stid in sorted(stations_by_stid):
        st = stations_by_stid[stid]
        elements = kansoku_to_elements(st["kansoku"])
        category = kansoku_to_class(st["kansoku"])
        slug = slugify(stid, used_slugs)
        entry = {
            "slug": slug,
            "stid": stid,
            "name_jp": st["name_jp"],
            "name_kana": st["name_kana"],
            "prec_no": st["prec_no"],
            "latitude": st["latitude"],
            "longitude": st["longitude"],
            "altitude_m": st["altitude_m"],
            "kansoku": st["kansoku"],
            "category": category,
            "elements": elements,
            "terminated": st["terminated"],
        }
        entries.append(entry)

    payload = {
        "metadata": {
            "generated_at": (
                dt.datetime.now(dt.timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            ),
            "source": "https://www.data.jma.go.jp/risk/obsdl/top/station",
            "prefectures": list(prefectures),
            "kansoku_position_semantics": KANSOKU_LABELS,
        },
        "stations": {
            entry["slug"]: {
                "stid": entry["stid"],
                "name_jp": entry["name_jp"],
                **({"name_kana": entry["name_kana"]} if entry["name_kana"] else {}),
                "prec_no": entry["prec_no"],
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
                **(
                    {"altitude_m": entry["altitude_m"]}
                    if entry["altitude_m"] is not None
                    else {}
                ),
                "kansoku": entry["kansoku"],
                "category": entry["category"],
                "elements": entry["elements"],
                "terminated": entry["terminated"],
            }
            for entry in entries
        },
    }
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build amedas_stations.yaml by scraping the JMA obsdl service.",
    )
    parser.add_argument(
        "--prefectures",
        nargs="+",
        default=DEFAULT_PREFECTURES,
        help="Prefecture codes to scrape (default: all of Japan).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help=f"Output YAML path (default: {OUTPUT_PATH}).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay between prefecture requests in seconds (default: 1.0).",
    )
    args = parser.parse_args()

    payload = build_catalog(args.prefectures, delay=args.delay)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(
        f"Wrote {args.output} ({len(payload['stations'])} AMeDAS stations across "
        f"{len(args.prefectures)} prefecture(s))"
    )


if __name__ == "__main__":
    main()
