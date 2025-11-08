# GWO-AMD Configuration Guide

This document explains how to configure data directory paths for GWO-AMD.

## Configuration Options

GWO-AMD supports multiple configuration methods, listed in order of precedence:

1. **Environment variables** (highest priority)
2. **`.env` file** in project root
3. **Default values** (fallback)

## Quick Setup

### Step 1: Copy the example environment file

```bash
cp .env.example .env
```

### Step 2: Edit `.env` with your paths

```bash
# Example for WSL/Linux system with data on D: drive
DATA_DIR=/mnt/d/Data

# Or specify full path directly
# JMA_DATABASE_DIR=/mnt/d/Data/met/JMA_DataBase
```

### Step 3: Verify configuration

```bash
python config.py
```

This will display your configuration and indicate which directories exist (✓) or are missing (✗).

## Environment Variables

### Primary Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATA_DIR` | Base data directory | `/mnt/d/Data` |
| `JMA_DATABASE_DIR` | JMA Database root (overrides `DATA_DIR/met/JMA_DataBase`) | `${DATA_DIR}/met/JMA_DataBase` |
| `JMA_DOWNLOAD_DIR` | Output directory for JMA web downloader | `./jma_data` |

### Specific Database Paths (Optional)

These allow fine-grained control. If not set, they are constructed from `JMA_DATABASE_DIR`:

| Variable | Default Value |
|----------|---------------|
| `GWO_HOURLY_DIR` | `${JMA_DATABASE_DIR}/GWO/Hourly` |
| `GWO_DAILY_DIR` | `${JMA_DATABASE_DIR}/GWO/Daily` |
| `AMD_DIR` | `${JMA_DATABASE_DIR}/AMD` |

## Expected Directory Structure

```
${DATA_DIR}/
  └── met/
      └── JMA_DataBase/
          ├── GWO/
          │   ├── Hourly/
          │   │   ├── Tokyo/
          │   │   │   ├── Tokyo2014.csv
          │   │   │   ├── Tokyo2015.csv
          │   │   │   └── ...
          │   │   ├── Chiba/
          │   │   └── ...
          │   └── Daily/
          │       ├── Tokyo/
          │       └── ...
          └── AMD/
              └── ...
```

## Usage in Python Scripts

### Using the config module

```python
from config import CONFIG

# Get configured paths
gwo_hourly = CONFIG['GWO_HOURLY_DIR']
print(f"GWO Hourly data: {gwo_hourly}")

# Or use helper functions
from config import get_gwo_hourly_dir, get_jma_download_dir

data_dir = get_gwo_hourly_dir()
output_dir = get_jma_download_dir()
```

### Using with Met_GWO class

```python
from mod_class_met import Met_GWO
from config import get_gwo_hourly_dir

# Use configured path
met = Met_GWO(
    datetime_ini="2014-1-1 00:00:00",
    datetime_end="2014-6-1 00:00:00",
    stn="Tokyo",
    dirpath=get_gwo_hourly_dir()
)
```

### Using in Jupyter Notebooks

Add this to the first cell of your notebook:

```python
from config import CONFIG

# Use configured paths
db_path = CONFIG['GWO_HOURLY_DIR']
print(f"Using data directory: {db_path}")
```

## Setting Environment Variables

### Option 1: Using `.env` file (Recommended)

Create a `.env` file in the project root:

```bash
# .env
DATA_DIR=/mnt/d/Data
```

The `python-dotenv` package automatically loads this file when you import the `config` module.

### Option 2: Shell environment (session-specific)

```bash
# Bash/Zsh
export DATA_DIR=/mnt/d/Data
export JMA_DOWNLOAD_DIR=./my_data

# Run your script
python script.py
```

### Option 3: Conda environment variables (persistent)

```bash
# Activate your environment
conda activate gwo-amd

# Set environment variables for this conda environment
conda env config vars set DATA_DIR=/mnt/d/Data
conda env config vars set JMA_DATABASE_DIR=/mnt/d/Data/met/JMA_DataBase

# Reactivate to apply changes
conda deactivate
conda activate gwo-amd

# Verify
conda env config vars list
```

### Option 4: Shell profile (persistent across sessions)

Add to `~/.bashrc` or `~/.zshrc`:

```bash
# GWO-AMD Configuration
export DATA_DIR=/mnt/d/Data
export JMA_DATABASE_DIR=/mnt/d/Data/met/JMA_DataBase
```

Then reload:
```bash
source ~/.bashrc  # or ~/.zshrc
```

## Migration from Hardcoded Paths

If you have existing notebooks or scripts with hardcoded paths, update them:

### Before:
```python
db_path = "/mnt/d/dat/met/JMA_DataBase/GWO/Hourly/"
```

### After:
```python
from config import get_gwo_hourly_dir
db_path = get_gwo_hourly_dir()
```

## Troubleshooting

### Check current configuration

```bash
python config.py
```

Output shows:
- ✓ = Directory exists
- ✗ = Directory not found

### Override for single script execution

```bash
DATA_DIR=/custom/path python script.py
```

### Windows vs WSL Paths

If you're using WSL (Windows Subsystem for Linux):

- Windows path: `D:\Data\met\JMA_DataBase`
- WSL path: `/mnt/d/Data/met/JMA_DataBase`

Use the WSL path in your `.env` file when running from WSL.

## Best Practices

1. **Never commit `.env`** - It's already in `.gitignore`
2. **Commit `.env.example`** - Helps other users set up their environment
3. **Use environment variables** - More portable than hardcoded paths
4. **Document custom paths** - If you use non-standard locations, document them
5. **Check paths exist** - Run `python config.py` to verify setup

## Alternative: Symlinks (Not Recommended)

While you can create a symlink to `JMA_DataBase` in the project directory:

```bash
ln -s /mnt/d/Data/met/JMA_DataBase ./JMA_DataBase
```

**We recommend against this because:**
- Not portable across systems
- Doesn't work well on Windows without admin privileges
- Can cause confusion about data location
- Hard to manage multiple data sources

Use environment variables instead for better flexibility and portability.
