from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
import requests
from pyogrio import read_dataframe
from pyproj import CRS
from rasterio.features import rasterize as rio_rasterize


_PROVINCE_INDEX_URL = (
    "https://www.catastro.hacienda.gob.es/INSPIRE/buildings/{prov:02d}/ES.SDGC.bu.atom_{prov:02d}.xml"
)
_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class CatastroMunicipality:
    province_code: str
    municipality_code: str
    name: str
    zip_url: str


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def _norm(name: str) -> str:
    return _strip_accents(name).strip().upper()


def _province_code_from_municipality(municipality_code: str) -> int:
    return int(municipality_code[:2])


def list_municipalities(province_code: int, *, timeout: int = 60) -> list[CatastroMunicipality]:
    url = _PROVINCE_INDEX_URL.format(prov=province_code)
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.content)
    municipalities: list[CatastroMunicipality] = []
    for entry in root.findall("atom:entry", _NS):
        title_el = entry.find("atom:title", _NS)
        link_el = entry.find("atom:link", _NS)
        if title_el is None or link_el is None:
            continue
        title = (title_el.text or "").strip()
        href = link_el.attrib.get("href", "")
        if not href.lower().endswith(".zip"):
            continue
        match = re.match(r"^\s*(\d{4,5})\s*[-_ ]\s*([^\n]+?)(?:\s+buildings)?\s*$", title, re.IGNORECASE)
        if not match:
            continue
        muni_code = match.group(1)
        muni_name = match.group(2).strip()
        municipalities.append(
            CatastroMunicipality(
                province_code=f"{province_code:02d}",
                municipality_code=muni_code,
                name=muni_name,
                zip_url=href,
            )
        )
    return municipalities


def find_municipality(
    name: str,
    *,
    province_code: int,
    timeout: int = 60,
) -> CatastroMunicipality:
    target = _norm(name)
    candidates = list_municipalities(province_code, timeout=timeout)
    exact = [m for m in candidates if _norm(m.name) == target]
    if exact:
        return exact[0]
    contains = [m for m in candidates if target in _norm(m.name)]
    if len(contains) == 1:
        return contains[0]
    if len(contains) > 1:
        names = ", ".join(m.name for m in contains)
        raise ValueError(
            f"Mas de un municipio coincide con '{name}' en provincia {province_code:02d}: {names}"
        )
    raise ValueError(
        f"No se ha encontrado el municipio '{name}' en provincia {province_code:02d}."
    )


def download_buildings_zip(
    municipality: CatastroMunicipality,
    *,
    target_dir: str | Path,
    timeout: int = 120,
) -> Path:
    out_dir = Path(target_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"A.ES.SDGC.BU.{municipality.municipality_code}.zip"
    if target.exists() and target.stat().st_size > 0:
        return target
    response = requests.get(municipality.zip_url, stream=True, timeout=timeout)
    response.raise_for_status()
    with target.open("wb") as dst:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                dst.write(chunk)
    return target


def extract_building_gml(zip_path: str | Path, target_dir: str | Path) -> Path:
    zip_path = Path(zip_path)
    out_dir = Path(target_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        building_names = [n for n in names if n.lower().endswith(".building.gml")]
        if not building_names:
            building_names = [n for n in names if n.lower().endswith(".gml") and "building" in n.lower() and "part" not in n.lower()]
        if not building_names:
            raise RuntimeError(f"El zip {zip_path.name} no contiene un fichero building.gml. Ficheros: {names}")
        gml_name = building_names[0]
        out_path = out_dir / Path(gml_name).name
        if not out_path.exists() or out_path.stat().st_size == 0:
            with zf.open(gml_name) as src, out_path.open("wb") as dst:
                dst.write(src.read())
    return out_path


def fetch_buildings_gml(
    municipality_name: str,
    *,
    province_code: int,
    cache_dir: str | Path,
) -> Path:
    cache_dir = Path(cache_dir)
    municipality = find_municipality(municipality_name, province_code=province_code)
    zip_path = download_buildings_zip(municipality, target_dir=cache_dir)
    return extract_building_gml(zip_path, target_dir=cache_dir)


def rasterize_buildings_to_template(
    *,
    gml_path: str | Path,
    template_raster: str | Path,
    output_path: str | Path,
) -> Path:
    template_raster = Path(template_raster)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(template_raster) as tpl:
        target_crs = CRS.from_user_input(tpl.crs)
        transform = tpl.transform
        out_shape = (tpl.height, tpl.width)
        bounds = tpl.bounds
        profile = {
            "driver": "GTiff",
            "height": tpl.height,
            "width": tpl.width,
            "count": 1,
            "dtype": "uint8",
            "crs": tpl.crs,
            "transform": tpl.transform,
            "nodata": 0,
            "compress": "deflate",
            "tiled": True,
            "blockxsize": 256,
            "blockysize": 256,
        }

    bbox = (bounds.left, bounds.bottom, bounds.right, bounds.top)
    gdf = read_dataframe(str(gml_path), bbox=bbox)
    if gdf.crs is None:
        raise RuntimeError(f"El GML {gml_path} no tiene CRS definido.")
    if CRS.from_user_input(gdf.crs) != target_crs:
        gdf = gdf.to_crs(target_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty]
    if gdf.empty:
        mask = np.zeros(out_shape, dtype=np.uint8)
    else:
        shapes = ((geom, 1) for geom in gdf.geometry.values if geom is not None)
        mask = rio_rasterize(
            shapes=shapes,
            out_shape=out_shape,
            transform=transform,
            fill=0,
            dtype="uint8",
            all_touched=False,
        )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(mask, 1)
    return output_path


def apply_mask_to_raster(
    *,
    source_raster: str | Path,
    mask_raster: str | Path,
    output_raster: str | Path,
    nodata_value: float = -9999.0,
) -> Path:
    source_raster = Path(source_raster)
    mask_raster = Path(mask_raster)
    output_raster = Path(output_raster)
    output_raster.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(source_raster) as src, rasterio.open(mask_raster) as msk:
        if src.shape != msk.shape:
            raise ValueError(
                f"Forma incompatible: {source_raster.name} {src.shape} vs {mask_raster.name} {msk.shape}"
            )
        if src.transform != msk.transform:
            raise ValueError("La transformada del raster fuente y la mascara no coincide.")
        data = src.read(1)
        mask_arr = msk.read(1).astype(bool)
        profile = src.profile.copy()

    profile.update(nodata=nodata_value)
    out = data.copy()
    out[mask_arr] = nodata_value

    with rasterio.open(output_raster, "w", **profile) as dst:
        dst.write(out, 1)
    return output_raster
