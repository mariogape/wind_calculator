from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, bounds as window_bounds


BUILDING_NODATA = -9999.0
SURFACE_NODATA = -9999.0


@dataclass(frozen=True)
class CfdTestDatasetOutputs:
    terrain_path: Path
    building_heights_path: Path
    surface_model_path: Path
    bounds_geojson_path: Path
    metadata_path: Path


def _write_raster(
    *,
    path: Path,
    array: np.ndarray,
    profile: dict,
    nodata: float,
) -> Path:
    out_profile = profile.copy()
    out_profile.pop("blockxsize", None)
    out_profile.pop("blockysize", None)
    out_profile.pop("predictor", None)
    out_profile.update(
        dtype="float32",
        count=1,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **out_profile) as dst:
        dst.write(array.astype(np.float32), 1)
    return path


def _window_bounds(src, window: Window) -> tuple[float, float, float, float]:
    return window_bounds(window, src.transform)


def create_cfd_test_dataset(
    *,
    source_dir: str | Path,
    output_dir: str | Path,
    window_size: int = 512,
    stride: int | None = None,
    min_building_height_m: float = 2.0,
) -> CfdTestDatasetOutputs:
    """
    Create a compact terrain/buildings dataset for CFD testing.

    This pipeline is intentionally independent from the wind-exposure pipeline:
    it only reads already-generated rasters from ``source_dir`` and writes
    a clipped test package for CFD experimentation.
    """
    source_root = Path(source_dir)
    output_root = Path(output_dir)

    terrain_path = next(source_root.glob("terrain_*.tif"))
    buildings_path = next(source_root.glob("buildings_height_*.tif"))
    surface_path = next(source_root.glob("terrain_buildings_*.tif"))

    with rasterio.open(terrain_path) as terrain_src, rasterio.open(buildings_path) as buildings_src, rasterio.open(
        surface_path
    ) as surface_src:
        terrain = terrain_src.read(1)
        buildings = buildings_src.read(1)
        surface = surface_src.read(1)

        terrain_valid = np.isfinite(terrain)
        if terrain_src.nodata is not None:
            terrain_valid &= terrain != terrain_src.nodata

        building_values = np.where(np.isfinite(buildings), buildings, 0.0)
        if buildings_src.nodata is not None:
            building_values = np.where(buildings == buildings_src.nodata, 0.0, building_values)
        building_mask = terrain_valid & (building_values >= min_building_height_m)

        if not np.any(building_mask):
            raise RuntimeError("No se han encontrado edificios suficientemente altos en el raster fuente.")

        if stride is None:
            stride = max(64, window_size // 4)

        best_score: tuple[int, int, int] | None = None
        for row in range(0, building_mask.shape[0] - window_size + 1, stride):
            for col in range(0, building_mask.shape[1] - window_size + 1, stride):
                score = int(building_mask[row : row + window_size, col : col + window_size].sum())
                if best_score is None or score > best_score[0]:
                    best_score = (score, row, col)

        if best_score is None:
            raise RuntimeError("No se ha podido encontrar una ventana urbana valida para el dataset de prueba.")

        _, row_off, col_off = best_score
        window = Window(col_off=col_off, row_off=row_off, width=window_size, height=window_size)
        window_transform = terrain_src.window_transform(window)

        r0 = int(window.row_off)
        r1 = int(window.row_off + window.height)
        c0 = int(window.col_off)
        c1 = int(window.col_off + window.width)

        terrain_clip = terrain[r0:r1, c0:c1].astype(np.float32)
        surface_clip = surface[r0:r1, c0:c1].astype(np.float32)
        terrain_valid_clip = terrain_valid[r0:r1, c0:c1]
        building_values_clip = building_values[r0:r1, c0:c1].astype(np.float32)

        building_clip = np.full(terrain_clip.shape, BUILDING_NODATA, dtype=np.float32)
        building_clip[terrain_valid_clip] = 0.0
        building_clip[terrain_valid_clip] = np.maximum(building_values_clip[terrain_valid_clip], 0.0)

        terrain_profile = terrain_src.profile.copy()
        terrain_profile.update(height=window_size, width=window_size, transform=window_transform)
        building_profile = buildings_src.profile.copy()
        building_profile.update(height=window_size, width=window_size, transform=window_transform)
        surface_profile = surface_src.profile.copy()
        surface_profile.update(height=window_size, width=window_size, transform=window_transform)

        terrain_out = _write_raster(
            path=output_root / terrain_path.name,
            array=terrain_clip,
            profile=terrain_profile,
            nodata=float(terrain_src.nodata if terrain_src.nodata is not None else SURFACE_NODATA),
        )
        buildings_out = _write_raster(
            path=output_root / buildings_path.name,
            array=building_clip,
            profile=building_profile,
            nodata=BUILDING_NODATA,
        )
        surface_out = _write_raster(
            path=output_root / surface_path.name,
            array=surface_clip,
            profile=surface_profile,
            nodata=float(surface_src.nodata if surface_src.nodata is not None else SURFACE_NODATA),
        )

        minx, miny, maxx, maxy = _window_bounds(terrain_src, window)
        transformer = Transformer.from_crs(terrain_src.crs, 4326, always_xy=True)
        lon_min, lat_min = transformer.transform(minx, miny)
        lon_max, lat_max = transformer.transform(maxx, maxy)

        bounds_geojson = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "source_dir": str(source_root.resolve()),
                        "window_size_px": int(window_size),
                        "building_pixel_score": int(best_score[0]),
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [lon_min, lat_min],
                                [lon_max, lat_min],
                                [lon_max, lat_max],
                                [lon_min, lat_max],
                                [lon_min, lat_min],
                            ]
                        ],
                    },
                }
            ],
        }
        bounds_geojson_path = output_root / "test_area.geojson"
        bounds_geojson_path.write_text(json.dumps(bounds_geojson, indent=2), encoding="utf-8")

        metadata = {
            "source_dir": str(source_root.resolve()),
            "window_size_px": int(window_size),
            "window_size_m": float(window_size * abs(terrain_src.res[0])),
            "row_off": int(row_off),
            "col_off": int(col_off),
            "building_pixel_score": int(best_score[0]),
            "projected_bounds": {
                "minx": float(minx),
                "miny": float(miny),
                "maxx": float(maxx),
                "maxy": float(maxy),
            },
            "crs": terrain_src.crs.to_string() if terrain_src.crs else None,
            "terrain_path": str(terrain_out.resolve()),
            "building_heights_path": str(buildings_out.resolve()),
            "surface_model_path": str(surface_out.resolve()),
        }
        metadata_path = output_root / "dataset_info.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return CfdTestDatasetOutputs(
        terrain_path=terrain_out,
        building_heights_path=buildings_out,
        surface_model_path=surface_out,
        bounds_geojson_path=bounds_geojson_path,
        metadata_path=metadata_path,
    )
