from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path

import laspy
import numpy as np
import rasterio
from pyproj import CRS
from pyproj.aoi import AreaOfInterest
from pyproj.database import query_utm_crs_info
from rasterio.features import geometry_mask
from rasterio.fill import fillnodata
from rasterio.transform import from_origin
from shapely.geometry import mapping

from .aoi import AOI, transform_geometry


GROUND_CLASS = 2
BUILDING_CLASS = 6
BUILDING_NODATA = -9999.0


@dataclass(frozen=True)
class LidarSurfaceOutputs:
    terrain_path: Path
    building_heights_path: Path
    surface_model_path: Path
    lidar_product_code: str
    resolution_m: float


def _resolution_label(resolution: float) -> str:
    if float(resolution).is_integer():
        return f"{int(resolution)}m"
    return f"{str(resolution).replace('.', 'p')}m"


def _estimate_projected_crs_from_aoi(aoi: AOI) -> CRS:
    bbox = aoi.bounds_4326
    candidates = query_utm_crs_info(
        datum_name="ETRS89",
        area_of_interest=AreaOfInterest(*bbox),
    )
    for candidate in candidates:
        if candidate.code == "25829":
            return CRS.from_epsg(25829)
    for candidate in candidates:
        if candidate.code == "25830":
            return CRS.from_epsg(25830)
    for candidate in candidates:
        if candidate.code == "25831":
            return CRS.from_epsg(25831)
    if candidates:
        return CRS.from_epsg(int(candidates[0].code))
    raise RuntimeError("No se ha podido estimar un CRS proyectado UTM ETRS89 para el AOI.")


def _grid_from_bounds(bounds: tuple[float, float, float, float], resolution: float) -> tuple[float, float, int, int]:
    minx, miny, maxx, maxy = bounds
    origin_x = floor(minx / resolution) * resolution
    origin_y = ceil(maxy / resolution) * resolution
    cols = int(ceil((maxx - origin_x) / resolution))
    rows = int(ceil((origin_y - miny) / resolution))
    return origin_x, origin_y, rows, cols


def _write_raster(
    *,
    path: Path,
    array: np.ndarray,
    transform,
    crs: CRS,
    nodata: float,
) -> Path:
    profile = {
        "driver": "GTiff",
        "height": array.shape[0],
        "width": array.shape[1],
        "count": 1,
        "dtype": "float32",
        "crs": crs,
        "transform": transform,
        "nodata": nodata,
        "compress": "deflate",
        "tiled": True,
        "blockxsize": 256,
        "blockysize": 256,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(array.astype(np.float32), 1)
    return path


def build_lidar_surface(
    *,
    aoi: AOI,
    lidar_paths: list[Path],
    lidar_product_code: str,
    output_dir: str | Path,
    resolution: float = 1.0,
    terrain_fill_distance_m: float = 64.0,
) -> LidarSurfaceOutputs:
    if not lidar_paths:
        raise ValueError("No hay teselas LiDAR para construir la superficie.")

    target_crs = _estimate_projected_crs_from_aoi(aoi)
    aoi_geometry = transform_geometry(aoi.geometry_4326, 4326, target_crs)
    origin_x, origin_y, rows, cols = _grid_from_bounds(aoi_geometry.bounds, resolution)
    transform = from_origin(origin_x, origin_y, resolution, resolution)
    bounds = aoi_geometry.bounds

    terrain_sum = np.zeros((rows, cols), dtype=np.float64)
    terrain_count = np.zeros((rows, cols), dtype=np.uint32)
    building_max = np.full((rows, cols), -np.inf, dtype=np.float32)

    for lidar_path in lidar_paths:
        las = laspy.read(lidar_path)
        x = np.asarray(las.x)
        y = np.asarray(las.y)
        z = np.asarray(las.z, dtype=np.float32)
        classification = np.asarray(las.classification)

        in_bbox = (
            (x >= bounds[0])
            & (x <= bounds[2])
            & (y >= bounds[1])
            & (y <= bounds[3])
        )
        if not np.any(in_bbox):
            continue

        x = x[in_bbox]
        y = y[in_bbox]
        z = z[in_bbox]
        classification = classification[in_bbox]

        ci = np.floor((x - origin_x) / resolution).astype(np.int32)
        ri = np.floor((origin_y - y) / resolution).astype(np.int32)
        in_grid = (ci >= 0) & (ci < cols) & (ri >= 0) & (ri < rows)
        if not np.any(in_grid):
            continue

        ci = ci[in_grid]
        ri = ri[in_grid]
        z = z[in_grid]
        classification = classification[in_grid]

        ground_mask = classification == GROUND_CLASS
        if np.any(ground_mask):
            np.add.at(terrain_sum, (ri[ground_mask], ci[ground_mask]), z[ground_mask].astype(np.float64))
            np.add.at(terrain_count, (ri[ground_mask], ci[ground_mask]), 1)

        building_mask = classification == BUILDING_CLASS
        if np.any(building_mask):
            np.maximum.at(building_max, (ri[building_mask], ci[building_mask]), z[building_mask])

    terrain = np.full((rows, cols), -9999.0, dtype=np.float32)
    valid_ground = terrain_count > 0
    if not np.any(valid_ground):
        raise RuntimeError("Las teselas LiDAR no contienen puntos de terreno clasificados dentro del AOI.")
    terrain[valid_ground] = (terrain_sum[valid_ground] / terrain_count[valid_ground]).astype(np.float32)
    fill_search_distance_pixels = max(1.0, float(terrain_fill_distance_m) / float(resolution))
    terrain = fillnodata(
        terrain,
        mask=valid_ground,
        max_search_distance=fill_search_distance_pixels,
        smoothing_iterations=0,
    ).astype(np.float32)

    building_roofs = np.full((rows, cols), np.nan, dtype=np.float32)
    valid_buildings = np.isfinite(building_max)
    building_roofs[valid_buildings] = building_max[valid_buildings]
    building_heights = np.where(valid_buildings, np.maximum(building_roofs - terrain, 0.0), 0.0).astype(np.float32)
    surface = np.where(valid_buildings, terrain + building_heights, terrain).astype(np.float32)

    inside_aoi = geometry_mask(
        [mapping(aoi_geometry)],
        out_shape=(rows, cols),
        transform=transform,
        invert=True,
    )

    terrain = np.where(inside_aoi, terrain, -9999.0).astype(np.float32)
    building_heights = np.where(inside_aoi, building_heights, BUILDING_NODATA).astype(np.float32)
    surface = np.where(inside_aoi, surface, -9999.0).astype(np.float32)

    output_root = Path(output_dir)
    resolution_label = _resolution_label(resolution)
    terrain_path = _write_raster(
        path=output_root / f"terrain_{resolution_label}.tif",
        array=terrain,
        transform=transform,
        crs=target_crs,
        nodata=-9999.0,
    )
    building_heights_path = _write_raster(
        path=output_root / f"buildings_height_{resolution_label}.tif",
        array=building_heights,
        transform=transform,
        crs=target_crs,
        nodata=BUILDING_NODATA,
    )
    surface_model_path = _write_raster(
        path=output_root / f"terrain_buildings_{resolution_label}.tif",
        array=surface,
        transform=transform,
        crs=target_crs,
        nodata=-9999.0,
    )

    return LidarSurfaceOutputs(
        terrain_path=terrain_path,
        building_heights_path=building_heights_path,
        surface_model_path=surface_model_path,
        lidar_product_code=lidar_product_code,
        resolution_m=float(resolution),
    )
