# GWO-AMD

Tools for JMA (Japan Meteorological Agency) meteorological data:
1. **Convert** commercial GWO/AMD database exports (SDP format via SQLViewer7) to per-station yearly CSV files
2. **Download** recent data from JMA website (since commercial data service ended)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

## Installation

```bash
mamba env create -f environment.yml
mamba activate gwo-amd
pip install -e .
```

## 1. Converting Commercial Database (SDP → CSV)

Extract data exported from GWO/AMD databases via SQLViewer7.exe:

```bash
# Step 1: Convert multi-station SDP export to per-station CSV
jupyter notebook notebooks/GWO_multiple_stns_to_stn.ipynb

# Step 2: Split into yearly files
jupyter notebook notebooks/GWO_div_year.ipynb
```

Output structure: `{Station}/{Station}{Year}.csv` (33 columns, GWO format)

## 2. Downloading Recent Data from JMA

Since commercial data service ended, download recent data directly from JMA:

```bash
# Recommended: obsdl service (accurate RMK codes, direct GWO format)
jma-obsdl --year 2023 --station tokyo
jma-obsdl --year 2020 2021 2022 --station tokyo osaka

# Alternative: etrn service (with optional GWO conversion)
jma-download --year 2023 --station tokyo --gwo-format

# List available stations
jma-obsdl --list-stations
```

Output: `gwo_data/{Station}/{Station}{Year}.csv`

## 3. Processing GWO Data

Read and analyze GWO CSV files with automatic unit conversion:

```python
from gwo_amd.mod_class_met import Met_GWO

met = Met_GWO("2023-1-1", "2023-12-31", "Tokyo", "/path/to/GWO/Hourly")
df = met.df  # Processed DataFrame
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

| RMK | Meaning | Value |
|----:|---------|-------|
| 0 | Observation not created | NaN |
| 1 | Missing observation | NaN |
| 2 | Not observed (nighttime for solar/sunshine) | 0 |
| 6 | No phenomenon (no precipitation) | 0 |
| 8 | Normal observation | observed |

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
| Cloud/weather | 3-hour only | Interpolated for other hours |

### Unit Conversion (by `Met_GWO`)

| Parameter | GWO Unit | Converted |
|-----------|----------|-----------|
| Pressure | 0.1 hPa | hPa |
| Temperature | 0.1°C | °C |
| Wind speed | 0.1 m/s | m/s |
| Wind direction | 1-16 code | degrees |
| Solar radiation | 0.01 MJ/m²/h | W/m² |

## References

- [JMA obsdl Service](https://www.data.jma.go.jp/risk/obsdl/) - Data download with quality codes
- [JMA etrn Service](https://www.data.jma.go.jp/stats/etrn/) - Historical weather data search
- [jmadata.py (GitHub Gist)](https://gist.github.com/barusan/3f098cc74b92fad00b9bb4478da35385) - obsdl API implementation reference
- [GWO Database (Weather Toy WEB)](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)
- [JMA RMK Codes](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)

## License

MIT. Meteorological data copyright: [JMA terms](https://www.jma.go.jp/jma/kishou/info/coment.html).

---

<details>
<summary>日本語</summary>

### 目的

1. 商用GWO/AMDデータベース（SDP形式）を地点別年別CSVに変換
2. 商用データサービス終了後、気象庁WebサイトからデータをダウンロードしてGWO形式CSVを作成

### 使い方

```bash
# インストール
mamba env create -f environment.yml
mamba activate gwo-amd
pip install -e .

# データダウンロード
jma-obsdl --year 2023 --station tokyo
```

詳細は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)を参照。

</details>
