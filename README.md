# Wind Effect Calculator (Jupyter + SAGA GIS)

Interactive Jupyter UI to compute **Wind Effect** from a DEM using **SAGA GIS** (`ta_morphometry` → tool 15).  
Includes live direction preview (rotating arrow), DEM upload, and an output directory chooser.

## Features

- Point to your `saga_cmd` and run SAGA’s Wind Effect with one click.
- **FROM / TO** direction logic with a **live rotating arrow** showing the actual **TO (SAGA)** direction used.
- Provide DEM by **path** or **upload**.
- Choose an **output directory** (folder picker via `ipyfilechooser`; fallback to native dialog or a text field).
- Optional **GeoTIFF export** alongside SAGA’s `.sgrd`.
- Quick-look previews (matplotlib) for input and output rasters.

---

## Prerequisites (once)

- **Python 3.10+** (3.12+ recommended)
- **SAGA GIS** (provides `saga_cmd`)
  - Windows: typical path `C:\Program Files\SAGA-[version]\saga_cmd.exe`
  - macOS / Linux: `saga_cmd` available on `PATH` after installing SAGA
- **Git** (to clone the repo)
- **Linux only (if missing):** `python3-venv`
  - Ubuntu/Debian: `sudo apt install python3-venv`

> You don’t need to pre-install Python libraries. The setup script creates a virtualenv and installs everything.

---

## One-shot setup

From the repository root, run the setup script. It creates `.venv`, installs requirements, and registers a Jupyter kernel named **wind_processor**.

Then open the notebook and select the **wind_processor** kernel.

---

## Using the UI

1. **saga_cmd** – Paste the full path to `saga_cmd.exe` (Windows) or `saga_cmd` (macOS/Linux).  
   You can also paste the folder containing it; the UI resolves the executable.
2. **Dir mode & Direction (°)** – Choose **FROM (met)** or **TO (SAGA)** and set degrees (0–359).  
   The **arrow** shows the **TO (SAGA)** direction actually passed to SAGA.
3. **DEM** – Provide a **path** or **Upload DEM** (`.tif/.tiff/.sgrd/.sdat/.sg-grd/.sg-grd-z`). **Note: if your goal is to simulate the wind exposure of a city you will need to consider the height of the buildings as well.**
4. **Output directory** – Pick a folder for outputs.  
   Uses `ipyfilechooser` if available; otherwise a **Browse…** (native dialog) or text box.  
   *Note:* native dialogs need a local desktop session. On headless/remote servers, use the text field.
5. **Output base** – Optional base **name** (no extension). If empty → `<DEM>_WindEffect`.
6. **Also export GeoTIFF (.tif)** – Toggle to write a `.tif` next to the `.sgrd`.
7. **Advanced** – Tune **MAXDIST (km)**, **ACCEL**, **PYRAMIDS**, **OLDVER**.
8. Click **Run Wind Effect**.  
   The log shows progress; quick-look previews appear when done.

### Outputs

- **SAGA grid:** `<output_base>.sgrd`
- **GeoTIFF (optional):** `<output_base>.tif`  
- Location: chosen **Output directory** (or DEM folder if none selected).

---

## Requirements

Installed automatically by `setup.py`:

- `ipykernel`, `jupyterlab`, `notebook`

From `requirements.txt` (already included; adjust if needed):

```
numpy>=1.22
matplotlib>=3.6
ipywidgets>=8
rasterio>=1.5; python_version >= "3.12"
pyogrio>=0.11
geopandas>=1.0
ipyfilechooser>=0.6
```

> `tkinter` (for the native folder dialog fallback) ships with most Python installers on Windows/macOS.  
> Some Linux distributions split it into a package, e.g. `sudo apt install python3-tk`.

---

## Troubleshooting

**“saga_cmd not found”**  
- Verify path:  
  - Windows: `C:\Program Files\SAGA-GIS\bin\saga_cmd.exe`  
  - macOS/Linux: ensure `saga_cmd` exists and is executable
- Paste either the full executable path **or** the folder containing it.

**Rasterio / GDAL errors**  
- Update pip/wheel inside the venv and install the stack that matches your Python:
  ```bash
  # Windows
  .venv\Scripts\python -m pip install --upgrade pip setuptools wheel
  .venv\Scripts\python -m pip install "rasterio>=1.5" "pyogrio>=0.11" "geopandas>=1.0"

  # macOS / Linux
  .venv/bin/python -m pip install --upgrade pip setuptools wheel
  .venv/bin/python -m pip install "rasterio>=1.5" "pyogrio>=0.11" "geopandas>=1.0"
  ```

**Linux: `No module named venv`**  
```bash
sudo apt install python3-venv
```

**Folder dialog doesn’t open**  
- On headless servers, native dialogs are unavailable. Use the text field or the `ipyfilechooser` picker.

**Widgets not showing in classic Notebook**  
- JupyterLab 3/4 doesn’t need `nbextension`. For classic Notebook:
  ```bash
  # Windows
  .venv\Scripts\python -m pip install notebook widgetsnbextension nbclassic
  .venv\Scripts\python -m jupyter nbextension enable --py widgetsnbextension --sys-prefix

  # macOS / Linux
  .venv/bin/python -m pip install notebook widgetsnbextension nbclassic
  .venv/bin/jupyter nbextension enable --py widgetsnbextension --sys-prefix
  ```

**GeoTIFF export warning**  
- The tool still writes the `.sgrd`. Check permissions and disk space; then retry export.

---

## Development

- Virtualenv lives in `.venv` (ignored by Git).

## Pipeline CLI

The repo now also includes an end-to-end pipeline for:

- reading an AOI from file
- downloading `MDT02` and `MDSE2` (building heights) from CNIG for that AOI
- building a `terrain + buildings` surface at `2 m`
- extracting hourly `u10` and `v10` wind from `ERA5-Land time-series`
- deriving wind speed and direction
- computing `Wind Effect` in **8 directions** with **SAGA GIS**
- combining the 8 directional rasters into a final `0-100` wind exposure map weighted toward strong-wind episodes

Run it with:

```bash
python -m wind_calculator --aoi path/to/aoi.gpkg --output-dir outputs --saga-cmd "C:\Program Files\SAGA-GIS\saga_cmd.exe"
```

Main outputs:

- `terrain_2m.tif`
- `buildings_height_2m.tif`
- `terrain_buildings_2m.tif`
- `wind_timeseries.csv`
- `wind_climatology.json`
- `wind_exposure_2m.tif`

CDS credentials:

- Copy `config/cdsapi.credentials.example` to `config/cdsapi.credentials`
- Fill `url` and `key` in `config/cdsapi.credentials`
- `config/cdsapi.credentials` is ignored by Git
- If that file does not exist, the pipeline falls back to `~/.cdsapirc`

Notes:

- The AOI is processed **without buffer**.
- The wind climatology uses **8 sectors**: `N, NE, E, SE, S, SW, W, NW`.
- The wind source is **ERA5-Land hourly time-series** using the nearest grid point.
- The directional weights default to `strong_wind`: only the upper tail of hourly speeds contributes, controlled by `--strong-wind-percentile`, `--strong-wind-min-mps`, and `--strong-wind-exponent`.
- You need valid **Copernicus Climate Data Store** credentials configured for `cdsapi`.
- `SAGA GIS` must be installed and `saga_cmd` must be available via `--saga-cmd` or `PATH`.
