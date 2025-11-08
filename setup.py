#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Setup script for GWO-AMD package
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_file = Path(__file__).parent / "README.md"
long_description = readme_file.read_text(encoding="utf-8") if readme_file.exists() else ""

setup(
    name="gwo-amd",
    version="0.1.0",
    description="Japan Meteorological Agency's meteorological dataset handling tool",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Jun Sasaki",
    url="https://github.com/jsasaki-utokyo/GWO-AMD",
    license="MIT",
    py_modules=[
        "mod_class_met",
        "jma_weather_downloader",
        "test_jma_downloader",
        "test_jma_week",
        "config",
    ],
    python_requires=">=3.12",
    install_requires=[
        "numpy",
        "pandas>=2.0.0",
        "matplotlib",
        "requests>=2.28.0",
        "lxml>=4.9.0",
        "html5lib>=1.1",
        "beautifulsoup4>=4.11.0",
        "python-dateutil",
        "python-dotenv",
    ],
    extras_require={
        "dev": [
            "jupyter",
            "notebook",
            "ipykernel",
        ],
    },
    entry_points={
        "console_scripts": [
            "jma-download=jma_weather_downloader:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Topic :: Scientific/Engineering :: Atmospheric Science",
    ],
)
