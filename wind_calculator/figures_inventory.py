"""EDA figures for the tree inventory × wind exposure cross-analysis."""

from __future__ import annotations

from pathlib import Path

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyArrowPatch, Patch
from rasterio.windows import Window, from_bounds

from .figures import BRAND, EXPOSURE_CMAP
from .inventory import (
    EXPOSURE_BAND_COLORS,
    EXPOSURE_BAND_LABELS,
    EXPOSURE_BANDS,
    HEIGHT_LABEL,
    HEIGHT_ORDER,
)


_TEXT_OUTLINE = [path_effects.withStroke(linewidth=2.5, foreground="black", alpha=0.85)]


def _style_axes(ax) -> None:
    ax.tick_params(colors=BRAND["txt"], labelsize=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("bottom", "left"):
        ax.spines[side].set_color(BRAND["g300"])
        ax.spines[side].set_linewidth(0.8)
    ax.grid(axis="y", color=BRAND["g200"], linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)


def f1_histogram(
    *,
    exposure_values: np.ndarray,
    output_path: str | Path,
) -> Path:
    values = exposure_values[~np.isnan(exposure_values)]
    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=160)

    for label, lo, hi, color in EXPOSURE_BANDS:
        ax.axvspan(lo, min(hi, 100), color=color, alpha=0.10, zorder=0)

    ax.hist(values, bins=50, range=(0, 100), color=BRAND["forest"], edgecolor="white", linewidth=0.6, zorder=2)
    p25, p50, p75 = np.percentile(values, [25, 50, 75])
    for p, label in zip((p25, p50, p75), ("P25", "Mediana", "P75")):
        ax.axvline(p, color=BRAND["dark"], linewidth=1.2, linestyle="--", zorder=3)
        ax.text(p, ax.get_ylim()[1] * 0.95, f"{label}\n{p:.1f}",
                ha="center", va="top", fontsize=9, color=BRAND["dark"], fontweight="600")

    ax.set_xlim(0, 100)
    ax.set_xlabel("Índice de exposición al viento (0 abrigado — 100 expuesto)", fontsize=11, color=BRAND["txt"])
    ax.set_ylabel("Número de árboles", fontsize=11, color=BRAND["txt"])
    _style_axes(ax)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f2_band_bars(*, df: pd.DataFrame, output_path: str | Path) -> Path:
    counts = df["exposure_class"].value_counts().reindex(EXPOSURE_BAND_LABELS, fill_value=0)
    total = int(counts.sum()) or 1
    pct = counts / total * 100

    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=160)
    colors = [EXPOSURE_BAND_COLORS[lbl] for lbl in EXPOSURE_BAND_LABELS]
    y = np.arange(len(EXPOSURE_BAND_LABELS))
    ax.barh(y, counts.values, color=colors, edgecolor="white", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(EXPOSURE_BAND_LABELS, fontsize=11)
    ax.invert_yaxis()
    for i, (n, p) in enumerate(zip(counts.values, pct.values)):
        ax.text(n + counts.max() * 0.01, i, f"{int(n):,} · {p:.1f} %".replace(",", "."),
                va="center", ha="left", fontsize=10, color=BRAND["dark"], fontweight="600")
    ax.set_xlabel("Número de árboles", fontsize=11, color=BRAND["txt"])
    ax.set_xlim(0, counts.max() * 1.18)
    _style_axes(ax)
    ax.grid(axis="x", color=BRAND["g200"], linewidth=0.6, alpha=0.8)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f3_top_species_stack(
    *,
    df: pd.DataFrame,
    output_path: str | Path,
    top_n: int = 15,
) -> Path:
    valid = df.dropna(subset=["exposure_class", "descripcion"]).copy()
    top = valid["descripcion"].value_counts().head(top_n).index[::-1]
    sub = valid[valid["descripcion"].isin(top)]
    table = pd.crosstab(sub["descripcion"], sub["exposure_class"])
    table = table.reindex(index=top, columns=EXPOSURE_BAND_LABELS, fill_value=0)

    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=160)
    y = np.arange(len(table.index))
    left = np.zeros(len(table.index))
    for label in EXPOSURE_BAND_LABELS:
        vals = table[label].values
        ax.barh(y, vals, left=left, color=EXPOSURE_BAND_COLORS[label],
                edgecolor="white", linewidth=0.4, label=label)
        left = left + vals

    ax.set_yticks(y)
    ax.set_yticklabels([f"{name.title()}" for name in table.index], fontsize=10)
    ax.set_xlabel("Número de árboles", fontsize=11, color=BRAND["txt"])
    _style_axes(ax)
    ax.grid(axis="x", color=BRAND["g200"], linewidth=0.6, alpha=0.8)
    ax.legend(title="Clase de exposición", loc="lower right", fontsize=9, title_fontsize=10,
              frameon=True, framealpha=1.0, edgecolor=BRAND["g200"])
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f4_top_species_box(
    *,
    df: pd.DataFrame,
    output_path: str | Path,
    top_n: int = 12,
    min_count: int = 200,
) -> Path:
    valid = df.dropna(subset=["exposure", "descripcion"]).copy()
    counts = valid["descripcion"].value_counts()
    candidates = counts[counts >= min_count].head(top_n).index.tolist()
    medians = valid[valid["descripcion"].isin(candidates)].groupby("descripcion")["exposure"].median()
    order = medians.sort_values(ascending=True).index.tolist()
    data = [valid.loc[valid["descripcion"] == sp, "exposure"].values for sp in order]

    fig, ax = plt.subplots(figsize=(11, 6.2), dpi=160)
    bp = ax.boxplot(
        data,
        vert=False,
        widths=0.6,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color=BRAND["dark"], linewidth=1.6),
        whiskerprops=dict(color=BRAND["g500"], linewidth=1.0),
        capprops=dict(color=BRAND["g500"], linewidth=1.0),
        boxprops=dict(facecolor=BRAND["forest"], alpha=0.30, edgecolor=BRAND["forest"], linewidth=1.0),
    )
    ax.set_yticks(range(1, len(order) + 1))
    ax.set_yticklabels([s.title() for s in order], fontsize=10)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Índice de exposición", fontsize=11, color=BRAND["txt"])
    _style_axes(ax)
    ax.grid(axis="x", color=BRAND["g200"], linewidth=0.6, alpha=0.8)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f5_alineacion_vs_parque(
    *,
    df: pd.DataFrame,
    output_path: str | Path,
) -> Path:
    valid = df.dropna(subset=["exposure", "tipo_ubicacion"])
    aline = valid.loc[valid["tipo_ubicacion"] == "ARBOLADO DE ALINEACION", "exposure"].values
    parque = valid.loc[valid["tipo_ubicacion"] == "PARQUES O ZONAS VERDES", "exposure"].values

    fig, ax = plt.subplots(figsize=(11, 5.2), dpi=160)
    ax.hist(aline, bins=50, range=(0, 100), color=BRAND["dark"], alpha=0.55,
            label=f"Alineación (n={len(aline):,})".replace(",", "."), edgecolor="white", linewidth=0.4)
    ax.hist(parque, bins=50, range=(0, 100), color=BRAND["lime"], alpha=0.55,
            label=f"Parque / zona verde (n={len(parque):,})".replace(",", "."), edgecolor="white", linewidth=0.4)
    ax.axvline(np.mean(aline), color=BRAND["dark"], linewidth=1.4, linestyle="--")
    ax.axvline(np.mean(parque), color=BRAND["forest"], linewidth=1.4, linestyle="--")
    ax.text(np.mean(aline), ax.get_ylim()[1] * 0.95, f"x̄ {np.mean(aline):.1f}",
            ha="center", va="top", fontsize=9, color=BRAND["dark"], fontweight="600")
    ax.text(np.mean(parque), ax.get_ylim()[1] * 0.86, f"x̄ {np.mean(parque):.1f}",
            ha="center", va="top", fontsize=9, color=BRAND["forest"], fontweight="600")
    ax.set_xlim(0, 100)
    ax.set_xlabel("Índice de exposición", fontsize=11, color=BRAND["txt"])
    ax.set_ylabel("Número de árboles", fontsize=11, color=BRAND["txt"])
    ax.legend(loc="upper right", fontsize=10, frameon=True, framealpha=1.0, edgecolor=BRAND["g200"])
    _style_axes(ax)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f6_height_box(*, df: pd.DataFrame, output_path: str | Path) -> Path:
    valid = df.dropna(subset=["exposure", "altura_clase"])
    data = []
    labels = []
    for cls in HEIGHT_ORDER:
        v = valid.loc[valid["altura_clase"] == cls, "exposure"].values
        if len(v) > 0:
            data.append(v)
            labels.append(f"{HEIGHT_LABEL[cls]}\nn = {len(v):,}".replace(",", "."))

    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=160)
    bp = ax.boxplot(
        data,
        widths=0.55,
        patch_artist=True,
        showfliers=False,
        medianprops=dict(color=BRAND["dark"], linewidth=1.6),
        whiskerprops=dict(color=BRAND["g500"], linewidth=1.0),
        capprops=dict(color=BRAND["g500"], linewidth=1.0),
    )
    height_colors = ["#a6cce3", "#5e9bc4", "#f4a363", "#b73224"]
    for patch, c in zip(bp["boxes"], height_colors):
        patch.set_facecolor(c)
        patch.set_alpha(0.65)
        patch.set_edgecolor(c)
    ax.set_xticks(range(1, len(labels) + 1))
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Índice de exposición", fontsize=11, color=BRAND["txt"])
    _style_axes(ax)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def f7_top_zones(*, zone_table: pd.DataFrame, output_path: str | Path) -> Path:
    sub = zone_table.copy()
    sub = sub.iloc[::-1].reset_index(drop=True)

    fig, ax = plt.subplots(figsize=(11, 6.0), dpi=160)
    y = np.arange(len(sub))
    ax.barh(y, sub["pct_alto"].values, color=BRAND["forest"],
            edgecolor="white", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(sub["zona"].str.title().tolist(), fontsize=10)
    for i, row in sub.iterrows():
        ax.text(row["pct_alto"] + 1.5, i,
                f"{row['pct_alto']:.0f} % · {int(row['n']):,} arb.".replace(",", "."),
                va="center", ha="left", fontsize=9, color=BRAND["dark"], fontweight="600")
    ax.set_xlim(0, max(100, sub["pct_alto"].max() * 1.25))
    ax.set_xlabel("% de árboles en exposición Alta o Muy alta (≥ 60)", fontsize=11, color=BRAND["txt"])
    _style_axes(ax)
    ax.grid(axis="x", color=BRAND["g200"], linewidth=0.6, alpha=0.8)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def _read_window(path: Path, bbox: tuple[float, float, float, float] | None):
    with rasterio.open(path) as src:
        if bbox is None:
            data = src.read(1)
            transform = src.transform
        else:
            window = from_bounds(*bbox, transform=src.transform).round_offsets().round_lengths()
            window = window.intersection(Window(0, 0, src.width, src.height))
            data = src.read(1, window=window)
            transform = src.window_transform(window)
        nodata = src.nodata
    return data, transform, nodata


def _draw_scale_bar_and_north(ax) -> None:
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    span_x = xlim[1] - xlim[0]
    span_y = ylim[1] - ylim[0]

    target = span_x * 0.18
    candidates = [200, 500, 1000, 2000, 5000]
    length = min(candidates, key=lambda c: abs(c - target))
    label = f"{length // 1000} km" if length >= 1000 else f"{length} m"

    x0 = xlim[0] + span_x * 0.04
    y0 = ylim[0] + span_y * 0.04
    bar_h = span_y * 0.006
    ax.add_patch(plt.Rectangle((x0, y0), length, bar_h, color="white", ec="black", lw=0.8, zorder=10))
    txt = ax.text(x0 + length / 2, y0 + bar_h * 2.5, label,
                  ha="center", va="bottom", fontsize=10, color="white", fontweight="600", zorder=10)
    txt.set_path_effects(_TEXT_OUTLINE)

    cx = xlim[1] - span_x * 0.06
    cy = ylim[1] - span_y * 0.10
    arrow_len = span_y * 0.06
    arrow = FancyArrowPatch(
        (cx, cy - arrow_len / 2), (cx, cy + arrow_len / 2),
        arrowstyle="-|>", mutation_scale=18, color="white", linewidth=2.5, zorder=10,
    )
    arrow.set_path_effects(_TEXT_OUTLINE)
    ax.add_patch(arrow)
    n_txt = ax.text(cx, cy + arrow_len / 2 + span_y * 0.012, "N",
                    ha="center", va="bottom", fontsize=12, color="white", fontweight="700", zorder=10)
    n_txt.set_path_effects(_TEXT_OUTLINE)


def f8_inventory_map(
    *,
    df: pd.DataFrame,
    exposure_tif: str | Path,
    terrain_tif: str | Path,
    output_path: str | Path,
    figsize: tuple[float, float] = (12, 12),
    dpi: int = 200,
) -> Path:
    expo, transform, expo_nodata = _read_window(Path(exposure_tif), None)
    terr, _, terr_nodata = _read_window(Path(terrain_tif), None)

    expo_valid = np.isfinite(expo)
    if expo_nodata is not None:
        expo_valid &= expo != expo_nodata
    terr_valid = np.isfinite(terr)
    if terr_nodata is not None:
        terr_valid &= terr != terr_nodata
    terr_filled = np.where(terr_valid, terr, np.nanmedian(terr[terr_valid]) if terr_valid.any() else 0)

    light = LightSource(azdeg=315, altdeg=45)
    hillshade = light.hillshade(terr_filled, vert_exag=2.5, dx=1.0, dy=1.0)
    hillshade_visible = np.where(expo_valid, hillshade, np.nan)

    extent = (
        transform.c,
        transform.c + transform.a * expo.shape[1],
        transform.f + transform.e * expo.shape[0],
        transform.f,
    )

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_facecolor("black")
    ax.imshow(hillshade_visible, cmap="gray", extent=extent, origin="upper", interpolation="bilinear", alpha=0.55)
    expo_masked = np.where(expo_valid, expo, np.nan)
    ax.imshow(expo_masked, cmap=EXPOSURE_CMAP, vmin=0, vmax=100,
              extent=extent, origin="upper", alpha=0.30, interpolation="nearest")

    valid = df.dropna(subset=["exposure"])
    point_colors = [EXPOSURE_BAND_COLORS[c] for c in valid["exposure_class"].astype(str)]
    ax.scatter(valid["x"], valid["y"], c=point_colors, s=4.5, alpha=0.85,
               linewidths=0.0, zorder=3)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_color(BRAND["g300"])
        ax.spines[side].set_linewidth(0.8)

    handles = [Patch(facecolor=EXPOSURE_BAND_COLORS[lbl], edgecolor="black", linewidth=0.4, label=lbl)
               for lbl in EXPOSURE_BAND_LABELS]
    leg = ax.legend(handles=handles, title="Exposición del árbol", loc="lower right",
                    fontsize=9, title_fontsize=10, frameon=True, framealpha=0.95,
                    edgecolor=BRAND["g200"])
    leg.get_title().set_color(BRAND["dark"])

    _draw_scale_bar_and_north(ax)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=dpi)
    plt.close(fig)
    return Path(output_path)


def f9_priority_map(
    *,
    df_priority: pd.DataFrame,
    exposure_tif: str | Path,
    terrain_tif: str | Path,
    output_path: str | Path,
    figsize: tuple[float, float] = (12, 12),
    dpi: int = 200,
) -> Path:
    expo, transform, expo_nodata = _read_window(Path(exposure_tif), None)
    terr, _, terr_nodata = _read_window(Path(terrain_tif), None)

    expo_valid = np.isfinite(expo)
    if expo_nodata is not None:
        expo_valid &= expo != expo_nodata
    terr_valid = np.isfinite(terr)
    if terr_nodata is not None:
        terr_valid &= terr != terr_nodata
    terr_filled = np.where(terr_valid, terr, np.nanmedian(terr[terr_valid]) if terr_valid.any() else 0)

    light = LightSource(azdeg=315, altdeg=45)
    hillshade = light.hillshade(terr_filled, vert_exag=2.5, dx=1.0, dy=1.0)
    hillshade_visible = np.where(expo_valid, hillshade, np.nan)

    extent = (
        transform.c,
        transform.c + transform.a * expo.shape[1],
        transform.f + transform.e * expo.shape[0],
        transform.f,
    )

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_facecolor("black")
    ax.imshow(hillshade_visible, cmap="gray", extent=extent, origin="upper",
              interpolation="bilinear", alpha=0.45)

    ax.scatter(df_priority["x"], df_priority["y"],
               c="#b2182b", s=18, alpha=0.92,
               edgecolors="white", linewidths=0.4, zorder=3)

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_color(BRAND["g300"])
        ax.spines[side].set_linewidth(0.8)

    txt = ax.text(0.02, 0.98,
                  f"{len(df_priority):,} árboles prioritarios".replace(",", "."),
                  transform=ax.transAxes, ha="left", va="top",
                  fontsize=14, color="white", fontweight="700")
    txt.set_path_effects(_TEXT_OUTLINE)
    sub = ax.text(0.02, 0.945,
                  "Altura ≥ Grande (≥ 9 m) y exposición ≥ 70",
                  transform=ax.transAxes, ha="left", va="top",
                  fontsize=10, color="white", fontweight="500")
    sub.set_path_effects(_TEXT_OUTLINE)

    _draw_scale_bar_and_north(ax)
    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=dpi)
    plt.close(fig)
    return Path(output_path)
