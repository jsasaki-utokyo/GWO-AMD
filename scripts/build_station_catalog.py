#!/usr/bin/env python3
"""
Generate stations.yaml from gwo_stn.csv and smaster.index.

The resulting YAML powers jma_weather_downloader.py by providing
prec_no/block_no metadata and station-specific remarks.
"""

from __future__ import annotations

import csv
import datetime as dt
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

import yaml

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "gwo_stn.csv"
SMASTER_PATH = ROOT / "smaster.index"
OUTPUT_PATH = ROOT / "src" / "gwo_amd" / "data" / "stations.yaml"

# Prefecture / bureau codes from ame_master.pdf (page 4)
PREF_CODES = {
    "宗谷総合振興局": "11",
    "上川総合振興局": "12",
    "留萌振興局": "13",
    "石狩振興局": "14",
    "空知総合振興局": "15",
    "後志総合振興局": "16",
    "オホーツク総合振興局": "17",
    "根室振興局": "18",
    "釧路総合振興局": "19",
    "十勝総合振興局": "20",
    "胆振総合振興局": "21",
    "日高振興局": "22",
    "渡島総合振興局": "23",
    "檜山振興局": "24",
    "青森県": "31",
    "秋田県": "32",
    "岩手県": "33",
    "宮城県": "34",
    "山形県": "35",
    "福島県": "36",
    "茨城県": "40",
    "栃木県": "41",
    "群馬県": "42",
    "埼玉県": "43",
    "東京都": "44",
    "千葉県": "45",
    "神奈川県": "46",
    "長野県": "48",
    "山梨県": "49",
    "静岡県": "50",
    "愛知県": "51",
    "岐阜県": "52",
    "三重県": "53",
    "新潟県": "54",
    "富山県": "55",
    "石川県": "56",
    "福井県": "57",
    "滋賀県": "60",
    "京都府": "61",
    "大阪府": "62",
    "兵庫県": "63",
    "奈良県": "64",
    "和歌山県": "65",
    "岡山県": "66",
    "広島県": "67",
    "島根県": "68",
    "鳥取県": "69",
    "徳島県": "71",
    "香川県": "72",
    "愛媛県": "73",
    "高知県": "74",
    "山口県": "81",
    "福岡県": "82",
    "大分県": "83",
    "長崎県": "84",
    "佐賀県": "85",
    "熊本県": "86",
    "宮崎県": "87",
    "鹿児島県": "88",
    "沖縄県": "91",
    "島尻郡南大東村": "92",
    "島尻郡北大東村": "92",
    "宮古島市": "93",
    "宮古郡": "93",
    "石垣市": "94",
    "八重山郡": "94",
}

PREF_ALIASES = {
    "宗谷総合振興局": ["宗谷総合振興局", "宗谷支庁", "宗谷総合"],
    "上川総合振興局": ["上川総合振興局", "上川支庁", "上川総合"],
    "留萌振興局": ["留萌振興局", "留萌支庁", "留萌振興"],
    "石狩振興局": ["石狩振興局", "石狩支庁", "石狩振興"],
    "空知総合振興局": ["空知総合振興局", "空知支庁", "空知総合"],
    "後志総合振興局": ["後志総合振興局", "後志支庁", "後志総合"],
    "オホーツク総合振興局": ["オホーツク総合振興局", "網走支庁"],
    "根室振興局": ["根室振興局", "根室支庁", "根室振興"],
    "釧路総合振興局": ["釧路総合振興局", "釧路支庁", "釧路総合"],
    "十勝総合振興局": ["十勝総合振興局", "十勝支庁", "十勝総合"],
    "胆振総合振興局": ["胆振総合振興局", "胆振支庁", "胆振総合"],
    "日高振興局": ["日高振興局", "日高支庁", "日高振興"],
    "渡島総合振興局": ["渡島総合振興局", "渡島支庁"],
    "檜山振興局": ["檜山振興局", "檜山支庁", "檜山振興"],
    "青森県": ["青森県"],
    "秋田県": ["秋田県"],
    "岩手県": ["岩手県"],
    "宮城県": ["宮城県"],
    "山形県": ["山形県"],
    "福島県": ["福島県"],
    "茨城県": ["茨城県"],
    "栃木県": ["栃木県"],
    "群馬県": ["群馬県"],
    "埼玉県": ["埼玉県"],
    "千葉県": ["千葉県"],
    "東京都": ["東京都"],
    "神奈川県": ["神奈川県"],
    "長野県": ["長野県"],
    "山梨県": ["山梨県", "甲府"],
    "静岡県": ["静岡県"],
    "愛知県": ["愛知県"],
    "岐阜県": ["岐阜県"],
    "三重県": ["三重県"],
    "新潟県": ["新潟県"],
    "富山県": ["富山県"],
    "石川県": ["石川県"],
    "福井県": ["福井県"],
    "滋賀県": ["滋賀県"],
    "京都府": ["京都府", "京都"],
    "大阪府": ["大阪府", "大阪"],
    "兵庫県": ["兵庫県"],
    "奈良県": ["奈良県"],
    "和歌山県": ["和歌山県"],
    "岡山県": ["岡山県"],
    "広島県": ["広島県"],
    "島根県": ["島根県"],
    "鳥取県": ["鳥取県"],
    "徳島県": ["徳島県"],
    "香川県": ["香川県"],
    "愛媛県": ["愛媛県"],
    "高知県": ["高知県", "清水測候所足摺分室高知県"],
    "山口県": ["山口県"],
    "福岡県": ["福岡県"],
    "大分県": ["大分県"],
    "長崎県": ["長崎県"],
    "佐賀県": ["佐賀県"],
    "熊本県": ["熊本県"],
    "宮崎県": ["宮崎県"],
    "鹿児島県": ["鹿児島県"],
    "沖縄県": ["沖縄県", "南大東島地方気象台沖縄県"],
    "島尻郡南大東村": ["南大東島", "南大東村"],
    "島尻郡北大東村": ["北大東村"],
    "宮古島市": ["宮古島"],
    "宮古郡": ["宮古郡"],
    "石垣市": ["石垣島"],
    "八重山郡": ["八重山郡", "与那国島"],
}

ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical, aliases in PREF_ALIASES.items():
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias] = canonical

ALIAS_ORDER = sorted(ALIAS_TO_CANONICAL, key=len, reverse=True)

SPECIAL_PREC_OVERRIDES = {
    "minamidaitojima": "92",
    "miyakojima": "93",
    "ishigakijima": "94",
    "yonakunijima": "94",
}

DATE_CHUNK = re.compile(r"(\d{16,})(?!.*\d{16,})")
KANA_PATTERN = re.compile(r"^\d{3}\s+\d+(?:\s+\d+)?\s+(?P<kana>\S+)")


def slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return base or name.lower()


def iso_date(raw: str) -> Optional[str]:
    if not raw or raw == "00000000":
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"


def detect_pref(note: str) -> Optional[str]:
    for alias in ALIAS_ORDER:
        if alias in note:
            return ALIAS_TO_CANONICAL[alias]
    return None


def build_station_index() -> Dict[int, Dict]:
    stations: Dict[int, Dict] = {}
    slug_counts: Dict[str, int] = {}
    with CSV_PATH.open(encoding="utf-8") as handle:
        reader = csv.DictReader(row for row in handle if not row.startswith("#"))
        for row in reader:
            station_id = int(row["station_id"])
            slug = slugify(row["Kname"])
            if slug in slug_counts:
                slug_counts[slug] += 1
                slug = f"{slug}-{slug_counts[slug]}"
            else:
                slug_counts[slug] = 1
            block_no = f"{station_id + 47000:05d}"
            entry = {
                "slug": slug,
                "station_id": station_id,
                "block_no": block_no,
                "name_en": row["Kname"],
                "name_jp": row["name_jp"],
                "latitude": round(float(row["latitude"]), 4),
                "longitude": round(float(row["longitude"]), 4),
                "altitude_m": round(float(row["altitude"]), 1),
                "barometer_height_m": round(float(row["barometer_height"]), 1),
                "anemometer_height_m": round(float(row["anemometer_height"]), 1),
                "remarks": [],
            }
            stations[station_id] = entry
    return stations


def enrich_with_smaster(stations: Dict[int, Dict]) -> None:
    with SMASTER_PATH.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.rstrip("\n")
            if not line.strip():
                continue
            head = line[:3].strip()
            if not head.isdigit():
                continue
            station_id = int(head)
            entry = stations.get(station_id)
            if not entry:
                continue
            date_match = DATE_CHUNK.search(line)
            if not date_match:
                continue
            digits = date_match.group(1)
            start_raw = digits[-16:-8]
            end_raw = digits[-8:]
            prefix = digits[:-16]
            suffix = line[date_match.end():]
            text = "".join(ch for ch in suffix if not ch.isdigit())
            note = unicodedata.normalize("NFKC", text.replace("\u3000", " ").strip())
            start_date = iso_date(start_raw)
            end_date = None if end_raw == "99999999" else iso_date(end_raw)
            if note:
                remark = {
                    "start_date": start_date,
                    "end_date": end_date,
                    "note": note,
                    "source": "smaster.index",
                }
                if prefix:
                    remark["context_code"] = prefix
                entry.setdefault("remarks", []).append(remark)
                pref_name = detect_pref(note)
                if pref_name and "prefecture_jp" not in entry:
                    entry["prefecture_jp"] = pref_name
                    entry["prec_no"] = PREF_CODES[pref_name]
            if "name_kana" not in entry:
                kana_match = KANA_PATTERN.match(line)
                if kana_match:
                    entry["name_kana"] = unicodedata.normalize("NFKC", kana_match.group("kana"))


def apply_overrides(stations: Dict[int, Dict]) -> None:
    for entry in stations.values():
        slug = entry["slug"]
        if slug in SPECIAL_PREC_OVERRIDES:
            entry["prec_no"] = SPECIAL_PREC_OVERRIDES[slug]
            entry.setdefault("prefecture_jp", "沖縄県")
        if "prec_no" not in entry or "prefecture_jp" not in entry:
            raise ValueError(f"Missing prefecture info for {slug} (station_id={entry['station_id']})")


def to_yaml_payload(stations: Dict[int, Dict]) -> Dict:
    # Sort by slug for stable output
    ordered = sorted(stations.values(), key=lambda item: item["slug"])
    generated_at = (
        dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    payload = {
        "metadata": {
            "generated_at": generated_at,
            "sources": ["gwo_stn.csv", "smaster.index"],
        },
        "stations": {
            entry["slug"]: {
                "station_id": entry["station_id"],
                "block_no": entry["block_no"],
                "prec_no": entry["prec_no"],
                "name_en": entry["name_en"],
                "name_jp": entry["name_jp"],
                **({"name_kana": entry["name_kana"]} if "name_kana" in entry else {}),
                "prefecture_jp": entry["prefecture_jp"],
                "latitude": entry["latitude"],
                "longitude": entry["longitude"],
                "altitude_m": entry["altitude_m"],
                "barometer_height_m": entry["barometer_height_m"],
                "anemometer_height_m": entry["anemometer_height_m"],
                "remarks": entry.get("remarks", []),
            }
            for entry in ordered
        },
    }
    return payload


def main() -> None:
    stations = build_station_index()
    enrich_with_smaster(stations)
    apply_overrides(stations)
    payload = to_yaml_payload(stations)
    OUTPUT_PATH.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    print(f"Wrote {OUTPUT_PATH} ({len(payload['stations'])} stations)")


if __name__ == "__main__":
    main()
