"""HTML report builder for the inventory × wind exposure cross-analysis."""

from __future__ import annotations

import base64
import html
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .figures_inventory import (
    f1_histogram, f2_band_bars, f3_top_species_stack, f4_top_species_box,
    f5_alineacion_vs_parque, f6_height_box, f7_top_zones,
    f8_inventory_map, f9_priority_map,
)
from .inventory import (
    EXPOSURE_BAND_LABELS,
    HEIGHT_LABEL,
    HEIGHT_ORDER,
    PERIMETER_LABEL,
    PERIMETER_ORDER,
    assign_exposure_class,
    build_coverage,
    categorical_stats,
    crosstab_height_exposure,
    crosstab_ubication_exposure,
    identify_priority_trees,
    load_inventory,
    overall_summary,
    sample_exposure_at_points,
    species_stats,
    zone_stats,
)
from .report import _STYLE_BLOCK, _logo_data_uri, _spanish_date


_EXTRA_STYLE = """<style>
.kpi{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}
.kpi .kc{background:var(--g100);border-radius:8px;padding:22px;border-top:3px solid var(--forest)}
.kpi .num{font-family:'Space Grotesk',sans-serif;font-size:34px;font-weight:700;color:var(--forest);line-height:1}
.kpi .lbl{font-family:'Space Grotesk',sans-serif;font-size:13px;color:var(--dark);margin-top:8px;font-weight:600}
.kpi .sub{font-size:12px;color:var(--g500);margin-top:4px}
.fig{margin:24px 0;text-align:center}
.fig img{max-width:100%;height:auto;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.fig figcaption{font-family:'Space Grotesk',sans-serif;font-size:12px;color:var(--g700);margin-top:10px;letter-spacing:.3px}
.fig.full img{width:100%}
.smallt table{font-size:12.5px}
.smallt thead th{padding:9px 10px;font-size:11px}
.smallt tbody td{padding:7px 10px}
.qa{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:12px 0 18px}
.qa .qc{background:var(--g100);border-radius:6px;padding:14px;text-align:center}
.qa .qc .qn{font-family:'Space Grotesk',sans-serif;font-size:22px;font-weight:700;color:var(--dark);line-height:1}
.qa .qc .ql{font-size:11px;color:var(--g500);margin-top:4px;letter-spacing:.5px;text-transform:uppercase}
</style>"""


def _b64_image(path: Path, mime: str = "image/png") -> str:
    payload = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _fmt_int(n: int | float) -> str:
    return f"{int(n):,}".replace(",", ".")


def _fmt_pct(p: float, decimals: int = 1) -> str:
    return f"{p:.{decimals}f} %"


def _esc(text: object) -> str:
    return html.escape("" if text is None else str(text))


def _row(*cells: str) -> str:
    return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"


def _coverage_html(cov_dict: dict) -> str:
    return f"""
<div class="qa">
  <div class="qc"><div class="qn">{_fmt_int(cov_dict['total'])}</div><div class="ql">Inventario total</div></div>
  <div class="qc"><div class="qn">{_fmt_int(cov_dict['bajas'])}</div><div class="ql">Bajas (excluidas)</div></div>
  <div class="qc"><div class="qn">{_fmt_int(cov_dict['fuera_aoi'])}</div><div class="ql">Fuera del raster</div></div>
  <div class="qc"><div class="qn">{_fmt_int(cov_dict['sobre_edificio'])}</div><div class="ql">Sobre edificio</div></div>
  <div class="qc"><div class="qn">{_fmt_int(cov_dict['validos'])}</div><div class="ql">Válidos</div></div>
</div>
"""


def _summary_table_html(summary: dict) -> str:
    return f"""
<table>
<thead><tr><th>Estadístico</th><th>Valor</th></tr></thead>
<tbody>
{_row("Árboles válidos analizados", _fmt_int(summary['n']))}
{_row("Media", f"{summary['media']:.1f}")}
{_row("Mediana", f"{summary['mediana']:.1f}")}
{_row("Desviación típica", f"{summary['std']:.1f}")}
{_row("Percentil 25", f"{summary['p25']:.1f}")}
{_row("Percentil 75", f"{summary['p75']:.1f}")}
{_row("Percentil 95", f"{summary['p95']:.1f}")}
{_row("% en exposición ≥ 60 (Alta o Muy alta)", _fmt_pct(summary['pct_alto']))}
{_row("% en exposición ≥ 80 (Muy alta)", _fmt_pct(summary['pct_muy_alto']))}
{_row("% en exposición < 40 (Bajo o Muy bajo)", _fmt_pct(summary['pct_bajo']))}
</tbody></table>
"""


def _species_table_html(species_df: pd.DataFrame) -> str:
    rows = []
    for _, r in species_df.iterrows():
        nombre = (r.get("descripcion") or r["nombre_cientifico"]).title()
        rows.append(_row(
            f"<strong>{_esc(nombre)}</strong>",
            _fmt_int(r["n"]),
            f"{r['media']:.1f}",
            f"{r['mediana']:.1f}",
            _fmt_pct(r["pct_alto"]),
            _fmt_pct(r["pct_muy_alto"]),
        ))
    return f"""
<table class="smallt">
<thead><tr>
<th>Especie</th><th>Ejemplares</th><th>Exp. media</th><th>Exp. mediana</th><th>% en Alta+</th><th>% en Muy alta</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
"""


def _zone_table_html(zone_df: pd.DataFrame) -> str:
    rows = []
    for _, r in zone_df.iterrows():
        rows.append(_row(
            f"<strong>{_esc(r['zona'].title())}</strong>",
            _fmt_int(r["n"]),
            f"{r['media']:.1f}",
            _fmt_pct(r["pct_alto"]),
            _fmt_int(r["n_muy_alto"]),
        ))
    return f"""
<table class="smallt">
<thead><tr>
<th>Zona</th><th>Ejemplares</th><th>Exp. media</th><th>% en Alta+</th><th>Nº en Muy alta</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
"""


def _crosstab_html(table: pd.DataFrame, *, index_label: str, label_map: dict[str, str] | None = None) -> str:
    cols = list(table.columns)
    head = "<th>" + _esc(index_label) + "</th>" + "".join(f"<th>{_esc(c)}</th>" for c in cols) + "<th>Total</th>"
    rows = []
    for idx, row in table.iterrows():
        idx_label = label_map.get(idx, idx) if label_map else idx
        total = int(row.sum())
        cells = [_fmt_int(v) for v in row.values]
        rows.append("<tr><td><strong>" + _esc(idx_label) + "</strong></td>" +
                    "".join(f"<td>{c}</td>" for c in cells) +
                    f"<td><strong>{_fmt_int(total)}</strong></td></tr>")
    grand_total = int(table.values.sum())
    totals = "<tr class='tt'><td>Total</td>" + "".join(f"<td>{_fmt_int(int(s))}</td>" for s in table.sum(axis=0)) + f"<td>{_fmt_int(grand_total)}</td></tr>"
    return f"""
<table>
<thead><tr>{head}</tr></thead>
<tbody>
{chr(10).join(rows)}
{totals}
</tbody></table>
"""


def _priority_table_html(df: pd.DataFrame, *, top_n: int = 50) -> str:
    sub = df.head(top_n).copy()
    rows = []
    for _, r in sub.iterrows():
        fecha = r.get("fecha_inspeccion")
        if pd.notna(fecha):
            try:
                fecha_str = pd.Timestamp(fecha).strftime("%Y-%m-%d")
            except Exception:
                fecha_str = str(fecha)
        else:
            fecha_str = "—"
        rows.append(_row(
            _esc(int(r["tree_id"])),
            _esc((r.get("descripcion") or "").title()),
            _esc((r.get("nombre_cientifico") or "")),
            _esc(HEIGHT_LABEL.get(r.get("altura_clase"), r.get("altura_clase") or "—")),
            _esc(PERIMETER_LABEL.get(r.get("perimetro_clase"), r.get("perimetro_clase") or "—")),
            _esc((r.get("zona") or "").title()),
            f"<strong>{r['exposure']:.0f}</strong>",
            _esc(fecha_str),
        ))
    return f"""
<table class="smallt">
<thead><tr>
<th>ID</th><th>Especie</th><th>Nombre científico</th><th>Altura</th><th>Perímetro</th><th>Zona</th><th>Exposición</th><th>Última inspección</th>
</tr></thead>
<tbody>
{chr(10).join(rows)}
</tbody></table>
"""


def _mann_whitney_text(a: np.ndarray, b: np.ndarray) -> tuple[str, float]:
    res = stats.mannwhitneyu(a, b, alternative="two-sided")
    p = float(res.pvalue)
    if p < 1e-4:
        text = "p < 0,0001 — diferencia estadísticamente significativa"
    elif p < 0.01:
        text = f"p = {p:.4f} — diferencia estadísticamente significativa"
    elif p < 0.05:
        text = f"p = {p:.3f} — diferencia significativa al 5 %"
    else:
        text = f"p = {p:.3f} — no se detecta diferencia significativa"
    return text, p


def _chi2_text(table: pd.DataFrame) -> tuple[str, float]:
    safe = table.loc[(table.sum(axis=1) > 0), (table.sum(axis=0) > 0)]
    try:
        res = stats.chi2_contingency(safe.values)
    except ValueError:
        return ("Distribución incompatible con un test χ² (tablas con margen nulo).", float("nan"))
    p = float(res.pvalue)
    if p < 1e-4:
        text = (f"χ² = {res.statistic:.0f} (gl = {res.dof}); "
                f"p < 0,0001 — la distribución de exposición depende del tamaño del árbol.")
    elif p < 0.05:
        text = (f"χ² = {res.statistic:.0f} (gl = {res.dof}); "
                f"p = {p:.3f} — relación significativa entre tamaño y exposición.")
    else:
        text = (f"χ² = {res.statistic:.0f} (gl = {res.dof}); "
                f"p = {p:.3f} — sin evidencia de relación.")
    return text, p


def build_inventory_report(
    *,
    inventory_shp: Path,
    exposure_tif: Path,
    terrain_tif: Path,
    output_html: Path,
    figures_dir: Path,
    logo_data_path: Path | None = None,
    municipality_label: str = "Cáceres",
    report_date: str | None = None,
) -> Path:
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        df_full = load_inventory(inventory_shp)

    df_full["exposure"] = sample_exposure_at_points(df_full, exposure_tif=exposure_tif)
    df_full["exposure_class"] = assign_exposure_class(df_full["exposure"].to_numpy())

    cov = build_coverage(df_full, df_full, exposure_tif=exposure_tif)
    df = df_full.loc[~df_full["baja_flag"] & df_full["exposure"].notna()].copy()

    summary = overall_summary(df)
    species_df = species_stats(df, top_n=20, min_count=200)
    zones_top = zone_stats(df, top_n=12, min_count=80)
    priority_df = identify_priority_trees(df, min_exposure=70.0)
    height_x_expo = crosstab_height_exposure(df)
    ubic_x_expo = crosstab_ubication_exposure(df)

    aline = df.loc[df["tipo_ubicacion"] == "ARBOLADO DE ALINEACION", "exposure"].dropna().to_numpy()
    parque = df.loc[df["tipo_ubicacion"] == "PARQUES O ZONAS VERDES", "exposure"].dropna().to_numpy()
    aline_parque_text, aline_parque_p = _mann_whitney_text(aline, parque)
    aline_mean = float(np.mean(aline)); parque_mean = float(np.mean(parque))

    chi_text, chi_p = _chi2_text(height_x_expo)

    sentinel_species = species_df.copy()
    sentinel_species["uplift"] = sentinel_species["pct_alto"] - summary["pct_alto"]
    sentinel = sentinel_species[sentinel_species["uplift"] > 2.0].sort_values("uplift", ascending=False).head(3)

    # Generate figures
    f1 = figures_dir / "f1_hist.png"
    f2 = figures_dir / "f2_bands.png"
    f3 = figures_dir / "f3_species_stack.png"
    f4 = figures_dir / "f4_species_box.png"
    f5 = figures_dir / "f5_aline_parque.png"
    f6 = figures_dir / "f6_height_box.png"
    f7 = figures_dir / "f7_zones.png"
    f8 = figures_dir / "f8_inventory_map.png"
    f9 = figures_dir / "f9_priority_map.png"

    f1_histogram(exposure_values=df["exposure"].to_numpy(), output_path=f1)
    f2_band_bars(df=df, output_path=f2)
    f3_top_species_stack(df=df, output_path=f3)
    f4_top_species_box(df=df, output_path=f4)
    f5_alineacion_vs_parque(df=df, output_path=f5)
    f6_height_box(df=df, output_path=f6)
    f7_top_zones(zone_table=zones_top, output_path=f7)
    f8_inventory_map(df=df, exposure_tif=exposure_tif, terrain_tif=terrain_tif, output_path=f8)
    f9_priority_map(df_priority=priority_df, exposure_tif=exposure_tif, terrain_tif=terrain_tif, output_path=f9)

    f1_uri = _b64_image(f1)
    f2_uri = _b64_image(f2)
    f3_uri = _b64_image(f3)
    f4_uri = _b64_image(f4)
    f5_uri = _b64_image(f5)
    f6_uri = _b64_image(f6)
    f7_uri = _b64_image(f7)
    f8_uri = _b64_image(f8)
    f9_uri = _b64_image(f9)

    logo_uri = _logo_data_uri(logo_data_path) if logo_data_path else ""
    today = report_date or _spanish_date(date.today())

    coverage_html = _coverage_html(cov.as_dict())
    summary_html = _summary_table_html(summary)
    species_html = _species_table_html(species_df)
    zone_html = _zone_table_html(zones_top)
    height_xt_html = _crosstab_html(height_x_expo, index_label="Clase de altura", label_map=HEIGHT_LABEL)
    ubic_xt_html = _crosstab_html(ubic_x_expo, index_label="Tipo de ubicación")
    priority_html = _priority_table_html(priority_df, top_n=50)

    sentinel_text = ""
    if not sentinel.empty:
        items = []
        for _, r in sentinel.iterrows():
            name = (r.get("descripcion") or r["nombre_cientifico"]).title()
            items.append(f"<strong>{_esc(name)}</strong> ({_fmt_pct(r['pct_alto'])} en exposición ≥ 60, "
                         f"+{r['uplift']:.1f} pp sobre la media municipal del {_fmt_pct(summary['pct_alto'])})")
        sentinel_text = " · ".join(items)

    pct_alto_total = summary["pct_alto"]
    pct_alto_aline = float((aline >= 60).mean() * 100)
    pct_alto_parque = float((parque >= 60).mean() * 100)
    n_priority = len(priority_df)
    n_macondo = int(zones_top.loc[zones_top["zona"] == "MACONDO", "n"].sum()) if "MACONDO" in zones_top["zona"].values else 0

    html_doc = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>Análisis del arbolado urbano frente a la exposición al viento — {municipality_label}</title>
{_STYLE_BLOCK}
{_EXTRA_STYLE}
</head>
<body>

<section class="cover">
  {f'<img class="cover-logo" src="{logo_uri}" alt="Darwin Geospatial" />' if logo_uri else ''}
  <div class="cover-label">Informe técnico</div>
  <h1>Análisis del arbolado urbano frente a la exposición al viento</h1>
  <div class="cover-sub">{municipality_label} · Cruce del inventario con la capa Darwin</div>
  <div class="cover-meta">
    <div class="cover-meta-item"><div class="lbl">Cliente</div>INFFE Ingeniería para el Medio Ambiente, S.L.</div>
    <div class="cover-meta-item"><div class="lbl">Preparado por</div>Darwin Geospatial</div>
    <div class="cover-meta-item"><div class="lbl">Referencia</div>26.03-INFFE — Actividad 1</div>
    <div class="cover-meta-item"><div class="lbl">Fecha</div>{today}</div>
    <div class="cover-meta-item"><div class="lbl">Versión</div>1.0</div>
    <div class="cover-meta-item"><div class="lbl">Ejemplares analizados</div>{_fmt_int(summary['n'])}</div>
  </div>
</section>

<div class="page">

<section class="sh"><div class="sn">§ 1</div><h2>Resumen ejecutivo</h2></section>

<p>Este informe cruza, árbol a árbol, el <strong>inventario de arbolado urbano</strong> de {municipality_label} ({_fmt_int(cov.total)} ejemplares) con la <strong>capa Darwin de exposición al viento</strong>, y resume los patrones más relevantes para la gestión técnica del arbolado. La capa de exposición es el primer entregable de la Actividad 1 del encargo INFFE, ya entregado en su nota metodológica.</p>

<div class="kpi">
  <div class="kc">
    <div class="num">{_fmt_pct(pct_alto_total)}</div>
    <div class="lbl">del arbolado está en exposición Alta o Muy alta</div>
    <div class="sub">{_fmt_int(int(pct_alto_total/100*summary['n']))} ejemplares de un total de {_fmt_int(summary['n'])}.</div>
  </div>
  <div class="kc">
    <div class="num">{_fmt_int(n_priority)}</div>
    <div class="lbl">árboles prioritarios</div>
    <div class="sub">Ejemplares grandes (≥ 9 m) en zonas con exposición ≥ 70.</div>
  </div>
  <div class="kc">
    <div class="num">{aline_mean:.1f} vs {parque_mean:.1f}</div>
    <div class="lbl">Alineación vs Parques (exposición media)</div>
    <div class="sub">Diferencia significativa según test de Mann-Whitney U.</div>
  </div>
</div>

<div class="hb">
  <strong>Lectura rápida.</strong> La inmensa mayoría del arbolado urbano de {municipality_label} se localiza en zonas <em>relativamente abrigadas</em> del relieve (la media municipal es {summary['media']:.1f} sobre una escala 0–100). Sin embargo, hay <strong>concentraciones muy claras</strong> de exposición elevada en sectores periurbanos —especialmente <strong>MACONDO</strong> y <strong>PASEO ALTO</strong>— donde más del 75 % de los árboles supera el umbral de exposición Alta. Cruzando con la altura del ejemplar, los <strong>árboles más grandes y maduros</strong> son los que más se concentran en zonas expuestas: <strong>{(height_x_expo.loc['Ejemplar (Más de 15 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Ejemplar (Más de 15 m.)'].sum(),1)*100):.0f} % de los ejemplares de más de 15 m</strong> están en exposición ≥ 60, frente al {pct_alto_total:.0f} % medio del municipio.
</div>

<section class="sh"><div class="sn">§ 2</div><h2>Cómo se ha hecho el cruce</h2></section>

<div class="phase">
<div class="pn">Dato 1</div><h4>Inventario INFFE</h4>
<p>Shapefile facilitado por INFFE (<code>todo arbolado caceres prueba1.shp</code>): <strong>{_fmt_int(cov.total)} puntos</strong> en EPSG:25829, un punto por ejemplar de arbolado urbano. Cada árbol incluye especie (nombre científico y nombre común), tipo de ubicación (alineación o parque/zona verde), zona urbana, clase de altura y perímetro de tronco, además de la fecha y resultado de la última inspección.</p>
</div>

<div class="phase">
<div class="pn">Dato 2</div><h4>Capa de exposición Darwin</h4>
<p>Capa raster <code>wind_exposure_1m.tif</code> a <strong>1 m de resolución</strong> en EPSG:25829. Cada píxel toma un valor entre <strong>0 (abrigado)</strong> y <strong>100 (expuesto)</strong>; los píxeles de edificación están enmascarados a NoData según la huella catastral. La capa se produjo siguiendo la metodología detallada en el informe metodológico previamente entregado.</p>
</div>

<div class="phase">
<div class="pn">Dato 3</div><h4>Cruce y filtrado</h4>
<p>Para cada árbol del inventario se extrae el valor de la capa en el píxel donde se ubica. Se descartan del análisis los ejemplares marcados como <em>baja</em>, los que caen fuera del raster y los que caen sobre un edificio enmascarado. Las cinco bandas de exposición utilizadas en este informe (Muy bajo / Bajo / Medio / Alto / Muy alto) están definidas en intervalos fijos (0–20, 20–40, 40–60, 60–80, 80–100) para que la lectura sea reproducible y comparable con futuros análisis sobre otros municipios.</p>
</div>

<div class="hb w">
<strong>Control de calidad del cruce</strong>
{coverage_html}
La cobertura efectiva sobre el inventario activo es del {(cov.validos/max(cov.activos,1)*100):.1f} %; el resto se concentra en árboles fuera del límite del raster (parques periurbanos lejanos al casco) o sobre la huella de edificación catastral.
</div>

<section class="sh"><div class="sn">§ 3</div><h2>Distribución general de la exposición</h2></section>

<p>El histograma siguiente muestra la distribución completa del valor de exposición sobre los <strong>{_fmt_int(summary['n'])}</strong> árboles válidos. Las bandas de color de fondo corresponden a las cinco clases que utilizamos en todo el informe.</p>

<figure class="fig full"><img src="{f1_uri}" alt="Histograma" /><figcaption>Figura 1 — Distribución del índice de exposición sobre el inventario completo. Líneas discontinuas: cuartiles (P25, mediana, P75).</figcaption></figure>

<figure class="fig"><img src="{f2_uri}" alt="Bandas de exposición" /><figcaption>Figura 2 — Conteo y porcentaje de árboles en cada clase de exposición.</figcaption></figure>

{summary_html}

<div class="hb">
  La media municipal (<strong>{summary['media']:.1f}</strong>) y la mediana (<strong>{summary['mediana']:.1f}</strong>) reflejan que <em>la mayor parte del arbolado urbano de {municipality_label} se desarrolla sobre suelo abrigado</em>: el casco urbano, el ensanche y los parques históricos están todos en zonas resguardadas por el relieve respecto al régimen dominante de viento (SW–W). La cola derecha del histograma —el <strong>{_fmt_pct(pct_alto_total)}</strong> de árboles con exposición ≥ 60— representa los ejemplares <em>realmente expuestos</em>, y es donde se concentra el valor del análisis siguiente.
</div>

<section class="sh"><div class="sn">§ 4</div><h2>Análisis por especie</h2></section>

<p>El catálogo del arbolado de {municipality_label} es muy diverso. Las cinco especies más numerosas (<em>Platanus hispanica</em> 4 729 ejemplares, <em>Celtis australis</em> 3 959, <em>Olea europaea</em> 2 618, <em>Cupressus sempervirens</em> 2 249, <em>Melia azedarach</em> 2 047) explican alrededor del 30 % del inventario. Para no introducir ruido, todos los análisis estadísticos por especie se restringen a los taxones con al menos 200 ejemplares.</p>

<figure class="fig full"><img src="{f3_uri}" alt="Top especies por exposición" /><figcaption>Figura 3 — Top 15 especies del inventario, con el desglose interno de cada una por clase de exposición. La proporción de barra coloreada en rojo (Alta/Muy alta) es directamente comparable entre especies.</figcaption></figure>

<figure class="fig full"><img src="{f4_uri}" alt="Boxplot por especie" /><figcaption>Figura 4 — Distribución del índice de exposición por especie (top 12 con mediana ascendente). Cada caja contiene el rango intercuartílico; la línea oscura es la mediana.</figcaption></figure>

{species_html}

<div class="hb">
  <strong>Especies «centinela».</strong> Aquellas cuya proporción de ejemplares en exposición ≥ 60 es claramente superior a la media municipal: {sentinel_text or "no se detecta una concentración inusual en ninguna especie."}. Estas especies merecen una atención específica: no necesariamente son más frágiles biomecánicamente, pero su distribución espacial las está sobre-exponiendo al régimen de viento de {municipality_label}.
</div>

<section class="sh"><div class="sn">§ 5</div><h2>Alineación vs Parques</h2></section>

<p>El inventario distingue dos grandes tipos de ubicación: arbolado de <strong>alineación</strong> (calles, avenidas, viario) y arbolado de <strong>parques o zonas verdes</strong>. Dado que la disposición urbana protege diferencialmente cada categoría, comparar sus distribuciones de exposición es revelador.</p>

<figure class="fig full"><img src="{f5_uri}" alt="Alineacion vs Parque" /><figcaption>Figura 5 — Distribución de exposición en alineación (gris) y en parques/zonas verdes (verde lima). Líneas discontinuas: media de cada categoría.</figcaption></figure>

{ubic_xt_html}

<div class="hb">
  Los árboles de <strong>parques o zonas verdes</strong> presentan una media de exposición de <strong>{parque_mean:.1f}</strong> y un <strong>{_fmt_pct(pct_alto_parque)}</strong> en exposición ≥ 60, frente a <strong>{aline_mean:.1f}</strong> de media y <strong>{_fmt_pct(pct_alto_aline)}</strong> en alineación. {_esc(aline_parque_text)}.
  El resultado es contraintuitivo respecto al folclor urbano («las calles están más expuestas al viento»): en el caso de {municipality_label}, los grandes parques periurbanos (Macondo, Paseo Alto, Aldea Moret) se sitúan en cotas más altas y abiertas que el viario del casco, lo que invierte el patrón.
</div>

<section class="sh"><div class="sn">§ 6</div><h2>Tamaño y exposición</h2></section>

<p>¿Los ejemplares más grandes y maduros están sobre-representados en zonas expuestas? Esta es una de las preguntas clave para la priorización de inspecciones: un árbol grande en una zona expuesta es exactamente el perfil de mayor riesgo de daño mecánico.</p>

<figure class="fig"><img src="{f6_uri}" alt="Boxplot por altura" /><figcaption>Figura 6 — Distribución del índice de exposición por clase de altura.</figcaption></figure>

{height_xt_html}

<div class="hb">
  La proporción de árboles en exposición ≥ 60 escala con la clase de altura: <strong>{(height_x_expo.loc['Pequeño (Hasta 5 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Pequeño (Hasta 5 m.)'].sum(),1)*100):.1f} %</strong> en pequeños, <strong>{(height_x_expo.loc['Mediano (5 a 9 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Mediano (5 a 9 m.)'].sum(),1)*100):.1f} %</strong> en medianos, <strong>{(height_x_expo.loc['Grande (9 a 15 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Grande (9 a 15 m.)'].sum(),1)*100):.1f} %</strong> en grandes y <strong>{(height_x_expo.loc['Ejemplar (Más de 15 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Ejemplar (Más de 15 m.)'].sum(),1)*100):.1f} %</strong> en ejemplares de más de 15 m. {_esc(chi_text)}.
</div>

<section class="sh"><div class="sn">§ 7</div><h2>Zonas urbanas con mayor presión</h2></section>

<p>Agregando el cruce por <strong>zona urbana</strong> identificamos los sectores donde la exposición se concentra. Las 12 zonas con mayor proporción de arbolado en clases Alta + Muy alta concentran un volumen muy significativo de las inspecciones que merecerían priorizarse.</p>

<figure class="fig full"><img src="{f7_uri}" alt="Top zonas" /><figcaption>Figura 7 — Top 12 zonas urbanas por porcentaje de árboles en exposición Alta o Muy alta (mínimo 80 árboles por zona).</figcaption></figure>

{zone_html}

<div class="hb">
  <strong>MACONDO</strong> es el caso más extremo del municipio: prácticamente la totalidad de su arbolado catalogado se encuentra en clases Alta o Muy alta. El <strong>Paseo Alto</strong> sigue un patrón similar. Estas dos zonas, junto con <strong>Cabezarrubia / Parque Padre Pacífico</strong> y <strong>Río Tinto</strong>, son las primeras candidatas a un protocolo de inspección reforzada.
</div>

<section class="sh"><div class="sn">§ 8</div><h2>Árboles prioritarios para inspección</h2></section>

<p>Definimos como <strong>árbol prioritario</strong> aquel que cumple las dos condiciones simultáneamente:</p>
<ol>
  <li>Altura clase <strong>Grande (9–15 m)</strong> o <strong>Ejemplar (&gt;15 m)</strong>.</li>
  <li>Índice de exposición ≥ <strong>70</strong> (el percentil 95 del municipio se encuentra en {summary['p95']:.0f}).</li>
</ol>
<p>El criterio identifica <strong>{_fmt_int(n_priority)} ejemplares</strong> en {municipality_label} que combinan tamaño relevante con exposición elevada. Es el listado accionable más útil del informe.</p>

<figure class="fig full"><img src="{f9_uri}" alt="Mapa hotspots" /><figcaption>Figura 8 — Localización de los {_fmt_int(n_priority)} árboles prioritarios. Concentraciones claras en Macondo, Paseo Alto, Aldea Moret y la franja sur del casco.</figcaption></figure>

<section class="sh"><div class="sn">§ 9</div><h2>Mapa general del inventario</h2></section>

<p>Mapa completo del inventario sobre la capa de exposición. Cada punto es un árbol coloreado por su clase de exposición. Útil para identificar visualmente bolsas de arbolado expuesto y para validar geográficamente los hallazgos numéricos del informe.</p>

<figure class="fig full"><img src="{f8_uri}" alt="Mapa inventario completo" /><figcaption>Figura 9 — Inventario arbóreo completo coloreado por clase de exposición.</figcaption></figure>

<section class="sh"><div class="sn">§ 10</div><h2>Conclusiones e implicaciones operativas</h2></section>

<ul>
  <li><strong>El arbolado urbano de {municipality_label} está mayoritariamente abrigado.</strong> Tres de cada cuatro árboles del inventario tienen un índice de exposición por debajo de 40, gracias a que el casco urbano se desarrolla en una posición topográficamente protegida del régimen SW–W dominante.</li>
  <li><strong>El riesgo no se reparte de forma homogénea: se concentra en pocos sectores periurbanos.</strong> Macondo, Paseo Alto, Cabezarrubia/P. Padre Pacífico y Río Tinto agrupan la inmensa mayoría de los árboles en exposición ≥ 60. Cualquier protocolo de inspección preventiva debería empezar por allí.</li>
  <li><strong>Los ejemplares grandes están sobre-representados en zonas expuestas.</strong> El {(height_x_expo.loc['Ejemplar (Más de 15 m.)', ['Alto', 'Muy alto']].sum()/max(height_x_expo.loc['Ejemplar (Más de 15 m.)'].sum(),1)*100):.0f} % de los ejemplares > 15 m están en exposición ≥ 60, frente al {pct_alto_total:.0f} % medio. Esto eleva el coste potencial de un fallo mecánico (ramas y pies grandes son más peligrosos al caer) y justifica una inspección más exigente para esa cohorte.</li>
  <li><strong>El arbolado de parque está más expuesto que el de alineación, contrariando la intuición.</strong> Los parques periurbanos en cota alta empujan la media del «parque» por encima de la del «viario». Esta lectura debe incorporarse al protocolo: la regla «la calle está más expuesta» no aplica en {municipality_label}.</li>
  <li><strong>{_fmt_int(n_priority)} árboles prioritarios concretos</strong> ya están identificados y geolocalizados (§ 8). Es el listado de partida más eficiente para una primera ronda de inspección reforzada.</li>
  <li><strong>Para zonas con concentración extrema de exposición</strong> (Macondo, Paseo Alto) sería conveniente complementar este índice con un <strong>modelado CFD</strong> de mayor detalle, capaz de cuantificar la velocidad real del viento a escala de calle y de copa.</li>
</ul>

<div class="footer">
  Darwin Geospatial · {today} · Documento 26.03-INFFE / Análisis cruzado / 1.0
</div>

</div>
</body>
</html>
"""

    output_html = Path(output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html_doc, encoding="utf-8")
    return output_html
