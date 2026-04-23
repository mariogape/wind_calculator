from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pyproj import CRS, Transformer
from pyogrio import read_dataframe, read_info
from shapely.geometry import box, mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as shapely_transform
from shapely.ops import unary_union


@dataclass(frozen=True)
class AOI:
    path: Path
    source_crs: CRS
    geometry: BaseGeometry
    geometry_4326: BaseGeometry
    centroid_lon: float
    centroid_lat: float

    @property
    def bounds_4326(self) -> tuple[float, float, float, float]:
        return tuple(self.geometry_4326.bounds)

    def to_feature_collection(self) -> str:
        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": mapping(self.geometry_4326),
                    "properties": {},
                }
            ],
        }
        return json.dumps(feature_collection, ensure_ascii=True)

    def to_bounds_feature_collection(self) -> str:
        bounds_geometry = box(*self.bounds_4326)
        feature_collection = {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": mapping(bounds_geometry),
                    "properties": {},
                }
            ],
        }
        return json.dumps(feature_collection, ensure_ascii=True)


def _repair_geometry(geometry: BaseGeometry) -> BaseGeometry:
    if geometry.is_valid:
        return geometry
    repaired = geometry.buffer(0)
    if repaired.is_empty:
        raise ValueError("La geometria del AOI es invalida y no se ha podido reparar.")
    return repaired


def transform_geometry(
    geometry: BaseGeometry,
    source_crs: CRS | int | str,
    target_crs: CRS | int | str,
) -> BaseGeometry:
    source = CRS.from_user_input(source_crs)
    target = CRS.from_user_input(target_crs)
    transformer = Transformer.from_crs(source, target, always_xy=True)
    return shapely_transform(transformer.transform, geometry)


def read_aoi(path: str | Path) -> AOI:
    aoi_path = Path(path)
    if not aoi_path.exists():
        raise FileNotFoundError(f"No existe el AOI: {aoi_path}")

    info = read_info(aoi_path)
    source_crs_raw = info.get("crs")
    if not source_crs_raw:
        raise ValueError(
            "El AOI no tiene CRS definido. Define el CRS en el fichero antes de ejecutar el pipeline."
        )

    source_crs = CRS.from_user_input(source_crs_raw)
    dataframe = read_dataframe(aoi_path)
    geometries = [geom for geom in dataframe.geometry if geom is not None and not geom.is_empty]
    if not geometries:
        raise ValueError("El AOI no contiene geometria utilizable.")

    merged = _repair_geometry(unary_union(geometries))
    geometry_4326 = _repair_geometry(transform_geometry(merged, source_crs, 4326))
    centroid = geometry_4326.centroid

    return AOI(
        path=aoi_path,
        source_crs=source_crs,
        geometry=merged,
        geometry_4326=geometry_4326,
        centroid_lon=float(centroid.x),
        centroid_lat=float(centroid.y),
    )
