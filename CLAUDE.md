# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Language conventions

- **Chat / conversational responses**: Japanese (the user's working language).
- **Written artifacts**: English only. This includes — but is not limited to —
  every `*.md` file (README, design docs, this file), all code comments and
  docstrings, commit messages, PR titles/descriptions, and any new file or
  directory name.
- Data values that are inherently Japanese (e.g. station names in YAML
  catalogs, the `name_jp` field, prefecture names embedded in domain data)
  keep their original Japanese. The surrounding code and comments stay in
  English.

This mirrors the global convention in `~/.claude/CLAUDE.md`. Restating it here
so it is explicit at the project level.

## Project Overview

GWO-AMD is a Japan Meteorological Agency (JMA) meteorological dataset handling tool:
- **GWO**: Ground Weather Observatory database (気象データベース地上観測)
- **AMD**: AMeDAS database (アメダス)
- **JMA obsdl (SYNOP)**: `jma-obsdl` — SYNOP/官署 hourly downloader (recommended)
- **JMA obsdl (AMeDAS)**: `jma-obsdl-amd` — AMeDAS hourly downloader, bbox-aware
- **JMA etrn**: `jma-download` — etrn HTML-scraping downloader (deprecated)

## Core Commands

### Environment Setup
```bash
conda env create -f environment.yml
conda activate gwo-amd
pip install -e .[dev]

# Configure data directories
cp .env.example .env  # Edit .env to set DATA_DIR
python -m gwo_amd.config  # Verify configuration
```

### Testing
```bash
# Run all tests
pytest

# Or via conda
conda run --no-capture-output -n gwo-amd pytest

# Live download tests (network-dependent, skipped by default)
RUN_LIVE_JMA_TESTS=1 pytest tests/test_manual_jma_download.py
```

### Linting
```bash
ruff check .
ruff format .
```

### JMA Data Download (Recommended: obsdl)
```bash
# Console script (GWO format output)
jma-obsdl --year 2023 --station tokyo

# Module execution
python -m gwo_amd.jma_obsdl_downloader --year 2023 --station tokyo

# Download multiple years/stations
jma-obsdl --year 2020 2021 2022 --station tokyo osaka

# Custom output directory
jma-obsdl --year 2023 --station tokyo --output ./gwo_data

# List available stations
jma-obsdl --list-stations

# Verify conversion against original GWO database
python -m gwo_amd.verify_gwo_conversion <converted_file> <original_file>
```

### JMA AMeDAS Hourly Download (`jma-obsdl-amd`)
```bash
# Bounding-box download (W S E N in decimal degrees)
jma-obsdl-amd --year 2020 --bbox 138.889 33.972 141.528 36.250

# Single AMeDAS station (slug = obsdl stid, 4-digit zero-padded)
jma-obsdl-amd --year 2020 --station a0371   # Haneda

# Multiple years
jma-obsdl-amd --year 2019 2020 2021 --bbox 138.889 33.972 141.528 36.250

# List bbox candidates without downloading
jma-obsdl-amd --list-stations --bbox 138.889 33.972 141.528 36.250

# Regenerate the AMeDAS station catalog (scrapes obsdl prefecture pages)
python scripts/build_amedas_station_catalog.py
python scripts/build_amedas_station_catalog.py --prefectures 44 45 46
```

Output: `amd_data/{stid}/{stid}{year}.csv` (33-column GWO-compatible layout).

### JMA etrn Download (Deprecated)
```bash
# Deprecated - use jma-obsdl instead
jma-download --year 2023 --station tokyo --gwo-format
```

## Architecture

### Package Structure
```
src/gwo_amd/
├── __init__.py
├── config.py                       # Environment variable configuration
├── jma_weather_downloader.py       # CLI: jma-download (etrn HTML scraping, deprecated)
├── jma_obsdl_downloader.py         # CLI: jma-obsdl (SYNOP/官署 hourly via obsdl)
├── jma_obsdl_amd_downloader.py     # CLI: jma-obsdl-amd (AMeDAS hourly via obsdl)
├── jma_to_gwo_converter.py         # JMA→GWO format conversion logic
├── mod_class_met.py                # Core classes for reading GWO/AMD databases
├── verify_gwo_conversion.py        # Verification tool for conversions
└── data/
    ├── stations.yaml               # SYNOP/官署 station catalog (~152 entries)
    └── amedas_stations.yaml        # AMeDAS station catalog (~1500 entries)
```

### Class Hierarchy in `mod_class_met.py`

1. **`Met`** (Base): Datetime ranges, station selection, RMK code handling
2. **`Met_GWO`** (Hourly): Reads `{station}/{station}{year}.csv`, handles 3-hour→1-hour interpolation
3. **`Met_GWO_check`**: Data quality validation, detects missing rows
4. **`Met_GWO_daily`**: Daily aggregated data with solar radiation unit handling
5. **`Data1D`/`Data1Ds`/`Plot1D`**: Time series visualization utilities

### Key Properties of `Met_GWO`
- `df_org`: Raw data as read from CSV
- `df_interp`: Interpolated at original frequency
- `df`: Uniform 1-hour intervals (main output)

## Data Formats

### Temporal Data Structure
- **1961-1990**: 3-hour intervals, no sunshine/solar/precipitation
- **1991+**: 1-hour intervals
- **Cloud cover/weather**: Always 3-hour intervals only

### RMK (Remark) Codes
| Code | Meaning |
|------|---------|
| 0 | Observation not created |
| 1 | Missing observation |
| 2 | Not observed (nighttime for solar, interpolated cloud) |
| 6 | Phenomenon absent (no precipitation) |
| 8 | Normal observation (reliable) |

### Unit Conversions in `Met_GWO._unit_conversion()`
- Pressure: 0.1hPa → hPa
- Temperature: 0.1°C → °C
- Wind direction: 1-16 code → degrees via `(-90 - val*22.5) % 360`
- Solar radiation: 0.01MJ/m²/h → W/m² (×10000÷3600)

### GWO CSV Format
- 33 columns, no headers
- Directory structure: `{dirpath}/{station}/{station}{year}.csv`
- Pre-2022: Scaled values (×10 for most)
- 2022+: JMA-compatible format with direct values

## Important Implementation Notes

### Missing Value Strategy
- RMK=0,1: Always missing
- RMK=2 for solar/daylight: Valid (nighttime)
- RMK=2 for cloud/weather: Missing
- Missing rows filled with NaN and RMK=0

### Known Data Issues
- **Chiba 2010-2011**: Missing rows in hourly data
- **Sea level pressure 1961-2002**: Values ≥10000 need +10000 correction
- **Cloud interpolation bug in original GWO**: Non-observation hours incorrectly set to cloud=0 with RMK=2 instead of interpolating

### JMA Downloader Guidelines

**obsdl Downloader (`jma_obsdl_downloader.py`) - Recommended:**
- Uses structured quality information (not symbol parsing)
- Accurate RMK=6 (no phenomenon) vs RMK=2 (not observed) distinction
- Handles JMA special notations: `0+` (trace), `10-` (slightly less than 10)
- API endpoint: `https://www.data.jma.go.jp/risk/obsdl/show/table`
- Session management via `ci_session` cookie
- CSV encoding: cp932/Shift-JIS
- Quality codes: 8 (normal), 5 (quasi-normal), 4/2 (questionable), 1 (missing), 0 (not observed)
- Phenomenon-absent flag: 1 (no phenomenon) → RMK=6 when quality=8
- Cloud cover: Linearly interpolated for non-observation hours (RMK=2)

**etrn Downloader (`jma_weather_downloader.py`) - Deprecated:**
- Minimum 0.5s delay between requests to respect server load
- Downloads use `pd.read_html()` for HTML table scraping
- Station codes: https://www.data.jma.go.jp/stats/etrn/index.php
- UTF-8-BOM encoding for Excel compatibility
- RMK codes inferred from symbols (`--`, `///`, `×`) - less accurate than obsdl

**AMeDAS obsdl Downloader (`jma_obsdl_amd_downloader.py`):**
- Reuses `JMAObsdlDownloader` for HTTP plumbing; AMeDAS-specific row converter
- Station IDs are `aXXXX` (4-digit zero-padded AMeDAS code), not `s47XXX`
- AMeDAS CSV layout: 36 cols (1 datetime + 35 element cols) — NO
  `phenomenon_absent` column for precipitation/sunshine (JMA documents it as
  SYNOP-only). Element column indices differ from SYNOP.
- Per-station kansoku flags decide which elements are observed. Elements the
  station does not measure → `value=NaN, RMK=0` ("observation not created"),
  regardless of what obsdl returns.
- Cloud cover is **never** AMeDAS-observed → always `NaN, RMK=0`.
- RMK=6 (no phenomenon) for precipitation is inferred heuristically from
  `value=0.0 + quality=8`, since the explicit `phenomenon_absent` flag is
  absent for AMeDAS.
- Bbox CLI excludes rain-only (`ame`) and snow-only (`yuki`) categories by
  default; use `--include-rain-only` to include them.
- Station catalog (`data/amedas_stations.yaml`) is built by
  `scripts/build_amedas_station_catalog.py`, which scrapes the obsdl
  per-prefecture HTML fragment (`POST /risk/obsdl/top/station` with
  `pd=<prec_no>`) and extracts `stid`/`prid`/lat/lon/`kansoku`.

### Configuration Priority
1. Environment variables (highest)
2. `.env` file
3. Default values

Key variables: `DATA_DIR`, `JMA_DATABASE_DIR`, `GWO_HOURLY_DIR`, `JMA_DOWNLOAD_DIR`

## Development Notes

### Notebooks
- Located in `notebooks/`
- Clear outputs before committing: `nbstripout notebooks/*.ipynb`
- Paths resolve via `$DATA_DIR`

### Linting Configuration (pyproject.toml)
- Target: Python 3.12+
- Excludes: `notebooks/`, `mod_class_met.py`
- Rules: E, F, W, I, B (ignores E203)

### Station Catalogs
- SYNOP/官署: `src/gwo_amd/data/stations.yaml`
  - Regenerate: `python scripts/build_station_catalog.py`
  - Custom catalog: `--stations-config my_stations.yaml`
- AMeDAS: `src/gwo_amd/data/amedas_stations.yaml`
  - Regenerate: `python scripts/build_amedas_station_catalog.py`
  - kansoku decoding: pos 0=rain, 1=wind, 2=temp, 3=sunshine, 4=snow, 5=other
    (humidity/pressure/dew/vapor/solar). Each char is `0`/`1`/`2`
    (not observed/observed/estimated).
