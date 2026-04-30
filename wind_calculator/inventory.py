"""Tree inventory loader, exposure sampler and EDA helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pyogrio import read_dataframe


_FIELD_MAP = {
    "id": "tree_id",
    "Referencia": "referencia_catastral",
    "Tipo de Ri": "tipo_riego",
    "Género _": "genero",
    "Descripci": "descripcion",
    "Tipo de Ub": "tipo_ubicacion",
    "Baja _": "baja",
    "Referenc_1": "direccion",
    "Nombre Cie": "nombre_cientifico",
    "Variedad _": "variedad",
    "zona": "zona",
    "Ultima_i_1": "perimetro_clase",
    "Ultima_i_2": "estado",
    "Ultima_i_3": "accion",
    "Ultima_i_4": "prioridad",
    "Ultima_i_6": "altura_clase",
    "Ultima_i_7": "fecha_inspeccion",
    "POINT_X": "x",
    "POINT_Y": "y",
}

EXPOSURE_BANDS = [
    ("Muy bajo", 0.0, 20.0, "#2166ac"),
    ("Bajo", 20.0, 40.0, "#67a9cf"),
    ("Medio", 40.0, 60.0, "#f7f7d4"),
    ("Alto", 60.0, 80.0, "#ef8a62"),
    ("Muy alto", 80.0, 100.0001, "#b2182b"),
]
EXPOSURE_BAND_LABELS = [b[0] for b in EXPOSURE_BANDS]
EXPOSURE_BAND_COLORS = {b[0]: b[3] for b in EXPOSURE_BANDS}

HEIGHT_ORDER = [
    "Pequeño (Hasta 5 m.)",
    "Mediano (5 a 9 m.)",
    "Grande (9 a 15 m.)",
    "Ejemplar (Más de 15 m.)",
]
HEIGHT_LABEL = {
    "Pequeño (Hasta 5 m.)": "Pequeño (≤5 m)",
    "Mediano (5 a 9 m.)": "Mediano (5–9 m)",
    "Grande (9 a 15 m.)": "Grande (9–15 m)",
    "Ejemplar (Más de 15 m.)": "Ejemplar (>15 m)",
}

PERIMETER_ORDER = [
    "Hasta 40 cm.",
    "40 a 80 cm.",
    "80 a 120 cm.",
    "Más de 120 cm.",
]
PERIMETER_LABEL = {
    "Hasta 40 cm.": "≤40 cm",
    "40 a 80 cm.": "40–80 cm",
    "80 a 120 cm.": "80–120 cm",
    "Más de 120 cm.": ">120 cm",
}


@dataclass
class CoverageReport:
    total: int
    bajas: int
    activos: int
    fuera_aoi: int
    sobre_edificio: int
    validos: int

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "bajas": self.bajas,
            "activos": self.activos,
            "fuera_aoi": self.fuera_aoi,
            "sobre_edificio": self.sobre_edificio,
            "validos": self.validos,
        }


def load_inventory(shp_path: str | Path) -> pd.DataFrame:
    df = read_dataframe(str(shp_path), encoding="cp1252")
    df = df.rename(columns={k: v for k, v in _FIELD_MAP.items() if k in df.columns})
    if "x" not in df.columns or "y" not in df.columns:
        df["x"] = df.geometry.x
        df["y"] = df.geometry.y
    df["baja_flag"] = df["baja"].astype(str).str.lower().eq("verdadero")
    return df


def sample_exposure_at_points(
    df: pd.DataFrame,
    *,
    exposure_tif: str | Path,
    nodata_value: float = -9999.0,
) -> np.ndarray:
    coords = list(zip(df["x"].to_numpy(), df["y"].to_numpy()))
    with rasterio.open(exposure_tif) as src:
        bounds = src.bounds
        sampled = np.fromiter(
            (val[0] for val in src.sample(coords)),
            dtype=np.float32,
            count=len(coords),
        )
    inside = (
        (df["x"] >= bounds.left)
        & (df["x"] <= bounds.right)
        & (df["y"] >= bounds.bottom)
        & (df["y"] <= bounds.top)
    ).to_numpy()
    out = np.where(inside, sampled, np.nan).astype(np.float32)
    out = np.where(np.isclose(out, nodata_value), np.nan, out)
    return out


def assign_exposure_class(values: np.ndarray) -> pd.Categorical:
    edges = [0.0] + [b[2] for b in EXPOSURE_BANDS]
    labels = EXPOSURE_BAND_LABELS
    cats = pd.cut(values, bins=edges, labels=labels, include_lowest=True, right=False)
    return pd.Categorical(cats, categories=labels, ordered=True)


def build_coverage(df_full: pd.DataFrame, df_sampled: pd.DataFrame, exposure_tif: str | Path) -> CoverageReport:
    total = len(df_full)
    bajas = int(df_full["baja_flag"].sum())
    activos = total - bajas

    coords = list(zip(df_full["x"].to_numpy(), df_full["y"].to_numpy()))
    with rasterio.open(exposure_tif) as src:
        bounds = src.bounds
    inside = (
        (df_full["x"] >= bounds.left)
        & (df_full["x"] <= bounds.right)
        & (df_full["y"] >= bounds.bottom)
        & (df_full["y"] <= bounds.top)
    )
    fuera_aoi = int((~inside & ~df_full["baja_flag"]).sum())

    validos = int((~df_sampled["exposure"].isna() & ~df_sampled["baja_flag"]).sum())
    sobre_edificio = activos - fuera_aoi - validos

    return CoverageReport(
        total=total,
        bajas=bajas,
        activos=activos,
        fuera_aoi=fuera_aoi,
        sobre_edificio=max(sobre_edificio, 0),
        validos=validos,
    )


def species_stats(df: pd.DataFrame, *, top_n: int = 20, min_count: int = 200) -> pd.DataFrame:
    valid = df.dropna(subset=["exposure", "nombre_cientifico"]).copy()

    grouped = valid.groupby("nombre_cientifico")["exposure"]
    stats = grouped.agg(
        n="count",
        media="mean",
        mediana="median",
        std="std",
        p25=lambda s: s.quantile(0.25),
        p75=lambda s: s.quantile(0.75),
    )

    pct_high = (
        valid.assign(_high=valid["exposure"] >= 60)
        .groupby("nombre_cientifico")["_high"]
        .mean()
        * 100.0
    )
    pct_very_high = (
        valid.assign(_vhigh=valid["exposure"] >= 80)
        .groupby("nombre_cientifico")["_vhigh"]
        .mean()
        * 100.0
    )

    desc = valid.groupby("nombre_cientifico")["descripcion"].agg(
        lambda s: s.value_counts().idxmax() if not s.empty else None
    )

    out = stats.assign(pct_alto=pct_high, pct_muy_alto=pct_very_high, descripcion=desc).reset_index()
    out = out[out["n"] >= min_count].sort_values("n", ascending=False).head(top_n)
    return out.reset_index(drop=True)


def categorical_stats(df: pd.DataFrame, *, by: str) -> pd.DataFrame:
    valid = df.dropna(subset=["exposure", by]).copy()
    grp = valid.groupby(by)["exposure"]
    out = grp.agg(n="count", media="mean", mediana="median", p75=lambda s: s.quantile(0.75))
    pct_alto = (
        valid.assign(_h=valid["exposure"] >= 60).groupby(by)["_h"].mean() * 100.0
    )
    pct_muy_alto = (
        valid.assign(_vh=valid["exposure"] >= 80).groupby(by)["_vh"].mean() * 100.0
    )
    return out.assign(pct_alto=pct_alto, pct_muy_alto=pct_muy_alto).reset_index()


def zone_stats(df: pd.DataFrame, *, top_n: int = 15, min_count: int = 50) -> pd.DataFrame:
    valid = df.dropna(subset=["exposure", "zona"]).copy()
    grp = valid.groupby("zona")["exposure"]
    out = grp.agg(n="count", media="mean", mediana="median")
    pct_alto = (
        valid.assign(_h=valid["exposure"] >= 60).groupby("zona")["_h"].mean() * 100.0
    )
    n_muy_alto = (
        valid.assign(_vh=valid["exposure"] >= 80).groupby("zona")["_vh"].sum().astype(int)
    )
    out = out.assign(pct_alto=pct_alto, n_muy_alto=n_muy_alto).reset_index()
    return out[out["n"] >= min_count].sort_values("pct_alto", ascending=False).head(top_n).reset_index(drop=True)


def identify_priority_trees(
    df: pd.DataFrame,
    *,
    height_classes: list[str] | None = None,
    min_exposure: float = 70.0,
) -> pd.DataFrame:
    if height_classes is None:
        height_classes = ["Grande (9 a 15 m.)", "Ejemplar (Más de 15 m.)"]
    mask = (
        df["altura_clase"].isin(height_classes)
        & (df["exposure"] >= min_exposure)
        & ~df["baja_flag"]
    )
    out = df.loc[mask].copy()
    return out.sort_values("exposure", ascending=False).reset_index(drop=True)


def crosstab_height_exposure(df: pd.DataFrame) -> pd.DataFrame:
    valid = df.dropna(subset=["exposure", "altura_clase"]).copy()
    valid["altura_clase"] = pd.Categorical(valid["altura_clase"], categories=HEIGHT_ORDER, ordered=True)
    table = pd.crosstab(valid["altura_clase"], valid["exposure_class"])
    table = table.reindex(index=HEIGHT_ORDER, columns=EXPOSURE_BAND_LABELS, fill_value=0)
    return table


def crosstab_ubication_exposure(df: pd.DataFrame) -> pd.DataFrame:
    valid = df.dropna(subset=["exposure", "tipo_ubicacion"]).copy()
    table = pd.crosstab(valid["tipo_ubicacion"], valid["exposure_class"])
    table = table.reindex(columns=EXPOSURE_BAND_LABELS, fill_value=0)
    return table


def overall_summary(df: pd.DataFrame) -> dict:
    valid = df["exposure"].dropna()
    n = len(valid)
    return {
        "n": int(n),
        "media": float(valid.mean()),
        "mediana": float(valid.median()),
        "std": float(valid.std()),
        "p25": float(valid.quantile(0.25)),
        "p75": float(valid.quantile(0.75)),
        "p95": float(valid.quantile(0.95)),
        "pct_alto": float((valid >= 60).mean() * 100),
        "pct_muy_alto": float((valid >= 80).mean() * 100),
        "pct_bajo": float((valid < 40).mean() * 100),
    }
