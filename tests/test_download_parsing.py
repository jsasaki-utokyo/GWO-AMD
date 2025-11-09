from io import StringIO

import pandas as pd


def test_html_fixture_matches_expected_shape(fixtures_dir):
    html_path = fixtures_dir / "jma_hourly_sample.html"
    tables = pd.read_html(StringIO(html_path.read_text(encoding="utf-8")))
    assert len(tables) == 1
    df = tables[0]
    assert list(df.columns[:5]) == ["時", "現地気圧", "海面気圧", "降水量", "気温"]
    assert df.iloc[0]["時"] == 1
    assert df.iloc[1]["風向"] == "南"
