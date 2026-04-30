"""Figure generators for the Cáceres wind exposure report.

All figures save PNG with transparent background where applicable. They are
embedded by ``report.py`` as base64.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LightSource, LinearSegmentedColormap, Normalize
from matplotlib.patches import FancyArrowPatch
from rasterio.windows import Window, from_bounds


_TEXT_OUTLINE = [path_effects.withStroke(linewidth=2.5, foreground="black", alpha=0.85)]


SECTOR_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SECTOR_FROM_DEG = [0, 45, 90, 135, 180, 225, 270, 315]
SPEED_BINS = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, np.inf]
SPEED_LABELS = ["0–1", "1–2", "2–3", "3–4", "4–5", "≥ 5"]

BRAND = {
    "dark": "#1b373f",
    "forest": "#426331",
    "olive": "#879753",
    "lime": "#bcbe76",
    "cream": "#fcf5e3",
    "g100": "#f7f7f5",
    "g200": "#e8e8e4",
    "g300": "#d0d0c8",
    "g500": "#8a8a80",
    "g700": "#4a4a44",
    "txt": "#2c2c28",
}

EXPOSURE_CMAP = LinearSegmentedColormap.from_list(
    "expo_byr",
    ["#2166ac", "#67a9cf", "#d1e5f0", "#f7f7d4", "#fddbc7", "#ef8a62", "#b2182b"],
)


def _polar_setup(ax, radial_max: float | None = None) -> None:
    ax.set_theta_zero_location("N")
    ax.set_theta_direction(-1)
    ax.set_xticks(np.deg2rad(SECTOR_FROM_DEG))
    ax.set_xticklabels(SECTOR_LABELS, fontsize=11, color=BRAND["dark"], fontweight="600")
    ax.tick_params(axis="y", colors=BRAND["g500"], labelsize=8)
    ax.spines["polar"].set_color(BRAND["g200"])
    ax.set_facecolor("white")
    ax.grid(color=BRAND["g200"], linewidth=0.6, alpha=0.7)
    if radial_max is not None:
        ax.set_ylim(0, radial_max)


def make_wind_rose_frequency(
    *,
    timeseries_csv: str | Path,
    output_path: str | Path,
) -> Path:
    speeds: list[float] = []
    sectors_idx: list[int] = []
    label_to_idx = {label: i for i, label in enumerate(SECTOR_LABELS)}

    with open(timeseries_csv, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                speed = float(row["speed_mps"])
            except (TypeError, ValueError):
                continue
            sector = row.get("sector")
            if sector not in label_to_idx:
                continue
            speeds.append(speed)
            sectors_idx.append(label_to_idx[sector])

    speeds_arr = np.asarray(speeds)
    sectors_arr = np.asarray(sectors_idx, dtype=int)
    total = len(speeds_arr)

    counts = np.zeros((len(SPEED_BINS) - 1, len(SECTOR_LABELS)), dtype=np.int64)
    for bi in range(len(SPEED_BINS) - 1):
        lo, hi = SPEED_BINS[bi], SPEED_BINS[bi + 1]
        in_bin = (speeds_arr >= lo) & (speeds_arr < hi) if np.isfinite(hi) else (speeds_arr >= lo)
        for si in range(len(SECTOR_LABELS)):
            counts[bi, si] = int(np.sum(in_bin & (sectors_arr == si)))

    freq_pct = 100.0 * counts / max(total, 1)
    cumulative_pct = freq_pct.sum(axis=0)
    radial_max = float(np.ceil(cumulative_pct.max() / 5.0) * 5.0) if cumulative_pct.max() > 0 else 5.0

    bin_colors = [
        "#3a6ea5",
        "#5e9bc4",
        "#a6cce3",
        "#fce39a",
        "#f4a363",
        "#b73224",
    ]

    angles = np.deg2rad(SECTOR_FROM_DEG)
    width = np.deg2rad(45.0) * 0.92

    fig = plt.figure(figsize=(8, 8), dpi=160)
    ax = fig.add_subplot(111, projection="polar")
    _polar_setup(ax, radial_max=radial_max)

    bottoms = np.zeros(len(SECTOR_LABELS))
    for bi in range(len(SPEED_BINS) - 1):
        ax.bar(
            angles,
            freq_pct[bi],
            width=width,
            bottom=bottoms,
            color=bin_colors[bi],
            edgecolor="white",
            linewidth=0.6,
            label=f"{SPEED_LABELS[bi]} m/s",
            zorder=2,
        )
        bottoms = bottoms + freq_pct[bi]

    ax.set_yticks(np.arange(5, radial_max + 0.001, 5))
    ax.set_yticklabels([f"{int(v)} %" for v in np.arange(5, radial_max + 0.001, 5)])

    legend = ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.32, 1.10),
        title="Velocidad",
        title_fontsize=10,
        fontsize=9,
        frameon=True,
        framealpha=1.0,
        edgecolor=BRAND["g200"],
    )
    legend.get_title().set_color(BRAND["dark"])

    fig.text(
        0.02, 0.02,
        f"ERA5-Land · {total:,} muestras horarias · 8 sectores de 45°",
        fontsize=9,
        color=BRAND["g500"],
    )

    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def make_wind_rose_weights(
    *,
    climatology_json: str | Path,
    output_path: str | Path,
) -> Path:
    with open(climatology_json, "r", encoding="utf-8") as fh:
        clim = json.load(fh)

    weight_by_label = {s["label"]: float(s["weight"]) for s in clim["sectors"]}
    weights = np.array([weight_by_label[lbl] for lbl in SECTOR_LABELS])
    pct = 100.0 * weights

    angles = np.deg2rad(SECTOR_FROM_DEG)
    width = np.deg2rad(45.0) * 0.85
    radial_max = float(np.ceil(pct.max() / 5.0) * 5.0) if pct.max() > 0 else 5.0

    fig = plt.figure(figsize=(8, 8), dpi=160)
    ax = fig.add_subplot(111, projection="polar")
    _polar_setup(ax, radial_max=radial_max)

    ax.bar(
        angles,
        pct,
        width=width,
        color=BRAND["forest"],
        edgecolor="white",
        linewidth=0.7,
        zorder=2,
    )

    for ang, value in zip(angles, pct):
        if value < 0.5:
            continue
        ax.text(
            ang,
            value + radial_max * 0.04,
            f"{value:.1f} %",
            ha="center",
            va="center",
            fontsize=9.5,
            color=BRAND["dark"],
            fontweight="600",
        )

    ax.set_yticks(np.arange(5, radial_max + 0.001, 5))
    ax.set_yticklabels([f"{int(v)} %" for v in np.arange(5, radial_max + 0.001, 5)])

    threshold = clim.get("strong_wind_threshold_mps", 0.0)
    fig.text(
        0.02, 0.02,
        f"Pesos del modelo · viento fuerte ≥ {threshold:.1f} m/s · exponente 3",
        fontsize=9,
        color=BRAND["g500"],
    )

    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=160)
    plt.close(fig)
    return Path(output_path)


def _read_window(
    path: Path,
    bbox: tuple[float, float, float, float] | None,
) -> tuple[np.ndarray, rasterio.Affine, float | None]:
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


def _draw_scale_bar(ax, length_m: float, label: str, *, position: str = "lower left") -> None:
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    span_x = xlim[1] - xlim[0]
    span_y = ylim[1] - ylim[0]
    margin_x = span_x * 0.04
    margin_y = span_y * 0.04
    if "left" in position:
        x0 = xlim[0] + margin_x
    else:
        x0 = xlim[1] - margin_x - length_m
    if "lower" in position:
        y0 = ylim[0] + margin_y
    else:
        y0 = ylim[1] - margin_y
    bar_h = span_y * 0.006
    bar = plt.Rectangle((x0, y0), length_m, bar_h, color="white", ec="black", lw=0.8, zorder=10)
    ax.add_patch(bar)
    txt = ax.text(x0 + length_m / 2, y0 + bar_h * 2.5, label,
                  ha="center", va="bottom", fontsize=10, color="white", fontweight="600", zorder=10)
    txt.set_path_effects(_TEXT_OUTLINE)


def _draw_north_arrow(ax) -> None:
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    span_x = xlim[1] - xlim[0]
    span_y = ylim[1] - ylim[0]
    cx = xlim[1] - span_x * 0.06
    cy = ylim[1] - span_y * 0.10
    arrow_len = span_y * 0.06
    arrow = FancyArrowPatch(
        (cx, cy - arrow_len / 2),
        (cx, cy + arrow_len / 2),
        arrowstyle="-|>",
        mutation_scale=18,
        color="white",
        linewidth=2.5,
        zorder=10,
    )
    arrow.set_path_effects(_TEXT_OUTLINE)
    ax.add_patch(arrow)
    n_txt = ax.text(cx, cy + arrow_len / 2 + span_y * 0.012, "N",
                    ha="center", va="bottom", fontsize=12, color="white", fontweight="700", zorder=10)
    n_txt.set_path_effects(_TEXT_OUTLINE)


def _suggest_scalebar_length(span_x_m: float) -> tuple[float, str]:
    target = span_x_m * 0.20
    candidates = [100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000]
    length = min(candidates, key=lambda c: abs(c - target))
    if length >= 1000:
        label = f"{length // 1000} km"
    else:
        label = f"{length} m"
    return float(length), label


def make_exposure_render(
    *,
    exposure_tif: str | Path,
    terrain_tif: str | Path,
    output_path: str | Path,
    bbox: tuple[float, float, float, float] | None = None,
    title: str | None = None,
    figsize: tuple[float, float] = (12, 10),
    dpi: int = 180,
) -> Path:
    expo, transform, expo_nodata = _read_window(Path(exposure_tif), bbox)
    terr, _, terr_nodata = _read_window(Path(terrain_tif), bbox)

    expo_valid = np.isfinite(expo)
    if expo_nodata is not None:
        expo_valid &= expo != expo_nodata
    terr_valid = np.isfinite(terr)
    if terr_nodata is not None:
        terr_valid &= terr != terr_nodata

    expo_masked = np.where(expo_valid, expo, np.nan)
    terr_filled = np.where(terr_valid, terr, np.nanmedian(terr[terr_valid]) if terr_valid.any() else 0)

    light = LightSource(azdeg=315, altdeg=45)
    hillshade = light.hillshade(terr_filled, vert_exag=2.5, dx=1.0, dy=1.0)

    extent = (
        transform.c,
        transform.c + transform.a * expo.shape[1],
        transform.f + transform.e * expo.shape[0],
        transform.f,
    )

    fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
    ax.set_facecolor("black")
    hillshade_visible = np.where(expo_valid, hillshade, np.nan)
    ax.imshow(hillshade_visible, cmap="gray", extent=extent, origin="upper", interpolation="bilinear")
    norm = Normalize(vmin=0.0, vmax=100.0)
    expo_im = ax.imshow(
        expo_masked,
        cmap=EXPOSURE_CMAP,
        norm=norm,
        extent=extent,
        origin="upper",
        alpha=0.78,
        interpolation="nearest",
    )

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for side in ("top", "right", "bottom", "left"):
        ax.spines[side].set_color(BRAND["g300"])
        ax.spines[side].set_linewidth(0.8)

    if title:
        ax.set_title(title, fontsize=14, color=BRAND["dark"], fontweight="600", pad=12, loc="left")

    span_x = extent[1] - extent[0]
    bar_len, bar_label = _suggest_scalebar_length(span_x)
    _draw_scale_bar(ax, bar_len, bar_label, position="lower left")
    _draw_north_arrow(ax)

    cbar = fig.colorbar(
        expo_im,
        ax=ax,
        orientation="horizontal",
        fraction=0.045,
        pad=0.04,
        shrink=0.6,
        aspect=35,
    )
    cbar.set_ticks([0, 25, 50, 75, 100])
    cbar.set_ticklabels(["0\nabrigado", "25", "50", "75", "100\nexpuesto"])
    cbar.ax.tick_params(labelsize=9, colors=BRAND["txt"])
    cbar.outline.set_color(BRAND["g300"])

    fig.text(
        0.02, 0.012,
        "Edificios (Catastro INSPIRE) en NoData · Hillshade del MDS LiDAR PNOA · CRS: EPSG:25829",
        fontsize=8,
        color=BRAND["g500"],
    )

    fig.savefig(output_path, bbox_inches="tight", facecolor="white", dpi=dpi)
    plt.close(fig)
    return Path(output_path)
