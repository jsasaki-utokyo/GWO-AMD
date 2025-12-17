# GWO-AMD

Tools for JMA (Japan Meteorological Agency) meteorological data:
1. **Download** data from JMA website using obsdl service (recommended)
2. **Convert** commercial GWO/AMD database exports (SDP format via SQLViewer7) to per-station yearly CSV files

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

## Installation

```bash
mamba env create -f environment.yml
mamba activate gwo-amd
pip install -e .
```

## 1. Downloading Data from JMA (Recommended)

Download meteorological data directly from JMA obsdl service and output in GWO format:

```bash
# Download single year/station
jma-obsdl --year 2023 --station tokyo

# Download multiple years/stations
jma-obsdl --year 2020 2021 2022 --station tokyo osaka

# Custom output directory
jma-obsdl --year 2023 --station tokyo --output ./my_data

# List available stations
jma-obsdl --list-stations
```

Output: `gwo_data/{Station}/{Station}{Year}.csv`

### Why obsdl?

The `jma-obsdl` command uses JMA's obsdl API which provides:
- **Accurate RMK codes**: Explicit quality information (not inferred from symbols)
- **Proper distinction**: Between RMK=2 (not observed) and RMK=6 (no phenomenon)
- **Direct GWO format**: No conversion needed
- **Reliable parsing**: Handles JMA's special notations (e.g., `0+`, `10-`)

### Deprecated: etrn Service

The `jma-download` command (using etrn HTML scraping) is **deprecated** but kept for legacy purposes:

```bash
# Deprecated - use jma-obsdl instead
jma-download --year 2023 --station tokyo --gwo-format
```

**Limitations of etrn**: RMK codes are inferred from display symbols (`--`, `///`, `×`), which is less accurate than obsdl's explicit quality codes.

## 2. Converting Commercial Database (SDP → CSV)

Extract data exported from GWO/AMD databases via SQLViewer7.exe:

```bash
# Step 1: Convert multi-station SDP export to per-station CSV
jupyter notebook notebooks/GWO_multiple_stns_to_stn.ipynb

# Step 2: Split into yearly files
jupyter notebook notebooks/GWO_div_year.ipynb
```

Output structure: `{Station}/{Station}{Year}.csv` (33 columns, GWO format)

## 3. Processing GWO Data

Read and analyze GWO CSV files with automatic unit conversion:

```python
from gwo_amd.mod_class_met import Met_GWO

met = Met_GWO("2023-1-1", "2023-12-31", "Tokyo", "/path/to/GWO/Hourly")
df = met.df  # Processed DataFrame with unit conversion applied
```

## Data Format

### GWO CSV Structure (33 columns, no header)

| Col | Field | Unit | Col | Field | Unit |
|----:|-------|------|----:|-------|------|
| 1-3 | station_id, name, id2 | | 18-19 | wind_dir, rmk | 0-16 |
| 4-7 | year, month, day, hour | | 20-21 | wind_speed, rmk | 0.1 m/s |
| 8-9 | local_pressure, rmk | 0.1 hPa | 22-23 | cloud, rmk | 0-10 |
| 10-11 | sea_pressure, rmk | 0.1 hPa | 24-25 | weather, rmk | code |
| 12-13 | temperature, rmk | 0.1°C | 26-27 | dew_point, rmk | 0.1°C |
| 14-15 | vapor_pressure, rmk | 0.1 hPa | 28-29 | sunshine, rmk | 0.1 h |
| 16-17 | humidity, rmk | % | 30-31 | solar, rmk | 0.01 MJ/m²/h |
| | | | 32-33 | precip, rmk | 0.1 mm |

### RMK (Remark) Codes

| RMK | Meaning | Value Handling |
|----:|---------|----------------|
| 0 | Observation not created | Missing (NaN) |
| 1 | Missing observation | Missing (NaN) |
| 2 | Not observed (nighttime for solar/sunshine) | 0 (physically correct) |
| 6 | No phenomenon (no precipitation) | 0 (physically correct) |
| 8 | Normal observation | Observed value |

### Wind Direction Codes

| Code | Dir | Code | Dir | Code | Dir | Code | Dir |
|-----:|-----|-----:|-----|-----:|-----|-----:|-----|
| 0 | Calm | 5 | ESE | 10 | SW | 15 | NNW |
| 1 | NNE | 6 | SE | 11 | WSW | 16 | N |
| 2 | NE | 7 | SSE | 12 | W | | |
| 3 | ENE | 8 | S | 13 | WNW | | |
| 4 | E | 9 | SSW | 14 | NW | | |

### Temporal Structure

| Period | Interval | Notes |
|--------|----------|-------|
| 1961-1990 | 3-hour | No sunshine/solar/precipitation |
| 1991+ | 1-hour | Full data coverage |
| Cloud/weather | 3-hour only | Linearly interpolated for other hours |

### Unit Conversion (by `Met_GWO`)

| Parameter | GWO Unit | Converted |
|-----------|----------|-----------|
| Pressure | 0.1 hPa | hPa |
| Temperature | 0.1°C | °C |
| Wind speed | 0.1 m/s | m/s |
| Wind direction | 1-16 code | degrees |
| Solar radiation | 0.01 MJ/m²/h | W/m² |

## References

- [JMA obsdl Service](https://www.data.jma.go.jp/risk/obsdl/) - Recommended data download with quality codes
- [JMA etrn Service](https://www.data.jma.go.jp/stats/etrn/) - Historical weather data search (deprecated for download)
- [jmadata.py (GitHub Gist)](https://gist.github.com/barusan/3f098cc74b92fad00b9bb4478da35385) - obsdl API implementation reference
- [GWO Database (Weather Toy WEB)](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)
- [JMA RMK Codes](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)

## License

MIT. Meteorological data copyright: [JMA terms](https://www.jma.go.jp/jma/kishou/info/coment.html).

---

<details>
<summary>日本語</summary>

### 目的

1. 気象庁obsdlサービスから気象データをダウンロードしGWO形式CSVを作成（推奨）
2. 商用GWO/AMDデータベース（SDP形式）を地点別年別CSVに変換

### 使い方

```bash
# インストール
mamba env create -f environment.yml
mamba activate gwo-amd
pip install -e .

# データダウンロード（推奨）
jma-obsdl --year 2023 --station tokyo

# 複数年・複数地点
jma-obsdl --year 2020 2021 2022 --station tokyo osaka

# 利用可能な地点一覧
jma-obsdl --list-stations
```

### なぜobsdlを使うのか？

`jma-obsdl`コマンドは気象庁のobsdl APIを使用し、以下の利点があります：
- **正確なRMKコード**: 品質情報が明示的に提供される（記号からの推測ではない）
- **適切な区別**: RMK=2（観測なし）とRMK=6（現象なし）を正しく区別
- **直接GWO形式出力**: 変換不要
- **信頼性の高い解析**: 気象庁の特殊表記（`0+`、`10-`など）に対応

### 非推奨: etrnサービス

`jma-download`コマンド（etrn HTMLスクレイピング）は**非推奨**ですが、互換性のため残されています。

詳細は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)を参照。

</details>
