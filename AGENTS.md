# Repository Guidelines

## Project Structure & Module Organization
`jma_weather_downloader.py` powers the `jma-download` CLI, `jma_to_gwo_converter.py` and `mod_class_met.py` handle conversion and analytics, and `config.py` centralizes paths via `.env`. Data defaults to `jma_data/` (web output) plus the external GWO/AMD trees described in `CONFIGURATION.md`, while notebooks at the repo root remain exploratory—promote reusable code into modules.

## Build, Test, and Development Commands
- `conda env create -f environment.yml && conda activate gwo-amd` – provision the Python 3.12 stack with pandas, requests, and lxml.
- `pip install -e .[dev]` – editable install plus notebook extras.
- `python config.py` – confirm `DATA_DIR` and sibling paths before downloads.
- `jma-download --year 2023 --station tokyo --gwo-format` – pull hourly CSVs into `jma_data/Tokyo/` and emit GWO columns.
- `python verify_gwo_conversion.py --input jma_data/Tokyo2023.csv --out temp_jma/Tokyo2023_gwo.csv` – check converters before distributing results.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indents, `snake_case` functions, and `CapWords` classes (e.g., `Met_GWO`). Prefer `pathlib.Path`, f-strings, and concise logging strings. CLI options should stay long-form (`--year`, `--prec_no`) and match argparse defaults documented in `README.md`. Keep pandas logic vectorized, isolating unavoidable loops in helpers for easier profiling.

## Testing Guidelines
Existing smoke tests (`test_jma_downloader.py`, `test_jma_week.py`) are executable scripts; run via `python test_jma_downloader.py` after exporting `DATA_DIR`. Honor the built-in one-second delay and avoid parallel runs to stay polite to JMA. When adding tests, store deterministic fixtures under `temp_jma/fixtures/`, name files `test_<scope>.py`, and consider wrapping them with pytest for future CI.

## Commit & Pull Request Guidelines
History favors short imperative subjects (`Add comparison document`, `Minor bugfix and revisions`). Keep commits focused, mention affected stations or years in the body, and link issues with `Fixes #ID` when relevant. PRs should summarize the datapath touched, list the exact commands executed, attach sample CSV diffs or screenshots, and mention any `.env` keys reviewers must set.

## Configuration & Data Handling
Copy `.env.example` to `.env`, set `DATA_DIR`, and let `config.CONFIG` derive `GWO_HOURLY_DIR`, `AMD_DIR`, and `JMA_DOWNLOAD_DIR`. Keep proprietary GWO/AMD dumps outside the repo and point configs to mounted drives; never commit real observations. Reference paths indirectly (e.g., `config.get_jma_download_dir()`) so collaborators can run the same notebook or CLI invocation without edits.
