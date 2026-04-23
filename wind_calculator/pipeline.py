from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import rasterio
from requests import RequestException
from pyproj import CRS
from rasterio.io import MemoryFile
from rasterio.mask import mask
from rasterio.merge import merge
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT
from rasterio.warp import reproject

from .aoi import read_aoi, transform_geometry
from .cnig import CnigClient
from .saga import from_direction_to_saga, resolve_saga_cmd, run_wind_effect
from .wind import WindClimatology, build_wind_climatology


def _choose_target_crs(
    dataset_paths: list[Path],
    *,
    expected_resolution: float | None = None,
    resolution_tolerance: float = 0.1,
) -> tuple[CRS, float]:
    crs_counts: dict[str, int] = {}
    projected_resolutions: set[tuple[float, float]] = set()
    projected_crs: dict[str, CRS] = {}

    for path in dataset_paths:
        with rasterio.open(path) as src:
            if src.crs is None:
                raise ValueError(f"El raster {path.name} no tiene CRS.")
            crs_key = src.crs.to_string()
            crs_counts[crs_key] = crs_counts.get(crs_key, 0) + 1
            crs_obj = CRS.from_user_input(src.crs)
            if crs_obj.is_projected:
                projected_crs[crs_key] = crs_obj
                projected_resolutions.add((round(abs(src.res[0]), 8), round(abs(src.res[1]), 8)))

    if not projected_crs:
        raise ValueError("Las teselas descargadas no estan en un CRS proyectado.")
    if len(projected_resolutions) > 1:
        raise ValueError(
            "Las teselas proyectadas no comparten la misma resolucion. Este caso aun no esta soportado."
        )

    crs_key = max(
        projected_crs,
        key=lambda key: (crs_counts.get(key, 0), -len(key)),
    )
    crs = projected_crs[crs_key]
    xres, yres = projected_resolutions.pop() if projected_resolutions else (2.0, 2.0)
    if expected_resolution is not None and (
        abs(xres - expected_resolution) > resolution_tolerance
        or abs(yres - expected_resolution) > resolution_tolerance
    ):
        raise ValueError(
            f"Se esperaba una resolucion de {expected_resolution} m y se ha recibido {xres} x {yres} m."
        )
    return crs, xres


def _open_merge_sources(
    dataset_paths: list[Path],
    target_crs: CRS,
    resolution: float,
    resampling: Resampling,
) -> tuple[list[rasterio.DatasetReader], list[WarpedVRT], list[rasterio.io.DatasetReader]]:
    sources: list[rasterio.io.DatasetReader] = []
    vrts: list[WarpedVRT] = []
    merge_sources: list[rasterio.DatasetReader] = []

    for path in dataset_paths:
        src = rasterio.open(path)
        sources.append(src)
        if CRS.from_user_input(src.crs) == target_crs:
            merge_sources.append(src)
            continue

        vrt = WarpedVRT(
            src,
            crs=target_crs,
            resampling=resampling,
            nodata=src.nodata,
        )
        vrts.append(vrt)
        merge_sources.append(vrt)

    return merge_sources, vrts, sources


def build_clipped_mosaic_from_tiles(
    *,
    tile_paths: list[Path],
    aoi_geometry_4326,
    output_path: str | Path,
    expected_resolution: float | None = None,
    warp_resampling: Resampling = Resampling.bilinear,
) -> Path:
    if not tile_paths:
        raise ValueError("No hay teselas para construir el raster solicitado.")

    source_crs, resolution = _choose_target_crs(tile_paths, expected_resolution=expected_resolution)
    aoi_geometry_source = transform_geometry(aoi_geometry_4326, 4326, source_crs)

    datasets, vrts, sources = _open_merge_sources(tile_paths, source_crs, resolution, warp_resampling)
    try:
        mosaic, transform = merge(datasets, res=resolution)
        profile = datasets[0].profile.copy()
        nodata = profile.get("nodata")
        if nodata is None:
            nodata = -9999.0

        profile.update(
            height=mosaic.shape[1],
            width=mosaic.shape[2],
            transform=transform,
            nodata=nodata,
            compress="deflate",
            tiled=True,
            predictor=2,
        )

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with MemoryFile() as memory_file:
            with memory_file.open(**profile) as dataset:
                dataset.write(mosaic)

            with memory_file.open() as dataset:
                clipped, clipped_transform = mask(
                    dataset,
                    [aoi_geometry_source],
                    crop=True,
                    nodata=nodata,
                )

        profile.update(
            height=clipped.shape[1],
            width=clipped.shape[2],
            transform=clipped_transform,
        )

        with rasterio.open(output, "w", **profile) as dst:
            dst.write(clipped)

        return output
    finally:
        for dataset in vrts:
            dataset.close()
        for dataset in sources:
            dataset.close()


def _reproject_to_template(
    *,
    source_path: Path,
    template_path: Path,
    output_path: Path,
    resampling: Resampling,
    dst_nodata: float,
) -> Path:
    with rasterio.open(template_path) as template_src:
        template_profile = template_src.profile.copy()
        destination = np.full((template_src.height, template_src.width), dst_nodata, dtype=np.float32)

        with rasterio.open(source_path) as source_src:
            reproject(
                source=rasterio.band(source_src, 1),
                destination=destination,
                src_transform=source_src.transform,
                src_crs=source_src.crs,
                src_nodata=source_src.nodata,
                dst_transform=template_src.transform,
                dst_crs=template_src.crs,
                dst_nodata=dst_nodata,
                resampling=resampling,
            )

    template_profile.pop("blockxsize", None)
    template_profile.pop("blockysize", None)
    template_profile.pop("predictor", None)
    template_profile.update(
        dtype="float32",
        count=1,
        nodata=dst_nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(output_path, "w", **template_profile) as dst:
        dst.write(destination.astype(np.float32), 1)
    return output_path


def build_terrain_buildings_surface(
    *,
    terrain_tile_paths: list[Path],
    building_tile_paths: list[Path],
    aoi_geometry_4326,
    output_dir: str | Path,
) -> dict[str, Path]:
    output_root = Path(output_dir)
    terrain_path = build_clipped_mosaic_from_tiles(
        tile_paths=terrain_tile_paths,
        aoi_geometry_4326=aoi_geometry_4326,
        output_path=output_root / "terrain_2m.tif",
        expected_resolution=2.0,
        warp_resampling=Resampling.bilinear,
    )
    building_native_path = build_clipped_mosaic_from_tiles(
        tile_paths=building_tile_paths,
        aoi_geometry_4326=aoi_geometry_4326,
        output_path=output_root / "buildings_height_2p5m.tif",
        expected_resolution=2.5,
        warp_resampling=Resampling.nearest,
    )
    building_aligned_path = _reproject_to_template(
        source_path=building_native_path,
        template_path=terrain_path,
        output_path=output_root / "buildings_height_2m.tif",
        resampling=Resampling.nearest,
        dst_nodata=0.0,
    )

    with rasterio.open(terrain_path) as terrain_src:
        terrain = terrain_src.read(1).astype(np.float32)
        terrain_nodata = terrain_src.nodata
        profile = terrain_src.profile.copy()

    with rasterio.open(building_aligned_path) as building_src:
        buildings = building_src.read(1).astype(np.float32)

    terrain_valid = np.isfinite(terrain)
    if terrain_nodata is not None:
        terrain_valid &= terrain != terrain_nodata

    buildings = np.where(np.isfinite(buildings), buildings, 0.0)
    buildings = np.maximum(buildings, 0.0)

    surface = np.full(terrain.shape, -9999.0, dtype=np.float32)
    surface[terrain_valid] = terrain[terrain_valid] + buildings[terrain_valid]

    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    profile.pop("predictor", None)
    profile.update(
        dtype="float32",
        count=1,
        nodata=-9999.0,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    surface_path = output_root / "terrain_buildings_2m.tif"
    with rasterio.open(surface_path, "w", **profile) as dst:
        dst.write(surface, 1)

    return {
        "terrain": terrain_path,
        "buildings_height_native": building_native_path,
        "buildings_height": building_aligned_path,
        "surface_model": surface_path,
    }


def _normalize_raster(array: np.ndarray, valid_mask: np.ndarray) -> np.ndarray:
    out = np.full(array.shape, np.nan, dtype=np.float32)
    if not np.any(valid_mask):
        return out

    values = array[valid_mask]
    lower, upper = np.nanpercentile(values, [2, 98])
    if not np.isfinite(lower) or not np.isfinite(upper) or upper <= lower:
        out[valid_mask] = 0.5
        return out

    out[valid_mask] = np.clip((values - lower) / (upper - lower), 0.0, 1.0).astype(np.float32)
    return out


def _write_final_raster(
    *,
    template_path: Path,
    data: np.ndarray,
    output_path: Path,
) -> Path:
    with rasterio.open(template_path) as src:
        profile = src.profile.copy()

    nodata = -9999.0
    output_path.parent.mkdir(parents=True, exist_ok=True)
    profile.pop("blockxsize", None)
    profile.pop("blockysize", None)
    profile.pop("tiled", None)
    profile.update(
        dtype="float32",
        count=1,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    )

    to_write = np.where(np.isfinite(data), data, nodata).astype(np.float32)
    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(to_write, 1)
    return output_path


def _build_exposure_map(
    *,
    saga_cmd: str,
    dem_path: Path,
    climatology: WindClimatology,
    temp_dir: Path,
    output_path: Path,
    maxdist_km: float,
    accel: float,
) -> Path:
    weighted_sum: np.ndarray | None = None
    global_valid_mask: np.ndarray | None = None
    template_tif: Path | None = None

    for sector in climatology.sectors:
        if sector.weight <= 0:
            continue

        direction_to = from_direction_to_saga(sector.from_degrees)
        tif_path = run_wind_effect(
            saga_cmd=saga_cmd,
            dem_path=dem_path,
            out_base=temp_dir / f"wind_effect_from_{sector.from_degrees:03d}",
            direction_to_deg=direction_to,
            maxdist_km=maxdist_km,
            accel=accel,
        )

        if template_tif is None:
            template_tif = tif_path

        with rasterio.open(tif_path) as src:
            array = src.read(1).astype(np.float32)
            nodata = src.nodata
            valid_mask = np.isfinite(array)
            if nodata is not None:
                valid_mask &= array != nodata
            normalized = _normalize_raster(array, valid_mask)

        if weighted_sum is None:
            weighted_sum = np.zeros_like(normalized, dtype=np.float32)
            global_valid_mask = valid_mask.copy()
        else:
            global_valid_mask &= valid_mask

        weighted_sum += np.where(valid_mask, normalized * sector.weight, 0.0)

    if weighted_sum is None or global_valid_mask is None or template_tif is None:
        raise RuntimeError("No se ha podido calcular ningun raster direccional de exposicion.")

    final = np.full(weighted_sum.shape, np.nan, dtype=np.float32)
    final[global_valid_mask] = weighted_sum[global_valid_mask]
    scaled = _normalize_raster(final, global_valid_mask) * 100.0
    return _write_final_raster(template_path=template_tif, data=scaled, output_path=output_path)


def _search_and_download_cnig_product(
    *,
    client: CnigClient,
    product_code: str,
    aoi,
    target_dir: Path,
) -> list[Path]:
    download_method = getattr(client, f"search_and_download_{product_code.lower()}")
    try:
        return download_method(
            geometry_geojson=aoi.to_feature_collection(),
            target_dir=target_dir,
        )
    except RequestException:
        return download_method(
            geometry_geojson=aoi.to_bounds_feature_collection(),
            target_dir=target_dir,
        )


def run_pipeline(
    *,
    aoi_path: str | Path,
    output_dir: str | Path,
    saga_cmd_path: str | None,
    cache_dir: str | Path | None,
    start_year: int,
    end_year: int,
    maxdist_km: float,
    accel: float,
    wind_weighting: str,
    strong_wind_percentile: float,
    strong_wind_min_mps: float,
    strong_wind_exponent: float,
    keep_temp: bool = False,
) -> dict[str, str]:
    aoi = read_aoi(aoi_path)
    saga_cmd = resolve_saga_cmd(saga_cmd_path)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    cache_path = Path(cache_dir) if cache_dir else output_path / "_cache"
    cache_path.mkdir(parents=True, exist_ok=True)

    cnig_cache = cache_path / "cnig"
    era5_cache = cache_path / "era5land"

    client = CnigClient()
    terrain_tile_paths = _search_and_download_cnig_product(
        client=client,
        product_code="mdt02",
        aoi=aoi,
        target_dir=cnig_cache / "mdt02",
    )
    building_tile_paths = _search_and_download_cnig_product(
        client=client,
        product_code="mdse2",
        aoi=aoi,
        target_dir=cnig_cache / "mdse2",
    )

    surface_outputs = build_terrain_buildings_surface(
        terrain_tile_paths=terrain_tile_paths,
        building_tile_paths=building_tile_paths,
        aoi_geometry_4326=aoi.geometry_4326,
        output_dir=output_path,
    )
    surface_model_path = surface_outputs["surface_model"]

    climatology = build_wind_climatology(
        longitude=aoi.centroid_lon,
        latitude=aoi.centroid_lat,
        start_year=start_year,
        end_year=end_year,
        cache_dir=era5_cache,
        timeseries_csv=output_path / "wind_timeseries.csv",
        summary_json=output_path / "wind_climatology.json",
        weighting_method=wind_weighting,
        strong_wind_percentile=strong_wind_percentile,
        strong_wind_min_mps=strong_wind_min_mps,
        strong_wind_exponent=strong_wind_exponent,
    )

    if keep_temp:
        temp_root = output_path / "_tmp"
        temp_root.mkdir(parents=True, exist_ok=True)
        exposure_path = _build_exposure_map(
            saga_cmd=saga_cmd,
            dem_path=surface_model_path,
            climatology=climatology,
            temp_dir=temp_root,
            output_path=output_path / "wind_exposure_2m.tif",
            maxdist_km=maxdist_km,
            accel=accel,
        )
    else:
        with TemporaryDirectory(prefix="wind_pipeline_", dir=output_path) as temp_dir_name:
            exposure_path = _build_exposure_map(
                saga_cmd=saga_cmd,
                dem_path=surface_model_path,
                climatology=climatology,
                temp_dir=Path(temp_dir_name),
                output_path=output_path / "wind_exposure_2m.tif",
                maxdist_km=maxdist_km,
                accel=accel,
            )

    summary = {
        "aoi": str(Path(aoi_path).resolve()),
        "terrain_model": str(surface_outputs["terrain"].resolve()),
        "building_heights": str(surface_outputs["buildings_height"].resolve()),
        "surface_model": str(surface_model_path.resolve()),
        "wind_timeseries": str((output_path / "wind_timeseries.csv").resolve()),
        "wind_climatology": str((output_path / "wind_climatology.json").resolve()),
        "wind_exposure": str(exposure_path.resolve()),
    }
    (output_path / "pipeline_outputs.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    return summary
