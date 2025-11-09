#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration module for GWO-AMD
Reads settings from environment variables with fallback to defaults
"""

import os
from pathlib import Path

# Load .env file if it exists (optional, requires python-dotenv)
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / '.env'
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    # python-dotenv not installed, will use system environment variables only
    pass


def get_data_dir():
    """Get base data directory from environment or default"""
    return os.getenv('DATA_DIR', '/mnt/d/Data')


def get_jma_database_dir():
    """Get JMA Database directory"""
    # Check for explicit override first
    jma_db = os.getenv('JMA_DATABASE_DIR')
    if jma_db:
        return jma_db

    # Construct from DATA_DIR
    data_dir = get_data_dir()
    return os.path.join(data_dir, 'met', 'JMA_DataBase')


def get_gwo_hourly_dir():
    """Get GWO hourly data directory"""
    override = os.getenv('GWO_HOURLY_DIR')
    if override:
        return override
    return os.path.join(get_jma_database_dir(), 'GWO', 'Hourly')


def get_gwo_daily_dir():
    """Get GWO daily data directory"""
    override = os.getenv('GWO_DAILY_DIR')
    if override:
        return override
    return os.path.join(get_jma_database_dir(), 'GWO', 'Daily')


def get_amd_dir():
    """Get AMD data directory"""
    override = os.getenv('AMD_DIR')
    if override:
        return override
    return os.path.join(get_jma_database_dir(), 'AMD')


def get_jma_download_dir():
    """Get JMA web downloader output directory"""
    return os.getenv('JMA_DOWNLOAD_DIR', './jma_data')


# Export configuration as dictionary
CONFIG = {
    'DATA_DIR': get_data_dir(),
    'JMA_DATABASE_DIR': get_jma_database_dir(),
    'GWO_HOURLY_DIR': get_gwo_hourly_dir(),
    'GWO_DAILY_DIR': get_gwo_daily_dir(),
    'AMD_DIR': get_amd_dir(),
    'JMA_DOWNLOAD_DIR': get_jma_download_dir(),
}


if __name__ == '__main__':
    # Print configuration when run as script
    print("GWO-AMD Configuration:")
    print("=" * 60)

    # Input directories (must exist)
    input_dirs = ['DATA_DIR', 'JMA_DATABASE_DIR', 'GWO_HOURLY_DIR', 'GWO_DAILY_DIR', 'AMD_DIR']
    # Output directories (created automatically)
    output_dirs = ['JMA_DOWNLOAD_DIR']

    print("\nInput Data Directories (should exist):")
    print("-" * 60)
    for key in input_dirs:
        value = CONFIG[key]
        exists = "✓" if os.path.isdir(value) else "✗"
        print(f"{exists} {key:20s} = {value}")

    print("\nOutput Directories (created automatically):")
    print("-" * 60)
    for key in output_dirs:
        value = CONFIG[key]
        exists = "✓" if os.path.isdir(value) else "○"
        status = "(exists)" if os.path.isdir(value) else "(will be created)"
        print(f"{exists} {key:20s} = {value} {status}")

    print("=" * 60)
