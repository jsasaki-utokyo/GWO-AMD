"""
Unit tests for JMA obsdl downloader module.

Tests cover:
- Quality to RMK mapping
- Wind direction conversion
- GWO format conversion
- Cloud interpolation
"""

import pandas as pd
import pytest

from gwo_amd.jma_obsdl_downloader import (
    WIND_DIR_MAP,
    JMAObsdlDownloader,
)


@pytest.fixture
def downloader():
    """Create a downloader instance for testing."""
    return JMAObsdlDownloader(delay=0.1)


class TestQualityToRMKMapping:
    """Test quality info to RMK conversion."""

    def test_normal_value(self, downloader):
        """Quality 8 (normal) should map to RMK 8."""
        assert downloader._convert_quality_to_rmk(8) == 8
        assert downloader._convert_quality_to_rmk("8") == 8

    def test_quasi_normal_value(self, downloader):
        """Quality 5 (quasi-normal) should map to RMK 5."""
        assert downloader._convert_quality_to_rmk(5) == 5
        assert downloader._convert_quality_to_rmk("5") == 5

    def test_insufficient_value(self, downloader):
        """Quality 4 (insufficient) should map to RMK 5."""
        assert downloader._convert_quality_to_rmk(4) == 5

    def test_questionable_value(self, downloader):
        """Quality 2 (questionable) should map to RMK 5."""
        assert downloader._convert_quality_to_rmk(2) == 5

    def test_missing_value(self, downloader):
        """Quality 1 (missing) should map to RMK 1."""
        assert downloader._convert_quality_to_rmk(1) == 1

    def test_not_observed_value(self, downloader):
        """Quality 0 (not observed) should map to RMK 2."""
        assert downloader._convert_quality_to_rmk(0) == 2

    def test_phenomenon_absent(self, downloader):
        """Phenomenon absent (1) + quality 8 should map to RMK 6."""
        # This is the critical improvement over etrn scraping
        result = downloader._convert_quality_to_rmk(8, phenomenon_absent=1)
        assert result == 6, "RMK should be 6 when phenomenon is absent with normal quality"

    def test_phenomenon_absent_only_affects_normal(self, downloader):
        """Phenomenon absent should only override to RMK 6 when quality is 8."""
        # If quality is not 8, phenomenon_absent should not trigger RMK=6
        assert downloader._convert_quality_to_rmk(5, phenomenon_absent=1) == 5
        assert downloader._convert_quality_to_rmk(1, phenomenon_absent=1) == 1
        assert downloader._convert_quality_to_rmk(0, phenomenon_absent=1) == 2

    def test_empty_string_quality(self, downloader):
        """Empty string should be treated as 0 (not observed)."""
        assert downloader._convert_quality_to_rmk("") == 2

    def test_none_quality(self, downloader):
        """None should be treated as 0 (not observed)."""
        assert downloader._convert_quality_to_rmk(None) == 2

    def test_invalid_quality(self, downloader):
        """Invalid quality values should default to RMK 8."""
        assert downloader._convert_quality_to_rmk("invalid") == 2
        assert downloader._convert_quality_to_rmk("abc") == 2


class TestWindDirectionMapping:
    """Test wind direction conversion from Japanese text to GWO code."""

    def test_basic_directions(self):
        """Test 16-point compass directions."""
        assert WIND_DIR_MAP["北"] == 16  # N
        assert WIND_DIR_MAP["東"] == 4  # E
        assert WIND_DIR_MAP["南"] == 8  # S
        assert WIND_DIR_MAP["西"] == 12  # W

    def test_intercardinal_directions(self):
        """Test intercardinal directions (NE, SE, SW, NW)."""
        assert WIND_DIR_MAP["北東"] == 2  # NE
        assert WIND_DIR_MAP["南東"] == 6  # SE
        assert WIND_DIR_MAP["南西"] == 10  # SW
        assert WIND_DIR_MAP["北西"] == 14  # NW

    def test_secondary_intercardinal_directions(self):
        """Test secondary intercardinal directions."""
        assert WIND_DIR_MAP["北北東"] == 1  # NNE
        assert WIND_DIR_MAP["東北東"] == 3  # ENE
        assert WIND_DIR_MAP["東南東"] == 5  # ESE
        assert WIND_DIR_MAP["南南東"] == 7  # SSE
        assert WIND_DIR_MAP["南南西"] == 9  # SSW
        assert WIND_DIR_MAP["西南西"] == 11  # WSW
        assert WIND_DIR_MAP["西北西"] == 13  # WNW
        assert WIND_DIR_MAP["北北西"] == 15  # NNW

    def test_calm_direction(self):
        """Test calm (no wind) condition."""
        assert WIND_DIR_MAP["静穏"] == 0

    def test_all_16_directions_present(self):
        """All 16 compass directions plus calm should be mapped."""
        # 16 compass directions + 1 calm = 17 entries
        assert len(WIND_DIR_MAP) == 17

    def test_all_codes_unique(self):
        """Each compass code (0-16) should be represented exactly once."""
        codes = list(WIND_DIR_MAP.values())
        assert set(codes) == set(range(17)), "Should have codes 0-16"
        assert len(codes) == len(set(codes)), "All codes should be unique"


class TestGWOConversion:
    """Test conversion to GWO format."""

    def _create_sample_obsdl_row(self):
        """Create a sample obsdl row for testing."""
        # 38 columns matching obsdl CSV structure
        return pd.Series(
            [
                "2023/1/15 12:00:00",  # 0: datetime
                1012.3,  # 1: local_pressure
                8,  # 2: local_pressure quality
                1,  # 3: local_pressure homogeneity
                1018.5,  # 4: sea_pressure
                8,  # 5: sea_pressure quality
                1,  # 6: sea_pressure homogeneity
                0.5,  # 7: precipitation
                0,  # 8: precip phenomenon_absent
                8,  # 9: precip quality
                1,  # 10: precip homogeneity
                5.2,  # 11: temperature
                8,  # 12: temp quality
                1,  # 13: temp homogeneity
                2.1,  # 14: dew_point
                8,  # 15: dew_point quality
                1,  # 16: dew_point homogeneity
                7.0,  # 17: vapor_pressure
                8,  # 18: vapor quality
                1,  # 19: vapor homogeneity
                68,  # 20: humidity
                8,  # 21: humidity quality
                1,  # 22: humidity homogeneity
                3.5,  # 23: wind_speed
                8,  # 24: wind_speed quality
                "北西",  # 25: wind_direction (Japanese)
                8,  # 26: wind_dir quality
                1,  # 27: wind homogeneity
                0.8,  # 28: sunshine
                0,  # 29: sunshine phenomenon_absent
                8,  # 30: sunshine quality
                1,  # 31: sunshine homogeneity
                1.23,  # 32: solar_radiation
                8,  # 33: solar quality
                1,  # 34: solar homogeneity
                7,  # 35: cloud_cover
                8,  # 36: cloud quality
                1,  # 37: cloud homogeneity
            ]
        )

    def test_convert_row_basic(self, downloader):
        """Test basic row conversion."""
        row = self._create_sample_obsdl_row()
        stats = {"total_rows": 0, "precip_no_phenomenon": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result is not None
        assert len(result) == 33, "GWO format should have 33 columns"

    def test_convert_row_station_info(self, downloader):
        """Test station ID and name in converted row."""
        row = self._create_sample_obsdl_row()
        stats = {}

        result = downloader._convert_row_to_gwo(row, "682", "千葉", stats)

        assert result[0] == "682"  # station_id
        assert result[1] == "千葉"  # station_name
        assert result[2] == "682"  # station_id2

    def test_convert_row_datetime(self, downloader):
        """Test datetime extraction."""
        row = self._create_sample_obsdl_row()
        stats = {}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[3] == 2023  # year
        assert result[4] == 1  # month
        assert result[5] == 15  # day
        assert result[6] == 12  # hour

    def test_convert_row_hour_24(self, downloader):
        """Test hour 24 handling (midnight)."""
        row = self._create_sample_obsdl_row()
        row.iloc[0] = "2023/1/15 0:00:00"  # midnight
        stats = {}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[6] == 24, "Midnight (00:00) should be hour 24 in GWO"

    def test_convert_row_pressure_scaling(self, downloader):
        """Test pressure scaling (×10)."""
        row = self._create_sample_obsdl_row()
        stats = {}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Local pressure: 1012.3 × 10 = 10123
        assert result[7] == 10123
        assert result[8] == 8  # RMK = normal

        # Sea pressure: 1018.5 × 10 = 10185
        assert result[9] == 10185
        assert result[10] == 8  # RMK = normal

    def test_convert_row_temperature_scaling(self, downloader):
        """Test temperature scaling (×10)."""
        row = self._create_sample_obsdl_row()
        stats = {"temperature_missing": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Temperature: 5.2 × 10 = 52
        assert result[11] == 52
        assert result[12] == 8  # RMK

    def test_convert_row_wind_direction(self, downloader):
        """Test wind direction conversion."""
        row = self._create_sample_obsdl_row()
        stats = {"wind_missing": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Wind direction: 北西 = NW = 14
        assert result[17] == 14
        assert result[18] == 8  # RMK

    def test_convert_row_wind_speed_scaling(self, downloader):
        """Test wind speed scaling (×10)."""
        row = self._create_sample_obsdl_row()
        stats = {"wind_missing": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Wind speed: 3.5 × 10 = 35
        assert result[19] == 35
        assert result[20] == 8  # RMK

    def test_convert_row_sunshine_scaling(self, downloader):
        """Test sunshine scaling (×10)."""
        row = self._create_sample_obsdl_row()
        stats = {"sunshine_not_observed": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Sunshine: 0.8 × 10 = 8
        assert result[27] == 8
        assert result[28] == 8  # RMK = normal

    def test_convert_row_solar_scaling(self, downloader):
        """Test solar radiation scaling (×100)."""
        row = self._create_sample_obsdl_row()
        stats = {"solar_not_observed": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        # Solar: 1.23 × 100 = 123
        assert result[29] == 123
        assert result[30] == 8  # RMK

    def test_convert_row_precipitation_no_phenomenon(self, downloader):
        """Test precipitation with no phenomenon (RMK=6)."""
        row = self._create_sample_obsdl_row()
        # Set precipitation phenomenon_absent = 1 (no rain)
        row.iloc[7] = 0.0  # value
        row.iloc[8] = 1  # phenomenon_absent
        row.iloc[9] = 8  # quality = normal
        stats = {"precip_no_phenomenon": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[32] == 6, "Precipitation RMK should be 6 when no phenomenon"
        assert result[31] == 0, "Precipitation value should be 0 when RMK=6"
        assert stats["precip_no_phenomenon"] == 1

    def test_convert_row_sunshine_nighttime_explicit_zero(self, downloader):
        """Test sunshine at nighttime (RMK=2) has explicit zero value."""
        row = self._create_sample_obsdl_row()
        # Set sunshine to not observed (quality=0 means nighttime)
        row.iloc[28] = ""  # empty value (nighttime)
        row.iloc[29] = 0  # phenomenon_absent = 0
        row.iloc[30] = 0  # quality = 0 (not observed / nighttime)
        stats = {"sunshine_not_observed": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[28] == 2, "Sunshine RMK should be 2 for nighttime"
        assert result[27] == 0, "Sunshine value should be 0 for nighttime, not NaN"
        assert stats["sunshine_not_observed"] == 1

    def test_convert_row_solar_nighttime_explicit_zero(self, downloader):
        """Test solar radiation at nighttime (RMK=2) has explicit zero value."""
        row = self._create_sample_obsdl_row()
        # Set solar to not observed (quality=0 means nighttime)
        row.iloc[32] = ""  # empty value (nighttime)
        row.iloc[33] = 0  # quality = 0 (not observed / nighttime)
        stats = {"solar_not_observed": 0}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[30] == 2, "Solar RMK should be 2 for nighttime"
        assert result[29] == 0, "Solar value should be 0 for nighttime, not NaN"
        assert stats["solar_not_observed"] == 1

    def test_convert_row_weather_always_not_observed(self, downloader):
        """Test weather is always marked as not observed (RMK=2)."""
        row = self._create_sample_obsdl_row()
        stats = {}

        result = downloader._convert_row_to_gwo(row, "999", "テスト", stats)

        assert result[23] is None  # Weather value
        assert result[24] == 2  # Weather RMK always 2


class TestCloudInterpolation:
    """Test cloud cover interpolation."""

    def test_cloud_interpolation_basic(self, downloader):
        """Test cloud interpolation between observation hours."""
        # Create a minimal DataFrame with hour 3, 4, 5, 6
        # Hours 3 and 6 are observation hours, 4 and 5 should be interpolated
        data = {
            6: [3, 4, 5, 6],  # hour column
            21: [8, None, None, 2],  # cloud column
            22: [8, 8, 8, 8],  # cloud RMK column
        }
        df = pd.DataFrame(data)
        stats = {"cloud_interpolated": 0}

        result = downloader._apply_cloud_interpolation(df, stats)

        # Hour 3: cloud=8 (observed)
        # Hour 4: cloud=6 (interpolated from 8 to 2)
        # Hour 5: cloud=4 (interpolated from 8 to 2)
        # Hour 6: cloud=2 (observed)
        assert result.iloc[0][21] == 8
        assert result.iloc[1][21] == 6
        assert result.iloc[2][21] == 4
        assert result.iloc[3][21] == 2

        # Non-observation hours should have RMK=2
        assert result.iloc[1][22] == 2
        assert result.iloc[2][22] == 2
        # Observation hours keep their RMK
        assert result.iloc[0][22] == 8
        assert result.iloc[3][22] == 8

    def test_cloud_interpolation_hour_24(self, downloader):
        """Test hour 24 is treated as non-observation hour."""
        data = {
            6: [21, 22, 23, 24],  # hours including hour 24
            21: [5, None, None, None],  # cloud
            22: [8, 8, 8, 8],  # RMK
        }
        df = pd.DataFrame(data)
        stats = {"cloud_interpolated": 0}

        result = downloader._apply_cloud_interpolation(df, stats)

        # Hour 24 (midnight) should be marked as interpolated
        assert result.iloc[3][22] == 2


class TestCSVParsing:
    """Test CSV content parsing."""

    def test_parse_csv_empty(self, downloader):
        """Empty content should return None."""
        result = downloader._parse_csv_content("")
        assert result is None

    def test_parse_csv_no_data_message(self, downloader):
        """'No data' message should return None."""
        content = "header1\nheader2\nheader3\nheader4\nheader5\nheader6\nデータがありません"
        result = downloader._parse_csv_content(content)
        assert result is None

    def test_parse_csv_too_few_rows(self, downloader):
        """Content with only headers should return None."""
        content = "row1\nrow2\nrow3\nrow4\nrow5\nrow6"
        result = downloader._parse_csv_content(content)
        assert result is None

    def test_parse_csv_basic(self, downloader):
        """Test parsing basic CSV with headers and data."""
        content = """ダウンロード時刻
empty
station header
element header
sub-element header
quality header
2023/1/1 1:00:00,1012.3,8,1,1018.5,8,1"""
        result = downloader._parse_csv_content(content)
        assert result is not None
        assert len(result) == 1


class TestDownloadParameters:
    """Test download parameter building."""

    def test_build_params_station_format(self, downloader):
        """Station ID should include 's' prefix."""
        from datetime import date

        params = downloader._build_download_params(
            "s47662", date(2023, 1, 1), date(2023, 1, 31)
        )

        import json

        station_list = json.loads(params["stationNumList"])
        assert station_list[0] == "s47662"

    def test_build_params_date_format(self, downloader):
        """Date range should be formatted correctly."""
        import json
        from datetime import date

        params = downloader._build_download_params(
            "s47662", date(2023, 6, 15), date(2023, 7, 20)
        )

        ymd_list = json.loads(params["ymdList"])
        assert ymd_list[0] == "2023"  # start year
        assert ymd_list[1] == "2023"  # end year
        assert ymd_list[2] == "6"  # start month
        assert ymd_list[3] == "7"  # end month
        assert ymd_list[4] == "15"  # start day
        assert ymd_list[5] == "20"  # end day

    def test_build_params_flags(self, downloader):
        """Verify required flags are set."""
        from datetime import date

        params = downloader._build_download_params(
            "s47662", date(2023, 1, 1), date(2023, 1, 31)
        )

        assert params["downloadFlag"] == "true"
        assert params["rmkFlag"] == "1"  # Quality info
        assert params["disconnectFlag"] == "1"  # Phenomenon-absent info
        assert params["csvFlag"] == "1"  # Numeric CSV
        assert params["aggrgPeriod"] == "9"  # Hourly data


class TestInit:
    """Test downloader initialization."""

    def test_delay_minimum(self):
        """Delay should be at least 0.5 seconds."""
        downloader = JMAObsdlDownloader(delay=0.1)
        assert downloader.delay >= 0.5

    def test_delay_normal(self):
        """Normal delay should be preserved."""
        downloader = JMAObsdlDownloader(delay=1.5)
        assert downloader.delay == 1.5

    def test_timeout_default(self):
        """Default timeout should be 120 seconds."""
        downloader = JMAObsdlDownloader()
        assert downloader.timeout == 120

    def test_timeout_custom(self):
        """Custom timeout should be preserved."""
        downloader = JMAObsdlDownloader(timeout=60)
        assert downloader.timeout == 60
