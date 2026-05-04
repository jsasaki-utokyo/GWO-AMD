"""
Unit tests for the AMeDAS obsdl downloader (gwo_amd.jma_obsdl_amd_downloader).

Coverage:
- Catalog loading from package data
- Bounding-box filter
- Kansoku → element-availability decoding
- AMeDAS CSV parsing (uses a saved fixture; no network)
- AMeDAS row → 33-column GWO conversion
- Quality-to-RMK mapping with the "instrument absent" override
- _resolve_station_set CLI helper

Live-network tests are skipped unless ``RUN_LIVE_JMA_TESTS=1`` (matching the
existing convention in tests/test_manual_jma_download.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from gwo_amd.jma_obsdl_amd_downloader import (
    AMD_TOTAL_COLS,
    JMAObsdlAmdConverter,
    JMAObsdlAmdYearDownloader,
    _kansoku_observes,
    filter_by_bbox,
    load_amedas_catalog,
)
from gwo_amd.jma_obsdl_downloader import JMAObsdlDownloader

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def amd_catalog():
    """Load the package-shipped AMeDAS catalog once for the test module."""
    catalog, _ = load_amedas_catalog()
    return catalog


@pytest.fixture
def converter():
    return JMAObsdlAmdConverter()


@pytest.fixture
def haneda_csv_text(fixtures_dir):
    """Recorded obsdl AMeDAS response: a0371 (Haneda) hourly, 2020-01-01.

    Captured live with all 11 elements requested (the typical request shape we
    send), so it has 36 columns: 1 datetime + 35 element columns.
    """
    path = fixtures_dir / "jma_obsdl_amedas_haneda_2020_01_01.csv"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class TestCatalog:
    def test_catalog_nonempty(self, amd_catalog):
        assert len(amd_catalog) > 0

    def test_catalog_has_haneda(self, amd_catalog):
        assert "a0371" in amd_catalog
        h = amd_catalog["a0371"]
        assert h["name_jp"] == "羽田"
        assert h["prec_no"] == "44"
        # Haneda obsdl reports kansoku=111000 (rain+wind+temp only).
        assert h["kansoku"] == "111000"
        assert h["category"] == "san"

    def test_catalog_entries_have_required_fields(self, amd_catalog):
        sample = next(iter(amd_catalog.values()))
        for field in ("stid", "name_jp", "prec_no", "latitude", "longitude",
                      "kansoku", "category", "elements", "terminated"):
            assert field in sample, f"missing {field}"


# ---------------------------------------------------------------------------
# Kansoku decoding
# ---------------------------------------------------------------------------


class TestKansokuObserves:
    @pytest.mark.parametrize("element,expected", [
        ("precipitation", True),
        ("wind", True),
        ("temperature", True),
        ("sunshine", False),
        ("humidity", False),
        ("local_pressure", False),
        ("solar_radiation", False),
        ("cloud_cover", False),  # cloud is never observed by AMeDAS
    ])
    def test_san_station(self, element, expected):
        # 三 station (rain+wind+temp only)
        assert _kansoku_observes("111000", element) is expected

    @pytest.mark.parametrize("element,expected", [
        ("precipitation", True),
        ("wind", True),
        ("temperature", True),
        ("sunshine", True),       # "2" = estimated, treated as observed
        ("humidity", True),       # other-bit = 1
        ("local_pressure", True),
        ("cloud_cover", False),   # never observed by AMeDAS
    ])
    def test_shi_station_with_humidity(self, element, expected):
        assert _kansoku_observes("111201", element) is expected

    def test_kan_station_full(self):
        # Class A — everything (except cloud, which is never AMeDAS-observed)
        for elem in ("precipitation", "wind", "temperature", "sunshine",
                     "humidity", "local_pressure"):
            assert _kansoku_observes("111111", elem)
        assert not _kansoku_observes("111111", "cloud_cover")

    def test_ame_station(self):
        # Rainfall only
        assert _kansoku_observes("100000", "precipitation")
        for elem in ("wind", "temperature", "sunshine", "humidity"):
            assert not _kansoku_observes("100000", elem)

    def test_short_or_empty_kansoku(self):
        assert not _kansoku_observes("", "precipitation")
        assert not _kansoku_observes("11", "precipitation")
        assert not _kansoku_observes(None, "precipitation")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Bbox filter
# ---------------------------------------------------------------------------


class TestBboxFilter:
    def test_tokyo_bay_bbox_finds_haneda(self, amd_catalog):
        selected = filter_by_bbox(
            amd_catalog,
            west=138.889, south=33.972, east=141.528, north=36.250,
        )
        assert "a0371" in selected, "Haneda should be inside the Tokyo Bay bbox"
        # Default behavior excludes rain-only stations? No — by default
        # filter_by_bbox includes everything; exclusion happens at the CLI
        # layer with --include-rain-only opt-out.

    def test_tiny_bbox_excludes_everything(self, amd_catalog):
        # A 0.001° box well off the coast should match nothing.
        selected = filter_by_bbox(
            amd_catalog,
            west=170.0, south=10.0, east=170.001, north=10.001,
        )
        assert selected == {}

    def test_category_filter_excludes_rain_only(self, amd_catalog):
        selected = filter_by_bbox(
            amd_catalog,
            west=138.889, south=33.972, east=141.528, north=36.250,
            include_categories=("kan", "shi", "san", "other"),
        )
        for info in selected.values():
            assert info["category"] in ("kan", "shi", "san", "other"), (
                f"unexpected category {info['category']} in filtered set"
            )

    def test_excludes_terminated_by_default(self, amd_catalog):
        terminated_in_full = [
            k for k, v in amd_catalog.items() if v.get("terminated")
        ]
        if not terminated_in_full:
            pytest.skip("catalog has no terminated stations")
        # Bbox big enough to cover all of Japan
        selected = filter_by_bbox(
            amd_catalog,
            west=120.0, south=20.0, east=150.0, north=46.0,
        )
        for info in selected.values():
            assert not info.get("terminated"), (
                f"terminated station {info['stid']} should be excluded"
            )


# ---------------------------------------------------------------------------
# Quality → RMK mapping
# ---------------------------------------------------------------------------


class TestQualityMapping:
    def test_observed_normal(self, converter):
        assert converter._quality_to_rmk(8, observed_by_station=True) == 8

    def test_observed_missing(self, converter):
        assert converter._quality_to_rmk(1, observed_by_station=True) == 1

    def test_observed_nighttime(self, converter):
        # Quality 0 at an observed station means nighttime (RMK=2).
        assert converter._quality_to_rmk(0, observed_by_station=True) == 2

    def test_unobserved_forces_rmk_zero(self, converter):
        # Even a "normal" obsdl quality must collapse to RMK=0 when the
        # station's kansoku flag says the instrument is absent.
        assert converter._quality_to_rmk(8, observed_by_station=False) == 0
        assert converter._quality_to_rmk(0, observed_by_station=False) == 0

    def test_string_quality(self, converter):
        assert converter._quality_to_rmk("8", observed_by_station=True) == 8

    def test_empty_quality(self, converter):
        assert converter._quality_to_rmk("", observed_by_station=True) == 2


# ---------------------------------------------------------------------------
# Numeric parsing
# ---------------------------------------------------------------------------


class TestParseValue:
    @pytest.mark.parametrize("raw,scale,expected", [
        ("12.3", 10, 123),
        ("1012.3", 10, 10123),
        ("0", 10, 0),
        ("0.0", 10, 0),
        ("--", 10, None),
        ("", 10, None),
    ])
    def test_basic(self, raw, scale, expected):
        assert JMAObsdlAmdConverter._parse_value(raw, scale) == expected

    def test_trace_plus(self):
        # JMA notation: "0+" = trace amount
        assert JMAObsdlAmdConverter._parse_value("0+", 10) == 0

    def test_dash_suffix_for_capped_values(self):
        # JMA notation: "10-" = slightly less than 10
        assert JMAObsdlAmdConverter._parse_value("10-", 1) == 10

    def test_negative_value(self):
        # Negative values like "-3.2" must NOT be treated as the dash-suffix
        # notation.
        assert JMAObsdlAmdConverter._parse_value("-3.2", 10) == -32


# ---------------------------------------------------------------------------
# CSV parsing + end-to-end conversion (offline, uses fixture)
# ---------------------------------------------------------------------------


class TestAmedasCsvParsing:
    def test_fixture_parses_to_36_cols(self, haneda_csv_text):
        dl = JMAObsdlDownloader(delay=0.5)
        df = dl._parse_csv_content(haneda_csv_text)
        assert df is not None
        assert df.shape[1] == AMD_TOTAL_COLS, (
            f"AMeDAS CSV should have {AMD_TOTAL_COLS} columns, got {df.shape[1]}"
        )
        assert df.shape[0] == 24, "fixture covers 2020-01-01 (24 hours)"


class TestEndToEndConversion:
    def test_haneda_san_station_full_conversion(
        self, haneda_csv_text, converter
    ):
        dl = JMAObsdlDownloader(delay=0.5)
        df = dl._parse_csv_content(haneda_csv_text)
        metadata = {
            "name_jp": "羽田",
            "station_id": 371,
            "kansoku": "111000",  # 三 station
        }
        gwo_df, stats = converter.convert_to_gwo(df, metadata)

        # Output shape
        assert gwo_df.shape == (24, 33)
        assert stats["total_rows"] == 24

        # Columns 0-2: station identity
        assert (gwo_df[0] == "371").all()
        assert (gwo_df[1] == "羽田").all()

        # First row: 2020-01-01 hour 1 (no midnight rollover)
        first = gwo_df.iloc[0]
        assert first[3] == 2020
        assert first[4] == 1
        assert first[5] == 1
        assert first[6] == 1

        # Observed elements at Haneda: precip / temp / wind dir+speed
        # Temperature: 4.6°C → 46
        assert first[11] == 46
        assert first[12] == 8
        # Wind direction: 北北西 = 15
        assert first[17] == 15
        assert first[18] == 8
        # Wind speed: 12.0 m/s → 120
        assert first[19] == 120
        assert first[20] == 8

        # Unobserved at this 三 station: pressure/RH/dew/vapor/sunshine/solar
        for unobs_value_col, unobs_rmk_col in (
            (7, 8),    # local pressure
            (9, 10),   # sea pressure
            (13, 14),  # vapor
            (15, 16),  # humidity
            (25, 26),  # dew
            (27, 28),  # sunshine
            (29, 30),  # solar
        ):
            assert pd.isna(first[unobs_value_col]), (
                f"col {unobs_value_col} should be NaN (unobserved)"
            )
            assert first[unobs_rmk_col] == 0, (
                f"col {unobs_rmk_col} should be RMK=0 (unobserved)"
            )

        # Cloud is never AMeDAS-observed
        assert (gwo_df[22] == 0).all(), "cloud RMK should always be 0 for AMeDAS"
        assert gwo_df[21].isna().all()

        # Weather is hardcoded RMK=2
        assert (gwo_df[24] == 2).all()
        assert gwo_df[23].isna().all()

        # All 24 hours are dry (RMK=6, value=0)
        assert (gwo_df[31] == 0).all(), (
            "Haneda 2020-01-01 was a dry day; precip values should all be 0"
        )
        assert (gwo_df[32] == 6).all(), (
            "RMK=6 (no phenomenon) should be applied when precip=0 with q=8"
        )
        assert stats["precip_no_phenomenon"] == 24

    def test_kan_station_conversion_uses_humidity(
        self, haneda_csv_text, converter
    ):
        """If the same CSV is interpreted as a kan station, humidity columns
        get their RMK from the obsdl quality (not forced to 0).
        Even though the obsdl response itself has empty humidity values, the
        RMK should be 2 (nighttime/not-observed) rather than 0 (instrument
        absent), since this kansoku claims the station observes humidity."""
        dl = JMAObsdlDownloader(delay=0.5)
        df = dl._parse_csv_content(haneda_csv_text)
        metadata = {
            "name_jp": "テスト",
            "station_id": 999,
            "kansoku": "111111",  # claim full observation
        }
        gwo_df, stats = converter.convert_to_gwo(df, metadata)
        # Humidity RMK col 16: should now be 2, not 0.
        assert (gwo_df[16] == 2).all()


# ---------------------------------------------------------------------------
# CLI helper: _resolve_station_set
# ---------------------------------------------------------------------------


class TestResolveStationSet:
    def _make_args(self, **overrides):
        import argparse
        args = argparse.Namespace(
            year=None,
            station=None,
            bbox=None,
            all_stations=False,
            include_rain_only=False,
            include_terminated=False,
            max_stations=None,
            output=Path("amd_data"),
            delay=1.0,
            stations_config=None,
            list_stations=False,
        )
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    def test_explicit_station_lookup(self, amd_catalog):
        from gwo_amd.jma_obsdl_amd_downloader import _resolve_station_set
        args = self._make_args(station=["a0371"])
        selected = _resolve_station_set(args, amd_catalog)
        assert "a0371" in selected

    def test_bbox_excludes_rain_only_by_default(self, amd_catalog):
        from gwo_amd.jma_obsdl_amd_downloader import _resolve_station_set
        args = self._make_args(bbox=[138.889, 33.972, 141.528, 36.250])
        selected = _resolve_station_set(args, amd_catalog)
        # No rain-only stations should appear
        assert all(
            info["category"] != "ame" for info in selected.values()
        ), "rain-only stations leaked into bbox selection"
        # And we still get the san/shi stations we expect
        assert "a0371" in selected

    def test_bbox_with_rain_only_opt_in(self, amd_catalog):
        from gwo_amd.jma_obsdl_amd_downloader import _resolve_station_set
        args = self._make_args(
            bbox=[138.889, 33.972, 141.528, 36.250],
            include_rain_only=True,
        )
        selected = _resolve_station_set(args, amd_catalog)
        # Now ame stations should appear
        assert any(
            info["category"] == "ame" for info in selected.values()
        ), "rain-only stations should be included when --include-rain-only set"

    def test_max_stations_caps_selection(self, amd_catalog):
        from gwo_amd.jma_obsdl_amd_downloader import _resolve_station_set
        args = self._make_args(
            bbox=[138.889, 33.972, 141.528, 36.250],
            max_stations=3,
        )
        selected = _resolve_station_set(args, amd_catalog)
        assert len(selected) == 3


# ---------------------------------------------------------------------------
# Live network test (gated by env var, mirrors test_manual_jma_download.py)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("RUN_LIVE_JMA_TESTS") != "1",
    reason="live JMA download — set RUN_LIVE_JMA_TESTS=1 to enable",
)
class TestLiveAmedasDownload:
    def test_download_haneda_one_day(self, tmp_path, amd_catalog):
        """Download Haneda 2020-01-01 (one day) and confirm a non-empty CSV."""
        from datetime import date
        assert "a0371" in amd_catalog, "catalog must contain Haneda"
        yd = JMAObsdlAmdYearDownloader(delay=1.0)
        yd.downloader._init_session()
        df = yd._download_period("a0371", date(2020, 1, 1), date(2020, 1, 1))
        assert df is not None
        assert df.shape[0] == 24
        assert df.shape[1] == AMD_TOTAL_COLS
