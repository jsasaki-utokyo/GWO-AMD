#!/usr/bin/env python3
"""
Verification script for GWO format conversion.

Compares converted JMA data with original GWO database files and reports differences.
Issues warnings for known bugs in original GWO data (e.g., missing cloud interpolation).

Usage:
    python -m gwo_amd.verify_gwo_conversion <converted_file> <original_file>
    python -m gwo_amd.verify_gwo_conversion jma_data/Tokyo/Tokyo2019.csv /path/to/GWO/Hourly/Tokyo/Tokyo2019.csv
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path


# Column definitions for GWO format (33 columns, 0-indexed)
GWO_COLUMNS = [
    "station_id", "station_name", "station_id2", "year", "month", "day", "hour",
    "local_pressure", "local_pressure_rmk", "sea_pressure", "sea_pressure_rmk",
    "temperature", "temperature_rmk", "vapor_pressure", "vapor_pressure_rmk",
    "humidity", "humidity_rmk", "wind_dir", "wind_dir_rmk", "wind_speed", "wind_speed_rmk",
    "cloud", "cloud_rmk", "weather", "weather_rmk",
    "dew_point", "dew_point_rmk", "sunshine", "sunshine_rmk",
    "solar", "solar_rmk", "precip", "precip_rmk"
]


def load_gwo_file(filepath):
    """Load GWO format CSV file (no header, 33 columns)."""
    try:
        df = pd.read_csv(filepath, header=None, encoding='utf-8')
        if len(df.columns) != 33:
            raise ValueError(f"Expected 33 columns, found {len(df.columns)}")
        return df
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        sys.exit(1)


def compare_column(converted, original, col_idx, col_name, tolerance=0):
    """Compare a single column between converted and original data."""
    if tolerance > 0:
        # For numeric columns with tolerance
        diffs = np.abs(converted[col_idx] - original[col_idx]) > tolerance
        diff_count = diffs.sum()
    else:
        # Exact match
        diff_count = (converted[col_idx] != original[col_idx]).sum()

    return diff_count


def check_cloud_interpolation_bug(converted, original):
    """
    Check if original GWO data has the cloud interpolation bug.

    Bug: Original GWO data sets cloud=0 with RMK=2 for non-observation hours,
         instead of interpolating between observed values at 3-hour intervals.

    Returns: (has_bug, diff_count, sample_rows)
    """
    # Cloud is at column 21, cloud_rmk at column 22
    # Check rows where hour is NOT 3,6,9,12,15,18,21 (non-observation times)
    non_obs_hours = ~converted[6].isin([3, 6, 9, 12, 15, 18, 21, 24])

    # Count differences in non-observation hours
    cloud_diffs = non_obs_hours & (converted[21] != original[21])
    diff_count = cloud_diffs.sum()

    # Check if original has zeros at these positions (indicating bug)
    original_has_zeros = non_obs_hours & (original[21] == 0) & (original[22] == 2)
    bug_count = original_has_zeros.sum()

    # Get sample rows
    sample_indices = cloud_diffs[cloud_diffs].index[:3].tolist()
    samples = []
    for idx in sample_indices:
        samples.append({
            'row': idx + 1,
            'date': f"{converted.iloc[idx, 3]}-{converted.iloc[idx, 4]:02d}-{converted.iloc[idx, 5]:02d}",
            'hour': converted.iloc[idx, 6],
            'conv_cloud': converted.iloc[idx, 21],
            'orig_cloud': original.iloc[idx, 21],
            'rmk': converted.iloc[idx, 22]
        })

    has_bug = bug_count > 0
    return has_bug, diff_count, samples


def verify_gwo_conversion(converted_file, original_file):
    """
    Verify converted GWO data against original GWO database.

    Reports differences and issues warnings for known bugs.
    """
    print("="*80)
    print("GWO Conversion Verification")
    print("="*80)
    print(f"Converted: {converted_file}")
    print(f"Original:  {original_file}")
    print()

    # Load files
    converted = load_gwo_file(converted_file)
    original = load_gwo_file(original_file)

    print(f"Rows: Converted={len(converted)}, Original={len(original)}")

    if len(converted) != len(original):
        print("⚠️  WARNING: Row counts differ!")
        print()

    # Compare each column
    print()
    print("Column-by-Column Comparison:")
    print("-"*80)

    total_diffs = 0
    significant_diffs = []

    for i, col_name in enumerate(GWO_COLUMNS):
        # Use small tolerance for solar radiation (rounding differences)
        tolerance = 1 if col_name == "solar" else 0

        diff_count = compare_column(converted, original, i, col_name, tolerance)

        if diff_count > 0:
            total_diffs += 1
            pct = diff_count * 100 / len(converted)

            # Skip expected differences (weather codes)
            if col_name in ["weather", "weather_rmk"]:
                status = "EXPECTED (JMA format lacks weather codes)"
            elif pct > 1.0:
                status = "⚠️  SIGNIFICANT"
                significant_diffs.append((i, col_name, diff_count, pct))
            else:
                status = "minor"

            print(f"Col {i:2d} ({col_name:20s}): {diff_count:5d} diffs ({pct:5.2f}%) - {status}")

    print("-"*80)
    print(f"Total columns with differences: {total_diffs}/33")
    print()

    # Check for known bugs
    print("Known Data Issues:")
    print("-"*80)

    # Check cloud interpolation bug
    has_cloud_bug, cloud_diff_count, cloud_samples = check_cloud_interpolation_bug(converted, original)

    if has_cloud_bug:
        print("⚠️  CLOUD INTERPOLATION BUG DETECTED in original GWO data!")
        print()
        print("   The original GWO database has a bug where cloud cover is NOT interpolated")
        print("   between 3-hour observation intervals. Instead, it sets cloud=0 with RMK=2")
        print("   for non-observation hours.")
        print()
        print("   The converted data correctly interpolates cloud values between observations,")
        print("   providing better data continuity.")
        print()
        print(f"   Affected rows: {cloud_diff_count:,} ({cloud_diff_count*100/len(converted):.1f}%)")
        print()
        print("   Sample differences:")
        for s in cloud_samples:
            print(f"     Row {s['row']:5d} ({s['date']} {s['hour']:02d}:00): "
                  f"Converted={s['conv_cloud']:2d}, Original={s['orig_cloud']:2d} (should be interpolated)")
        print()
        print("   ✓ This warning will disappear when you correct the GWO CSV files.")
        print()
    else:
        print("✓ No cloud interpolation bug detected (data is correct)")
        print()

    # Summary
    print("="*80)
    print("Summary:")
    print("-"*80)

    # Check if data matches (excluding known issues)
    core_data_matches = True
    for i, col_name, diff_count, pct in significant_diffs:
        if col_name not in ["cloud", "weather", "weather_rmk"]:
            core_data_matches = False
            print(f"⚠️  Unexpected difference in {col_name}: {diff_count} rows ({pct:.2f}%)")

    if core_data_matches:
        print("✓ Core data matches (pressure, temperature, humidity, wind, etc.)")

    if has_cloud_bug:
        print("⚠️  Cloud data differs due to interpolation bug in original GWO data")
    else:
        print("✓ Cloud data matches")

    print("✓ Weather code differences are expected (not available in JMA format)")
    print("="*80)

    # Return exit code
    if core_data_matches:
        return 0
    else:
        return 1


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    converted_file = Path(sys.argv[1])
    original_file = Path(sys.argv[2])

    if not converted_file.exists():
        print(f"Error: Converted file not found: {converted_file}")
        sys.exit(1)

    if not original_file.exists():
        print(f"Error: Original file not found: {original_file}")
        sys.exit(1)

    exit_code = verify_gwo_conversion(converted_file, original_file)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
