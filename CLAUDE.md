# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GWO-AMD is a Japan Meteorological Agency (JMA) meteorological dataset handling tool designed to work with:
- **GWO**: Ground Weather Observatory database (気象データベース地上観測)
- **AMD**: AMeDAS database (アメダス)
- **JMA etrn**: Live weather data downloader from JMA's online service

The project includes both legacy commercial database handlers (GWO/AMD) and a modern JMA web data downloader.

## Core Commands

### Environment Setup
```bash
# Create and activate conda environment
conda env create -f environment.yml
conda activate gwo-amd

# Configure data directories
cp .env.example .env
# Edit .env to set DATA_DIR=/your/data/path

# Verify configuration
python config.py

# Or manually install dependencies
pip install -r requirements_jma_downloader.txt
pip install -e .
```

### Configuration

The project uses environment variables for data directory configuration via the `config.py` module:

- **`.env` file**: Set `DATA_DIR` and other paths (recommended)
- **Conda environment variables**: `conda env config vars set DATA_DIR=/path/to/data`
- **Shell environment**: `export DATA_DIR=/path/to/data`

See [CONFIGURATION.md](CONFIGURATION.md) for detailed setup instructions.

### Testing
```bash
# Test JMA downloader with single day data
python test_jma_downloader.py

# Test JMA downloader with weekly data
python test_jma_week.py
```

### JMA Data Download
```bash
# Using the installed console script (after pip install -e .)
# Output: jma_data/Tokyo/Tokyo2023.csv (GWO/AMD compatible structure)
jma-download --year 2023 --station tokyo

# Or using the Python module directly
python jma_weather_downloader.py --year 2023 --station tokyo

# Download multiple years
jma-download --year 2020 2021 2022 2023 --station osaka

# Download with custom station (prec_no, block_no, and English name)
jma-download --year 2023 --prec_no 44 --block_no 47662 --name 東京 --name_en Tokyo

# Specify output directory (to copy to $DATA_DIR later)
jma-download --year 2023 --station tokyo --output ./download

# Adjust request delay (default 1.0s, minimum 0.5s recommended)
jma-download --year 2023 --station tokyo --delay 0.5

# Copy downloaded data to GWO database
cp -r jma_data/* $DATA_DIR/met/JMA_DataBase/GWO/Hourly/
```

## Architecture

### Module: `mod_class_met.py`
Core meteorological data processing module with class hierarchy:

1. **`Met`** (Base Class)
   - Handles datetime ranges, station selection, directory paths
   - Defines remark (RMK) codes for data quality (0-9)
   - `set_missing_values()`: Converts RMK-flagged data to NaN based on quality codes

2. **`Met_GWO`** (Hourly Data - extends `Met`)
   - Reads GWO hourly CSV files (station/year structure: `{station}/{station}{year}.csv`)
   - Handles temporal gaps: 3-hour intervals (≤1990) vs 1-hour intervals (1991+)
   - Missing value handling: RMK-based (RMK=0,1,2 indicate various types of missing/unreliable data)
   - Unit conversions: 0.1hPa→hPa, 0.1°C→°C, wind direction 1-16→degrees, radiation 0.01MJ/m²/h→W/m²
   - Interpolation: `_df_interp()` creates 1-hour uniform time series from 3-hour data
   - Missing row detection: `_check_fill_missing_rows()` fills datetime gaps
   - Properties expose: `df_org` (raw), `df_interp` (interpolated), `df` (1H uniform)

3. **`Met_GWO_check`** (Quality Check - extends `Met_GWO`)
   - Validates data integrity, checks for missing rows (e.g., Chiba 2010-2011 had missing rows)
   - Use when data quality needs verification before processing

4. **`Met_GWO_daily`** (Daily Data - extends `Met`)
   - Processes daily aggregated values
   - Special handling for solar radiation unit changes: 1961-1980 (1 cal/cm²), 1981+ (0.1 MJ/m²)
   - Minimum sea level pressure adjustment: 1961-2002 values >10000 have 10000 subtracted

5. **`Data1D` / `Data1Ds`** (Plotting Utilities)
   - Scalar and vector data organization for time series
   - `Data1D`: Handles both scalar (e.g., temperature) and vector (e.g., wind u,v) data
   - Automatic dtype detection based on whether `col_2` is provided

6. **`Plot1D`** (Visualization)
   - Time series plotting with rolling mean windows (must be odd integers)
   - Quiver plots for wind vectors
   - Matplotlib-based with extensive customization via `Data1D_PlotConfig`

### Module: `jma_weather_downloader.py`
Downloads live hourly weather data from JMA's etrn web service:

- **Target URL**: `https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php`
- **Station presets**: tokyo, yokohama, chiba, osaka, nagoya, fukuoka, sapporo (with English names for directory structure)
- **Parameters**: `prec_no` (prefecture code), `block_no` (station code)
- **Output structure**: GWO/AMD compatible format
  - Directory: `{output_dir}/{StationName}/`
  - Filename: `{StationName}{Year}.csv`
  - Example: `jma_data/Tokyo/Tokyo2023.csv`
- **Encoding**: UTF-8-BOM for Excel compatibility
- **Rate limiting**: Day-by-day downloads with configurable delay (default 1.0s)
- **Retry logic**: Exponential backoff (2^attempt) up to 3 attempts

Key functions:
- `download_daily_hourly_data()`: Fetches single day, uses pandas `read_html()` to parse tables
- `download_yearly_data()`: Iterates through all days in year, concatenates monthly data, saves in GWO-compatible structure

Station configuration format (STATIONS dictionary):
- `name`: Japanese name (display)
- `name_en`: English name (used for directory/filename)
- `prec_no`: Prefecture code
- `block_no`: Station code

## Data Formats and Units

### GWO/AMD CSV Structure
- Station/year directory structure: `{dirpath}/{station}/{station}{year}.csv`
- Two data formats exist:
  - Pre-2022: Original GWO database units (requires unit conversion)
  - 2022+: JMA-compatible format (already in standard units)

### RMK (Remark) Codes
Critical for data quality assessment:
- **0**: Observation value not created
- **1**: Missing observation
- **2**: Not observed (e.g., nighttime for solar radiation)
- **3**: Daily extreme value below true value / estimated value with no phenomenon
- **4**: Daily extreme value above true value / uses regional meteorological observation data
- **5**: Contains estimated values / 24-hour average includes missing values
- **6**: No corresponding phenomenon (precipitation, sunshine, snowfall, snow depth, minimum sea level pressure)
- **7**: Daily extreme occurred on previous day
- **8**: Normal observation value
- **9**: Daily extreme occurred on next day / Auto-retrieved value from 80-type ground meteorological observation equipment (until 1990)

### Unit Conversions in `Met_GWO._unit_conversion()`
- Pressure: 0.1hPa → hPa (÷10)
- Temperature: 0.1°C → °C (÷10)
- Humidity: % → 0-1 (÷100)
- Wind direction: 1-16 code → degrees (formula: `(-90 - val*22.5) % 360`)
- Wind speed: 0.1m/s → m/s (÷10)
- Cloud cover: 0-10 → 0-1 (÷10)
- Sunshine hours: 0.1h → h (÷10)
- Solar radiation: 0.01MJ/m²/h → W/m² (×10000÷3600)

## Important Implementation Notes

### Temporal Data Handling
- **1961-1990**: 3-hour intervals (03:00, 06:00, ..., 00:00 next day), no sunshine/solar/precipitation data
- **1991+**: 1-hour intervals (01:00, 02:00, ..., 00:00 next day)
- Cloud cover and weather codes are always 3-hour intervals (3-hour, 6-hour, ..., 21-hour)
- Pandas datetime index: Hours are 0-23, but original GWO data uses 1-24 (00:00 represents hour 24 of previous day)

### Missing Value Strategy
- Use RMK columns to identify data quality issues
- For solar radiation (`slht`) and daylight (`lght`): RMK=2 is valid (nighttime), only 0,1 are missing
- For cloud cover (`clod`) and weather (`tnki`): RMK=0,1,2 all indicate missing data
- Missing rows (entire datetime entries) are filled with value=NaN and RMK=0

### File Encoding
- All CSV outputs use UTF-8 encoding
- `nkf` command used to enforce Linux LF line endings (compatibility requirement)

## Development Workflows

### Working with GWO/AMD Database
The Jupyter notebooks process commercial database exports:

1. **GWO_multiple_stns_to_stn.ipynb**: Extract per-station CSVs from SqlView7.exe multi-station export
2. **GWO_div_year.ipynb**: Split station CSVs into yearly files
3. **run_hourly_met.ipynb**: Plot and analyze hourly meteorological data (imports `mod_class_met.py`)
4. **run_daily_met.ipynb**: Process daily aggregated data

Directory path pattern expected:
```
{dirpath}/
  ├── {station}/
  │   ├── {station}1990.csv  # 3-hour data
  │   ├── {station}1991.csv  # 1-hour data
  │   ├── {station}2022.csv  # JMA-compatible format
  │   └── ...
```

### Working with JMA Downloader
Files are self-contained Python scripts. When modifying:

- Respect server load: minimum 0.5s delay between requests
- Account for leap years in `monthrange()` usage
- Handle missing data gracefully (some dates may have no observations)
- UTF-8-BOM encoding is critical for Japanese characters in Excel compatibility

## Special Considerations

### Data Quality Issues
- **Chiba 2010-2011**: Known missing rows in hourly data (use `Met_GWO_check` to detect similar issues)
- **Sea level pressure 1961-2002**: Values ≥10000 need +10000 correction
- **Solar radiation units**: Discontinuity at 1961/1981/2010 boundaries due to sensor/unit changes

### Coordinate Systems
- Wind directions use mathematical convention: degrees counter-clockwise from East (West=180°, North=90°)
- Wind vectors stored as `(u, v)` components calculated from speed and direction

### JMA etrn Service Limitations
- One year (365 days × 1s delay) ≈ 6-10 minutes download time
- No official API; relies on HTML table scraping via `pd.read_html()`
- Station codes found at: https://www.data.jma.go.jp/stats/etrn/index.php
- Service may return empty tables for non-existent station/date combinations
