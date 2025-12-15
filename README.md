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

**GWO CSV**: 33 columns, no header, scaled values (pressure ×10, temperature ×10, etc.)

**RMK codes**: 0=not created, 1=missing, 2=not observed (value=0 for nighttime), 6=no phenomenon (value=0), 8=normal

**Temporal**: 1961-1990 3-hour intervals, 1991+ hourly; cloud/weather always 3-hourly (interpolated)

## References

- [JMA obsdl](https://www.data.jma.go.jp/risk/obsdl/) / [JMA etrn](https://www.data.jma.go.jp/stats/etrn/)
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
