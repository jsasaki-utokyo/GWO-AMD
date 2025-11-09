#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
JMA Format to GWO Format Converter
Converts JMA etrn downloaded data to GWO-compatible format for use with mod_class_met.py
"""

import pandas as pd

# Wind direction mapping: Japanese text to GWO code (1-16)
# GWO: 0=N/A, 1=NNE, 2=NE, 3=ENE, 4=E, 5=ESE, 6=SE, 7=SSE, 8=S,
#      9=SSW, 10=SW, 11=WSW, 12=W, 13=WNW, 14=NW, 15=NNW, 16=N
WIND_DIR_MAP = {
    '北': 16,
    '北北東': 1,
    '北東': 2,
    '東北東': 3,
    '東': 4,
    '東南東': 5,
    '南東': 6,
    '南南東': 7,
    '南': 8,
    '南南西': 9,
    '南西': 10,
    '西南西': 11,
    '西': 12,
    '西北西': 13,
    '北西': 14,
    '北北西': 15,
    '静穏': 0,  # Calm
}

# Station ID mapping (extend as needed)
STATION_IDS = {
    'Tokyo': ('662', '東京'),
    'Yokohama': ('671', '横浜'),
    'Chiba': ('682', '千葉'),
    'Osaka': ('772', '大阪'),
    'Nagoya': ('636', '名古屋'),
    'Fukuoka': ('807', '福岡'),
    'Sapporo': ('412', '札幌'),
}


def parse_cloud_cover(cloud_str):
    """
    Parse cloud cover from JMA text format to GWO numeric (0-10)
    Examples: "0+", "10-", "5", "" (empty)
    """
    if pd.isna(cloud_str) or cloud_str == '' or cloud_str == '--':
        return None

    cloud_str = str(cloud_str).strip()

    # Remove +/- symbols
    cloud_str = cloud_str.replace('+', '').replace('-', '').replace('−', '')

    try:
        value = float(cloud_str)
        # Cloud cover should be 0-10
        if 0 <= value <= 10:
            return int(value)
    except ValueError:
        pass

    return None


def convert_wind_direction(wind_dir_text):
    """Convert Japanese wind direction text to GWO code (1-16)"""
    if pd.isna(wind_dir_text) or wind_dir_text == '' or wind_dir_text == '--':
        return 0  # N/A

    wind_dir_text = str(wind_dir_text).strip()
    return WIND_DIR_MAP.get(wind_dir_text, 0)


def convert_value(value, missing_markers=None):
    """
    Convert JMA value to numeric, handling missing data markers
    Returns None for missing data
    """
    if missing_markers is None:
        missing_markers = ['--', '×', '/', '#']
    if pd.isna(value):
        return None

    value_str = str(value).strip()

    # Check for missing data markers
    for marker in missing_markers:
        if marker in value_str:
            return None

    # Empty string
    if value_str == '':
        return None

    try:
        return float(value_str)
    except ValueError:
        return None


def interpolate_cloud_cover(df):
    """
    Interpolate missing cloud cover data
    Cloud cover is typically observed at 3-hour intervals in JMA data
    """
    # Linear interpolation
    df['cloud_interp'] = df['cloud_cover'].interpolate(method='linear', limit_direction='both')

    # Round to nearest integer (0-10)
    df['cloud_interp'] = df['cloud_interp'].round().clip(0, 10).fillna(0)

    return df


def jma_to_gwo_format(input_file, output_file, station_name='Tokyo'):
    """
    Convert JMA etrn CSV format to GWO format

    Parameters
    ----------
    input_file : str or Path
        Input JMA CSV file
    output_file : str or Path
        Output GWO-format CSV file
    station_name : str
        Station name (e.g., 'Tokyo', 'Osaka')
    """

    # Get station ID
    if station_name not in STATION_IDS:
        raise ValueError(f"Unknown station: {station_name}. Add to STATION_IDS mapping.")

    station_id, station_name_jp = STATION_IDS[station_name]

    # Read JMA CSV (skip first 2 header rows)
    df = pd.read_csv(input_file, skiprows=2, encoding='utf-8-sig')

    print(f"Read {len(df)} rows from {input_file}")
    print(f"Columns: {df.columns.tolist()}")

    # Parse cloud cover
    if df.columns[15] not in df.columns:  # Cloud column
        df['cloud_cover'] = None
    else:
        df['cloud_cover'] = df.iloc[:, 15].apply(parse_cloud_cover)

    # Interpolate cloud cover
    df = interpolate_cloud_cover(df)

    # Create GWO format DataFrame
    gwo_data = []

    for _, row in df.iterrows():
        # Extract values
        year = int(row.iloc[17])
        month = int(row.iloc[18])
        day = int(row.iloc[19])
        hour = int(row.iloc[0])

        # Convert values (JMA uses direct units, GWO uses ×0.1 for most)
        local_pressure = convert_value(row.iloc[1])
        sea_pressure = convert_value(row.iloc[2])
        temperature = convert_value(row.iloc[4])
        dew_point = convert_value(row.iloc[5])
        vapor_pressure = convert_value(row.iloc[6])
        humidity = convert_value(row.iloc[7])
        wind_speed = convert_value(row.iloc[8])
        wind_direction_text = row.iloc[9]
        sunshine = convert_value(row.iloc[10])
        solar = convert_value(row.iloc[11])
        precipitation = convert_value(row.iloc[3])

        # Convert to GWO units (×10 for 0.1 precision)
        local_pressure_gwo = int(local_pressure * 10) if local_pressure is not None else None
        sea_pressure_gwo = int(sea_pressure * 10) if sea_pressure is not None else None
        temperature_gwo = int(temperature * 10) if temperature is not None else None
        dew_point_gwo = int(dew_point * 10) if dew_point is not None else None
        vapor_pressure_gwo = int(vapor_pressure * 10) if vapor_pressure is not None else None
        humidity_gwo = int(humidity) if humidity is not None else None
        wind_speed_gwo = int(wind_speed * 10) if wind_speed is not None else None
        wind_direction_gwo = convert_wind_direction(wind_direction_text)

        # Cloud cover (use interpolated value)
        cloud_cover_gwo = int(row['cloud_interp']) if not pd.isna(row['cloud_interp']) else None

        # Sunshine and solar radiation
        sunshine_gwo = int(sunshine * 10) if sunshine is not None else None
        solar_gwo = int(solar * 100) if solar is not None else None  # MJ/m² to 0.01MJ/m²

        # Precipitation
        precipitation_gwo = int(precipitation * 10) if precipitation is not None else None

        # Set RMK codes
        # 8 = normal observation, 2 = not observed, 1 = missing
        def get_rmk(value):
            if value is None:
                return 1  # Missing
            return 8  # Normal

        # Build GWO row (33 columns)
        gwo_row = [
            station_id,                    # Col 1: Station ID
            station_name_jp,               # Col 2: Station name
            station_id,                    # Col 3: Station ID (repeated)
            year,                          # Col 4: Year
            month,                         # Col 5: Month
            day,                           # Col 6: Day
            hour,                          # Col 7: Hour
            local_pressure_gwo,            # Col 8: Local pressure (0.1hPa)
            get_rmk(local_pressure_gwo),   # Col 9: RMK
            sea_pressure_gwo,              # Col 10: Sea pressure (0.1hPa)
            get_rmk(sea_pressure_gwo),     # Col 11: RMK
            temperature_gwo,               # Col 12: Temperature (0.1°C)
            get_rmk(temperature_gwo),      # Col 13: RMK
            vapor_pressure_gwo,            # Col 14: Vapor pressure (0.1hPa)
            get_rmk(vapor_pressure_gwo),   # Col 15: RMK
            humidity_gwo,                  # Col 16: Humidity (%)
            get_rmk(humidity_gwo),         # Col 17: RMK
            wind_direction_gwo,            # Col 18: Wind direction (1-16)
            get_rmk(wind_direction_gwo),   # Col 19: RMK
            wind_speed_gwo,                # Col 20: Wind speed (0.1m/s)
            get_rmk(wind_speed_gwo),       # Col 21: RMK
            cloud_cover_gwo,               # Col 22: Cloud cover (10ths)
            2 if cloud_cover_gwo is None else 8,  # Col 23: RMK (2=not observed)
            0,                             # Col 24: Weather code (not available in JMA)
            2,                             # Col 25: RMK (2=not observed)
            dew_point_gwo,                 # Col 26: Dew point (0.1°C)
            get_rmk(dew_point_gwo),        # Col 27: RMK
            sunshine_gwo,                  # Col 28: Sunshine hours (0.1h)
            2 if sunshine_gwo is None else 8,  # Col 29: RMK
            solar_gwo,                     # Col 30: Solar radiation (0.01MJ/m²/h)
            2 if solar_gwo is None else 8,     # Col 31: RMK
            precipitation_gwo,             # Col 32: Precipitation (0.1mm/h)
            get_rmk(precipitation_gwo),    # Col 33: RMK
        ]

        gwo_data.append(gwo_row)

    # Create DataFrame
    gwo_df = pd.DataFrame(gwo_data)

    # Save to CSV (no header, no index)
    gwo_df.to_csv(output_file, header=False, index=False, encoding='utf-8')

    print(f"Converted {len(gwo_df)} rows to GWO format")
    print(f"Saved to: {output_file}")

    # Statistics
    cloud_missing = gwo_df[21].isna().sum()
    cloud_total = len(gwo_df)
    cloud_interpolated = cloud_total - cloud_missing
    print(f"Cloud cover: {cloud_interpolated}/{cloud_total} values (interpolated)")

    return gwo_df


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Convert JMA format to GWO format')
    parser.add_argument('input', help='Input JMA CSV file')
    parser.add_argument('output', help='Output GWO CSV file')
    parser.add_argument('--station', default='Tokyo', help='Station name (default: Tokyo)')

    args = parser.parse_args()

    jma_to_gwo_format(args.input, args.output, args.station)
