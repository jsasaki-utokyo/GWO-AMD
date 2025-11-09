import pandas as pd

from gwo_amd.jma_weather_downloader import convert_to_gwo_format


def _make_sample_df():
    # Columns are positional because convert_to_gwo_format uses iloc indexes.
    columns = [f"col{i}" for i in range(20)]
    return pd.DataFrame(
        [
            [
                1,          # hour
                1008.4,     # local pressure
                1015.2,     # sea pressure
                0.5,        # precip
                15.3,       # temperature
                12.3,       # dew point
                18.3,       # vapor pressure
                80,         # humidity
                5.5,        # wind speed
                "北西",      # wind direction
                1.2,        # sunshine
                0.45,       # solar
                "", "", "", "5", "", 2020, 1, 1
            ],
            [
                2,
                1005.0,
                1010.0,
                "--",       # no precipitation
                10.0,
                5.0,
                12.0,
                60,
                3.2,
                "南",
                "///",      # missing sunshine
                "×",        # missing solar
                "", "", "", "7", "", 2020, 1, 1
            ],
        ],
        columns=columns,
    )


def test_convert_to_gwo_format_scales_and_handles_markers():
    df = _make_sample_df()
    metadata = {
        "name_en": "Chiba",
        "name_jp": "千葉",
        "station_id": "682",
        "remarks": [],
    }

    converted, stats = convert_to_gwo_format(df, metadata)

    # Shape and stats sanity.
    assert len(converted) == 2
    assert stats["total_rows"] == 2

    # Row 1 scaling and mapping checks.
    first = converted.iloc[0]
    assert first[7] == 10084          # local pressure ×10
    assert first[9] == 10152          # sea level pressure ×10
    assert first[11] == 153           # temperature ×10
    assert first[25] == 123           # dew point ×10
    assert first[27] == 12            # sunshine ×10
    assert first[29] == 45            # solar ×100
    assert first[21] == 5             # cloud cover interpolated

    # Row 2 handling of "--" / missing markers.
    second = converted.iloc[1]
    assert second[31] == 0            # precipitation coerced to 0
    assert second[32] == 2            # precipitation RMK -> no phenomenon
    assert second[27] == 0            # sunshine missing -> 0
    assert second[29] == 0            # solar missing -> 0
    assert second[21] >= 0            # cloud interpolated to numeric
