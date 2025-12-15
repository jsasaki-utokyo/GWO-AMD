# GWO-AMD

Download and process Japan Meteorological Agency (JMA) weather data, with tools for legacy GWO/AMD database compatibility.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

## Quick Start

```bash
# Install
conda env create -f environment.yml
conda activate gwo-amd
pip install -e .

# Download weather data (GWO format)
jma-obsdl --year 2023 --station tokyo

# Process existing GWO database
python -c "from gwo_amd.mod_class_met import Met_GWO; met = Met_GWO('2023-1-1', '2023-12-31', 'Tokyo', '/path/to/GWO/Hourly'); print(met.df.head())"
```

## JMA Data Download

Two CLI tools download historical hourly weather data from JMA:

| Tool | Source | Output | RMK Accuracy |
|------|--------|--------|--------------|
| `jma-obsdl` | [obsdl service](https://www.data.jma.go.jp/risk/obsdl/) | GWO format (33 cols) | High (structured quality codes) |
| `jma-download` | [etrn service](https://www.data.jma.go.jp/stats/etrn/) | JMA or GWO format | Medium (symbol parsing) |

### jma-obsdl (Recommended)

Downloads directly to GWO format with accurate RMK codes:

```bash
jma-obsdl --year 2023 --station tokyo                    # Single year
jma-obsdl --year 2020 2021 2022 --station tokyo osaka    # Multiple years/stations
jma-obsdl --list-stations                                # Show available stations
```

Output: `gwo_data/{Station}/{Station}{Year}.csv`

### jma-download

Downloads JMA format with optional GWO conversion:

```bash
jma-download --year 2023 --station tokyo                 # JMA format (20 cols)
jma-download --year 2023 --station tokyo --gwo-format    # GWO format (33 cols)
```

## GWO/AMD Database Processing

The `mod_class_met` module reads legacy GWO/AMD databases:

```python
from gwo_amd.mod_class_met import Met_GWO

met = Met_GWO("2014-1-1", "2014-6-1", "Tokyo", "/path/to/GWO/Hourly")
df = met.df  # Processed DataFrame with unit conversions
```

**Classes:**
- `Met_GWO`: Hourly data with interpolation and unit conversion
- `Met_GWO_daily`: Daily aggregated data
- `Met_GWO_check`: Data quality validation

## Data Format Reference

### GWO CSV Format (33 columns, no header)

| Col | Field | Unit | Col | Field | Unit |
|----:|-------|------|----:|-------|------|
| 1-3 | station_id, name, id2 | | 18-19 | wind_dir, rmk | 1-16 code |
| 4-7 | year, month, day, hour | | 20-21 | wind_speed, rmk | 0.1 m/s |
| 8-9 | local_pressure, rmk | 0.1 hPa | 22-23 | cloud, rmk | 0-10 |
| 10-11 | sea_pressure, rmk | 0.1 hPa | 24-25 | weather, rmk | code |
| 12-13 | temperature, rmk | 0.1°C | 26-27 | dew_point, rmk | 0.1°C |
| 14-15 | vapor_pressure, rmk | 0.1 hPa | 28-29 | sunshine, rmk | 0.1 h |
| 16-17 | humidity, rmk | % | 30-31 | solar, rmk | 0.01 MJ/m²/h |
| | | | 32-33 | precip, rmk | 0.1 mm |

### RMK (Remark) Codes

| RMK | Meaning |
|----:|---------|
| 0 | Observation not created |
| 1 | Missing observation |
| 2 | Not observed (nighttime for solar/sunshine: value=0) |
| 6 | No phenomenon (no precipitation: value=0) |
| 8 | Normal observation |

### Wind Direction Codes

| Code | Dir | Code | Dir | Code | Dir | Code | Dir |
|-----:|-----|-----:|-----|-----:|-----|-----:|-----|
| 0 | Calm | 5 | ESE | 10 | SW | 15 | NNW |
| 1 | NNE | 6 | SE | 11 | WSW | 16 | N |
| 2 | NE | 7 | SSE | 12 | W | | |
| 3 | ENE | 8 | S | 13 | WNW | | |
| 4 | E | 9 | SSW | 14 | NW | | |

### Temporal Structure

- **1961-1990**: 3-hour intervals; no sunshine/solar/precipitation
- **1991+**: 1-hour intervals
- **Cloud/weather**: 3-hour intervals only (interpolated for other hours)

## Station Catalog

152 stations defined in `src/gwo_amd/data/stations.yaml`:

```bash
jma-obsdl --list-stations              # List all stations
jma-obsdl --stations-config custom.yaml --year 2023 --station mystaton  # Custom catalog
```

## Development

```bash
# Run tests
conda activate gwo-amd
pytest

# Linting
ruff check .
ruff format .
```

## References

- [JMA Historical Weather Data](https://www.data.jma.go.jp/stats/etrn/index.php)
- [JMA obsdl Service](https://www.data.jma.go.jp/risk/obsdl/index.php)
- [JMA RMK Codes](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)
- [GWO Database (Weather Toy WEB)](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)

## License

MIT License. Meteorological data copyright belongs to JMA - see [terms of use](https://www.jma.go.jp/jma/kishou/info/coment.html).

---

<details>
<summary>日本語版 README</summary>

## GWO-AMD

気象庁の気象データをダウンロード・処理するツール。GWO/AMDデータベース形式に対応。

### 使い方

```bash
# インストール
conda env create -f environment.yml
conda activate gwo-amd
pip install -e .

# データダウンロード（GWO形式）
jma-obsdl --year 2023 --station tokyo
```

### データベースについて

- **GWO（気象データベース地上観測）**: 時別・日別データ（1961年〜）
- **AMD（アメダス）**: 自動気象観測システムデータ

詳細は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)を参照。

### 注意事項

- 2022年以降は「気象庁互換形式」（単位が異なる）
- 千葉2010-2011年の時別値に欠損行あり
- 全天日射量の単位: 1961-1980年 1cal/cm², 1981-2009年 0.1MJ/m², 2010年以降 0.01MJ/m²

</details>
