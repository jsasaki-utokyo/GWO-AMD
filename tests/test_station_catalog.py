import textwrap

from gwo_amd.jma_weather_downloader import (
    collect_relevant_remarks,
    load_station_catalog,
)


def test_load_station_catalog_normalizes_keys(tmp_path):
    catalog_path = tmp_path / "stations.yaml"
    catalog_path.write_text(
        textwrap.dedent(
            """
            metadata:
              generated_at: '2024-01-01T00:00:00Z'
            stations:
              TestStation:
                station_id: 999
                block_no: '47999'
                prec_no: '44'
                name_en: TestStation
                name_jp: テスト
                remarks: []
            """
        ),
        encoding="utf-8",
    )

    catalog, loaded_path = load_station_catalog(catalog_path)

    assert loaded_path == catalog_path
    assert "teststation" in catalog
    assert catalog["teststation"]["prec_no"] == "44"


def test_collect_relevant_remarks_filters_by_year():
    metadata = {
        "name_en": "Sample",
        "remarks": [
            {"start_date": "2010-01-01", "end_date": "2015-12-31", "note": "Moved"},
            {"start_date": "2016-01-01", "end_date": "9999-12-31", "note": "Current site"},
        ],
    }

    remarks_2012 = collect_relevant_remarks(metadata, 2012)
    assert len(remarks_2012) == 1
    assert remarks_2012[0]["note"] == "Moved"

    remarks_2020 = collect_relevant_remarks(metadata, 2020)
    assert len(remarks_2020) == 1
    assert remarks_2020[0]["note"] == "Current site"
