# GWO-AMD

A comprehensive toolkit for handling Japan Meteorological Agency (JMA) meteorological datasets, including legacy commercial databases (GWO/AMD) and modern web data download capabilities.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)

## Overview

GWO-AMD provides tools for working with three types of JMA meteorological data:

- **GWO (Ground Weather Observatory)** - 気象データベース地上観測: Legacy commercial database with hourly and daily ground observations
- **AMD (AMeDAS)** - アメダス: Automated Meteorological Data Acquisition System database
- **JMA etrn Web Downloader**: Modern tool to download hourly meteorological data from JMA's online service

## Quick Start

### Installation

```bash
# Create conda environment (recommended)
conda env create -f environment.yml
conda activate gwo-amd

# Or install with pip
pip install -e .
```

### Data Directory Configuration

Configure data paths using environment variables (recommended):

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your paths
# DATA_DIR=/mnt/d/Data

# Verify configuration
python config.py
```

See [CONFIGURATION.md](CONFIGURATION.md) for detailed configuration options.

### Basic Usage

```bash
# Download JMA weather data
jma-download --year 2023 --station tokyo

# Or use Python directly
python jma_weather_downloader.py --year 2023 --station tokyo

# Process GWO/AMD data with Python
python
>>> from mod_class_met import Met_GWO
>>> met = Met_GWO("2014-1-1", "2014-6-1", "Tokyo", "/path/to/data/")
>>> df = met.df  # Get processed DataFrame
```

## Features

### JMA Web Data Downloader

Downloads historical hourly weather data directly from [JMA's etrn service](https://www.data.jma.go.jp/stats/etrn/index.php).

**Key Features:**
- Preset stations: Tokyo, Yokohama, Chiba, Osaka, Nagoya, Fukuoka, Sapporo
- Custom station support via `prec_no` (prefecture code) and `block_no` (station code)
- Bulk downloads for multiple years
- Automatic retry with exponential backoff
- Configurable delay to reduce server load (default: 1.0s, minimum 0.5s recommended)

**Available Data:**
- Atmospheric pressure (local and sea level)
- Precipitation
- Temperature and dew point temperature
- Vapor pressure and humidity
- Wind direction and speed
- Sunshine duration
- Solar radiation
- Snowfall and snow depth
- Weather conditions and cloud cover
- Visibility

**Usage Examples:**

```bash
# Download single year (creates: jma_data/Tokyo/Tokyo2023.csv)
# Station names are case-insensitive: tokyo, Tokyo, TOKYO all work
jma-download --year 2023 --station tokyo

# Download multiple years
jma-download --year 2020 2021 2022 2023 --station osaka

# Custom station with prefecture and block codes
jma-download --year 2023 --prec_no 44 --block_no 47662 --name 東京 --name_en Tokyo

# Specify output directory (to copy to $DATA_DIR later)
jma-download --year 2023 --station tokyo --output ./download

# Adjust request delay (seconds)
jma-download --year 2023 --station tokyo --delay 0.5

# Download with GWO format conversion (legacy database compatible)
jma-download --year 2021 --station tokyo --gwo-format
```

### Format Conversion: JMA to GWO

The downloader can automatically convert downloaded data from the modern JMA format to the legacy GWO format for compatibility with existing databases and analysis tools.

**Why Convert?**
- JMA changed data format in 2022 (20 columns with headers vs. 33 columns without headers)
- Cloud cover data became sparse (only at 3-hour intervals)
- Wind direction changed from numeric codes (1-16) to Japanese text (北, 南東, etc.)
- Units changed from scaled values (×10) to direct values

**Conversion Features:**
- **Format transformation**: 20 columns → 33 columns, removes headers
- **Wind direction mapping**: Japanese text (北西, 南東, etc.) → GWO codes (1-16)
- **Unit conversion**: Direct values (hPa, °C, m/s) → Scaled values (×0.1)
- **Cloud cover interpolation**: Linear interpolation for missing hourly values
- **RMK code generation**: Proper remark codes (8=observed, 2=not observed, 1=missing)
- **Complete compatibility**: Output matches legacy GWO database format exactly

**Usage:**

```bash
# Download and convert to GWO format
jma-download --year 2021 --station tokyo --gwo-format

# Convert multiple years for direct integration
jma-download --year 2020 2021 2022 2023 --station tokyo --gwo-format --output ./converted

# Copy converted data directly to GWO database
cp -r ./converted/* $DATA_DIR/met/JMA_DataBase/GWO/Hourly/
```

**Format Comparison:**

| Feature | JMA Format (default) | GWO Format (--gwo-format) |
|---------|---------------------|---------------------------|
| Columns | 20 | 33 |
| Headers | Yes (2 rows) | No |
| Pressure | 1008.4 hPa | 10084 (×10) |
| Temperature | 15.3°C | 153 (×10) |
| Wind direction | 北西 (text) | 14 (code) |
| Cloud cover | Sparse, "0+" (text) | Interpolated, 0-10 (numeric) |
| No phenomenon | "--" (converted to 0 with RMK=2) | 0 with RMK=2 |
| Missing value | "///" or "×" (RMK=1) | RMK=1 (value omitted) |
| Weather code | Not available | 0 with RMK=2 |

**Wind Direction Mapping:**

| Japanese | Code | Direction | Japanese | Code | Direction |
|----------|------|-----------|----------|------|-----------|
| 北 | 16 | N | 南 | 8 | S |
| 北北東 | 1 | NNE | 南南西 | 9 | SSW |
| 北東 | 2 | NE | 南西 | 10 | SW |
| 東北東 | 3 | ENE | 西南西 | 11 | WSW |
| 東 | 4 | E | 西 | 12 | W |
| 東南東 | 5 | ESE | 西北西 | 13 | WNW |
| 南東 | 6 | SE | 北西 | 14 | NW |
| 南南東 | 7 | SSE | 北北西 | 15 | NNW |
| 静穏 | 0 | Calm | | | |

**Cloud Cover Interpolation Example:**

```
Original JMA data (3-hour intervals):
  Hour 03: 8 (observed)
  Hour 04: -- (missing)
  Hour 05: -- (missing)
  Hour 06: 2 (observed)

Converted GWO data (interpolated):
  Hour 03: 8, RMK=8 (observed)
  Hour 04: 6, RMK=2 (interpolated)
  Hour 05: 4, RMK=2 (interpolated)
  Hour 06: 2, RMK=8 (observed)
```

**Output Structure (GWO/AMD Compatible):**

Downloaded data follows the same structure as GWO/AMD databases:
```
{output_dir}/
  └── {StationName}/
      ├── {StationName}2020.csv
      ├── {StationName}2021.csv
      └── {StationName}2023.csv

Example: jma_data/Tokyo/Tokyo2023.csv
```

This makes it easy to copy downloaded data into your existing GWO database:
```bash
# After downloading
cp -r jma_data/* $DATA_DIR/met/JMA_DataBase/GWO/Hourly/
```

### Station Catalog

`stations.yaml` lists every supported GWO/AMD station (currently 152 entries) with `prec_no`, `block_no`, coordinates, and time-bounded remarks derived from `gwo_stn.csv`, `smaster.index`, and `ame_master.pdf`. Use these helpers to explore or customize the catalog:

- Show all keys and metadata: `python jma_weather_downloader.py --list-stations`
- Point to a custom catalog: `python jma_weather_downloader.py --stations-config my_stations.yaml ...`
- Regenerate the default catalog after editing source CSVs: `python scripts/build_station_catalog.py`

When you download data, the script automatically prints any special remarks whose date ranges intersect the requested year so you know about relocations or instrumentation changes that might affect the dataset.

**Quick sanity check**  
After creating/activating the `gwo-amd` conda environment, you can verify the catalog wiring without downloading data:

```bash
conda run --no-capture-output -n gwo-amd python jma_weather_downloader.py --list-stations | head
```

### GWO/AMD Database Processing

The `mod_class_met.py` module provides comprehensive classes for processing legacy commercial meteorological databases.

**Core Classes:**

- **`Met_GWO`**: Hourly data processing with automatic interpolation and unit conversion
  - Handles temporal gaps (3-hour data ≤1990, 1-hour data 1991+)
  - RMK-based quality control (remark codes 0-9)
  - Missing value detection and interpolation

- **`Met_GWO_check`**: Data quality validation (e.g., detects missing rows)

- **`Met_GWO_daily`**: Daily aggregated data processing
  - Special handling for solar radiation unit changes (1961/1981/2010)
  - Sea level pressure corrections (1961-2002)

- **`Data1D` / `Plot1D`**: Time series visualization with scalar/vector support

**Python Usage:**

```python
from mod_class_met import Met_GWO

# Load hourly data
met = Met_GWO(
    datetime_ini="2014-1-1 00:00:00",
    datetime_end="2014-6-1 00:00:00",
    stn="Tokyo",
    dirpath="/path/to/JMA_DataBase/GWO/Hourly/"
)

# Access DataFrames
df_original = met.df_org        # Raw data
df_interpolated = met.df_interp # Interpolated at original frequency
df_hourly = met.df              # Uniform 1-hour intervals

# Export to CSV
met.to_csv(df_hourly, "./tokyo_2014.csv")
```

### Jupyter Notebook Tools

- **`GWO_multiple_stns_to_stn.ipynb`**: Extract per-station CSV files from SQLViewer7.exe exports
- **`GWO_div_year.ipynb`**: Split station CSV files into yearly files
- **`run_hourly_met.ipynb`**: Plot and analyze hourly meteorological data
- **`run_daily_met.ipynb`**: Process daily aggregated data
- **`dev_class_met.ipynb`**: Development and testing notebook

## Data Format Notes

### JMA Data Format History

The Japan Meteorological Agency and its data providers have used three distinct format periods:

1. **Pre-2010 (Original GWO format)**
   - 3-hour intervals for 1961-1990
   - 33 columns, no headers
   - Limited data availability (no sunshine/solar/precipitation before 1991)

2. **2010-2021 (Modified GWO format)**
   - 1-hour intervals
   - 33 columns, no headers
   - Scaled values (×0.1 for most parameters)
   - Wind direction as numeric codes (1-16)
   - Complete data coverage

3. **2022+ (JMA-compatible format / 気象庁互換形式)**
   - 1-hour intervals
   - 20 columns with Japanese headers
   - Direct values (hPa, °C, m/s - no scaling)
   - Wind direction as Japanese text (北, 南東, etc.)
   - Sparse cloud cover data (3-hour intervals only)
   - Symbols: `--` = phenomenon did not occur (value 0), `×` / `///` = missing observation, `#` = questionable

The `jma_weather_downloader.py` tool downloads data in the modern JMA format (2022+) by default, but can convert to legacy GWO format (2010-2021 compatible) using the `--gwo-format` option.

### RMK (Remark) Codes

Quality control codes (0-9) indicate data reliability:

- **0**: Observation value not created
- **1**: Missing observation
- **2**: Not observed (e.g., nighttime for solar radiation)
- **3**: Daily extreme value below true value / estimated value
- **4**: Daily extreme value above true value / uses regional data
- **5**: Contains estimated values / 24-hour average includes missing values
- **6**: No corresponding phenomenon occurred
- **7**: Daily extreme occurred on previous day
- **8**: Normal observation value (reliable)
- **9**: Daily extreme occurred on next day / auto-retrieved value (≤1990)

See [JMA's official documentation](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html) for details.

### Temporal Data Structure

- **1961-1990**: 3-hour intervals (03:00, 06:00, ..., 00:00); no sunshine/solar/precipitation data
- **1991+**: 1-hour intervals (01:00, 02:00, ..., 00:00)
- **Cloud cover/weather**: Always 3-hour intervals (03:00, 06:00, ..., 21:00)

### Unit Conversions

The `Met_GWO` class automatically converts units:

| Parameter              | Original Unit    | Converted Unit |
|------------------------|------------------|----------------|
| Pressure               | 0.1 hPa          | hPa            |
| Temperature            | 0.1°C            | °C             |
| Humidity               | %                | 0-1            |
| Wind direction         | 1-16 code        | degrees (0-360)|
| Wind speed             | 0.1 m/s          | m/s            |
| Cloud cover            | 0-10             | 0-1            |
| Sunshine hours         | 0.1 h            | h              |
| Solar radiation        | 0.01 MJ/m²/h     | W/m²           |

### Special Considerations

**Solar Radiation Units (Daily Data):**
- 1961-1980: 1 cal/cm²
- 1981-2009: 0.1 MJ/m²
- 2010+: 0.01 MJ/m²

**Sea Level Pressure (1961-2002):**
- Values ≥10000 have 10000 subtracted; add 10000 for correction

**Known Data Issues:**
- Chiba 2010-2011: Missing rows in hourly data (use `Met_GWO_check` for validation)

## Testing

```bash
# Test JMA downloader with single day
python test_jma_downloader.py

# Test weekly data download
python test_jma_week.py

# Verify converted GWO data against original database
python verify_gwo_conversion.py jma_data/Tokyo/Tokyo2019.csv $DATA_DIR/met/JMA_DataBase/GWO/Hourly/Tokyo/Tokyo2019.csv
```

### Verification Script

The `verify_gwo_conversion.py` script compares converted JMA data with original GWO database files to ensure accuracy:

```bash
# Usage
python verify_gwo_conversion.py <converted_file> <original_file>

# Example
python verify_gwo_conversion.py jma_data/Tokyo/Tokyo2019.csv /path/to/GWO/Hourly/Tokyo/Tokyo2019.csv
```

**Features:**
- Column-by-column comparison of all 33 GWO format columns
- Identifies core data matches (pressure, temperature, humidity, wind)
- Detects known bugs in original GWO data (cloud interpolation)
- Issues warnings that disappear when original data is corrected
- Accounts for expected differences (weather codes not in JMA format)

**Known Bug in Original GWO Data:**

The original GWO database has a bug where **cloud cover is not interpolated** between 3-hour observation intervals (03:00, 06:00, 09:00, etc.). Instead, it sets `cloud=0` with `RMK=2` for non-observation hours.

The converter **correctly interpolates** cloud values, providing better data continuity. For example:
- Hour 03: cloud=8 (observed)
- Hour 04: cloud=6 (interpolated) ← Original GWO has 0 here (bug)
- Hour 05: cloud=4 (interpolated) ← Original GWO has 0 here (bug)
- Hour 06: cloud=2 (observed)

The verification script will issue a warning about this bug, which will disappear once you correct the original GWO CSV files with proper interpolation.

## Documentation

For detailed implementation guidance, see [CLAUDE.md](CLAUDE.md).

For Japanese documentation on the JMA downloader, see [JMA_DOWNLOADER_README.md](JMA_DOWNLOADER_README.md).

## About GWO/AMD Databases

The GWO (Ground Weather Observatory) and AMD (AMeDAS) databases are legacy commercial products from the Japan Meteorological Business Support Center. While no longer sold, purchasers can access support information at [Weather Toy WEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/).

- [GWO Database Details](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)
- [AMD Database Details](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)
- [More Information](https://estuarine.jp/2016/05/gwo/)

**Note**: The 2022+ data from Weather Toy WEB uses "JMA-compatible format" (気象庁互換形式) with different units than earlier data. The `mod_class_met.py` module handles both formats.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

**Note**: Meteorological data copyright belongs to the Japan Meteorological Agency. Please comply with [JMA's terms of use](https://www.jma.go.jp/jma/kishou/info/coment.html).

## References

- [JMA Historical Weather Data Search](https://www.data.jma.go.jp/stats/etrn/index.php)
- [JMA Data Remark Codes](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)
- [JMA Website Terms of Use](https://www.jma.go.jp/jma/kishou/info/coment.html)

## Author

Jun Sasaki (coded on 2017-09-09, updated on 2024-07-02)

---

<details>
<summary><b>日本語版 README (Original Japanese README)</b></summary>

# GWO-AMD
[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) and [AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/) GWO-AMD is a Japan Meteorological Agency's meteorological dataset handling tool.

## 気象庁互換形式
- 2022年のデータもウェザートーイWEBのサポートで配布されていますが，気象庁互換形式です．値欄に数値以外の記号が含まれており，要注意です．
- [**値欄の情報**](https://www.data.jma.go.jp/obd/stats/data/mdrr/man/remark.html)

## 気象データベース地上観測（GWO）とアメダス（AMD）の準備
- 気象データベース地上観測（GWO）およびアメダス（AMD）から**SQLViewer7.exe**で切り出した，全地点全期間（ただし，1990年以前と1991年以降の2つのファイルに分割）のCSVファイルを読み込み，観測点別年別のCSVファイルとして切り出す，**Jupyter Notebook**を用意しました．
- 切り出したCSVの単位は元のデータベースの単位です．[**気象庁互換**](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_11.html)はわかりやすいですが，2022年度以降に採用することとします．すなわち，地点別年別のCSVファイルの形式は2021年以前と2022年以降で異なっており，これらを読み込むコードで対応する方針とします．これは過去の蓄積を最大限生かすためです．この読み込むコードはmod_class_met.pyです．
- [**気象庁互換**](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_11.html)は最新の気象庁WEBで公開されており，換算不要のわかりやすい単位です．
- GWOには対応していますが，他は未完成です．
- これは商用データベースで，既に販売は終了していますが，購入者は[ウェザートーイWEB](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/)でサポート情報を入手できます．詳細は[こちら](https://estuarine.jp/2016/05/gwo/)を参照ください．
- データの詳細は[GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)および[AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)を参照ください．

## データベースの詳細情報

### [GWO](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top5_1.htm)
#### [日別データベース](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/gwodb.htm#2_1)

- 全天日射量の単位に付いての注意

```
1961年～1980年  1 cal/c㎡
1981年～2009年  0.1MJ/㎡
2010年以降は    0.01MJ/㎡
```
- 最低海面気圧の注意
```
1961年～2002年では、10000以上は、10000引かれています
（オンラインデータの2003年～2005年も10000以上は、10000引かれています）
```

#### [時別データベース](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/gwodb.htm#2_2)
```
◇１９６１年～１９９０年　３時間置きです
(※1)ただしこの期間の日照時間、全天日射量、降水量のデータはありません。
◇１９９１年～２０ｎｎ年　１時間置きです
◇雲量／現在天気は、3時～21時で3時間置きです
```

### [AMD](http://www.roy.hi-ho.ne.jp/ssai/mito_gis/top2_1.htm)

準備中

## 使い方
- **GWO_multiple_stns_to_stn.ipynb**で，SqlView7.exeで切り出した全観測点全期間のCSVファイルを読み込み，観測点別のCSVファイルとして，指定されたディレクトリに出力する．
- **GWO_div_year.ipynb**で，観測点別ディレクトリに年別CSVファイルとして出力する．
- 詳細はそれぞれのJupyter Notebookを参照ください．

## 注意
- **2019/01/11:** 千葉の2010年，2011年の時別値CSVデータファイルに欠損行があったので，欠損行をチェックするclass Met_GWO_check(Met_GWO)を**mod_class_met.py**に追加した．
- 詳細は../GWO/Hourly/Chiba/readme.txt を参照（GitHubには無し）
- Since there were missing rows in the time series CSV data files for Chiba in 2010 and 2011, a class of Met_GWO_check (Met_GWO) is added in **mod_class_met.py** to check such missing rows.

## Plotツール
- 簡単なプロットツール **run_hourly_met.ipynb** を用意しました．**mod_class_met.py**を読み込みます．
- A simple GWO hourly meteorological data plotting and processing tool of **run_hourly_met.ipynb** is prepared, which imports **mod_class_met.py**.
- Hourly data directory path should be given:
```bash
dirpath = "/mnt/d/dat/met/JMA_DataBase/GWO/Hourly/"
```

</details>
