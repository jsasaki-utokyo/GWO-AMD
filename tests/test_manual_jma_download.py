import os
import time

import pandas as pd
import pytest
import requests

RUN_LIVE = os.getenv("RUN_LIVE_JMA_TESTS") == "1"

pytestmark = pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live JMA download test (set RUN_LIVE_JMA_TESTS=1 to enable)",
)

BASE_URL = "https://www.data.jma.go.jp/obd/stats/etrn/view/hourly_s1.php"
TOKYO_PARAMS = {"prec_no": "44", "block_no": "47662"}


def _fetch_day(year: int, month: int, day: int) -> pd.DataFrame:
    params = {
        **TOKYO_PARAMS,
        "year": str(year),
        "month": str(month),
        "day": str(day),
        "view": "p1",
    }
    response = requests.get(BASE_URL, params=params, timeout=30)
    response.raise_for_status()

    tables = pd.read_html(response.text)
    assert tables, "No tables returned from JMA service"
    return tables[0]


def test_live_download_single_day():
    df = _fetch_day(2023, 1, 1)
    # Expect 24 hours for a complete day
    assert len(df) in {24, 25}, "Unexpected number of hourly rows"
    assert "日" in df.columns[-1], "Date column missing from table"


def test_live_download_week(tmp_path):
    frames = []
    for day in range(1, 8):
        frames.append(_fetch_day(2023, 1, day))
        time.sleep(0.5)

    combined = pd.concat(frames, ignore_index=True)
    assert len(combined) >= 7 * 24

    # Persist to tmp for manual inspection when running locally
    output = tmp_path / "tokyo_week_202301.csv"
    combined.to_csv(output, index=False, encoding="utf-8-sig")
    assert output.exists()
