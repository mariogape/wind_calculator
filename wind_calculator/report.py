"""HTML report builder for the Cáceres wind exposure deliverable.

Produces a self-contained HTML document with the same visual identity as the
engagement letter, embedding wind roses and map renders as base64 PNGs.
"""

from __future__ import annotations

import base64
import json
from datetime import date
from pathlib import Path


_SPANISH_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _spanish_date(d: date) -> str:
    return f"{d.day} de {_SPANISH_MONTHS[d.month - 1]} de {d.year}"

from .figures import (
    make_exposure_render,
    make_wind_rose_frequency,
    make_wind_rose_weights,
)


_STYLE_BLOCK = """<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');
:root{--dark:#1b373f;--forest:#426331;--olive:#879753;--lime:#bcbe76;--cream:#fcf5e3;--g100:#f7f7f5;--g200:#e8e8e4;--g300:#d0d0c8;--g500:#8a8a80;--g700:#4a4a44;--txt:#2c2c28}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter','TT Norms',sans-serif;color:var(--txt);background:#fff;line-height:1.7;font-size:15px;-webkit-font-smoothing:antialiased}
.page{max-width:900px;margin:0 auto;padding:0 40px}

/* COVER */
.cover{background:linear-gradient(135deg,var(--dark) 0%,#2a4f3a 50%,var(--forest) 100%);color:#fff;padding:80px 60px;position:relative;overflow:hidden;page-break-after:always}
.cover::before{content:'';position:absolute;top:-100px;right:-100px;width:500px;height:500px;border-radius:50%;background:rgba(188,190,118,.08)}
.cover::after{content:'';position:absolute;bottom:-150px;left:-80px;width:400px;height:400px;border-radius:50%;background:rgba(135,151,83,.06)}
.cover-logo{width:220px;margin-bottom:60px;position:relative;z-index:1;-webkit-mask-image:radial-gradient(ellipse 85% 85% at 50% 50%,rgba(0,0,0,1) 50%,rgba(0,0,0,0) 100%);mask-image:radial-gradient(ellipse 85% 85% at 50% 50%,rgba(0,0,0,1) 50%,rgba(0,0,0,0) 100%)}
.cover-label{font-size:12px;font-weight:600;letter-spacing:3px;text-transform:uppercase;color:var(--lime);margin-bottom:16px;position:relative;z-index:1}
.cover h1{font-family:'Space Grotesk','Codec Pro',sans-serif;font-size:38px;font-weight:700;line-height:1.2;margin-bottom:12px;position:relative;z-index:1}
.cover-sub{font-size:18px;font-weight:300;color:rgba(255,255,255,.8);margin-bottom:50px;position:relative;z-index:1}
.cover-meta{display:grid;grid-template-columns:1fr 1fr;gap:20px;position:relative;z-index:1;border-top:1px solid rgba(255,255,255,.15);padding-top:30px;margin-top:30px}
.cover-meta-item{font-size:13px}
.cover-meta-item .lbl{color:var(--lime);font-weight:600;font-size:10px;letter-spacing:1.5px;text-transform:uppercase;margin-bottom:4px}

/* SECTIONS */
.sh{background:var(--dark);color:#fff;padding:32px 60px;margin:50px -40px 30px;position:relative;page-break-before:always}
.sh::after{content:'';position:absolute;bottom:0;left:60px;width:60px;height:3px;background:var(--lime)}
.sh .sn{font-family:'Space Grotesk',sans-serif;font-size:11px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:var(--lime);margin-bottom:6px}
.sh h2{font-family:'Space Grotesk',sans-serif;font-size:26px;font-weight:700;line-height:1.3}
h3{font-family:'Space Grotesk',sans-serif;font-size:18px;font-weight:600;color:var(--dark);margin:32px 0 14px;padding-bottom:8px;border-bottom:2px solid var(--lime);display:inline-block}
h4{font-family:'Space Grotesk',sans-serif;font-size:15px;font-weight:600;color:var(--forest);margin:24px 0 10px}
p{margin-bottom:14px}
strong{color:var(--dark);font-weight:600}

/* BOXES */
.hb{background:var(--cream);border-left:4px solid var(--forest);padding:18px 24px;margin:20px 0;border-radius:0 6px 6px 0;font-size:14px}
.hb.w{border-left-color:var(--olive);background:#fefdf5}

/* TABLES */
table{width:100%;border-collapse:collapse;margin:18px 0 24px;font-size:14px}
thead th{background:var(--dark);color:#fff;font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:12px;letter-spacing:.5px;text-transform:uppercase;padding:12px 16px;text-align:left}
tbody td{padding:11px 16px;border-bottom:1px solid var(--g200)}
tbody tr:nth-child(even){background:var(--g100)}
.tt td{font-weight:700;color:var(--dark);border-top:2px solid var(--dark);background:var(--cream)!important;font-size:15px}
ul,ol{margin:10px 0 16px 24px}
li{margin-bottom:6px}
li::marker{color:var(--olive)}

/* CARDS */
.sg{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:24px 0}
.sc{background:var(--g100);border-radius:8px;padding:24px;border-top:3px solid var(--forest)}
.sc .cn{font-family:'Space Grotesk',sans-serif;font-size:32px;font-weight:700;color:var(--lime);opacity:.6}
.sc .ct{font-family:'Space Grotesk',sans-serif;font-weight:600;font-size:15px;color:var(--dark);margin:6px 0}
.sc .cl{color:var(--olive);font-size:13px;font-weight:600}

/* PHASES */
.phase{margin:20px 0;padding:20px 24px;background:var(--g100);border-radius:8px;border-left:3px solid var(--olive)}
.phase .pn{font-family:'Space Grotesk',sans-serif;font-weight:700;font-size:11px;letter-spacing:1px;text-transform:uppercase;color:var(--olive);margin-bottom:6px}
.phase h4{margin-top:0;color:var(--dark)}

/* MERMAID */
.mc{background:var(--g100);border-radius:8px;padding:30px 20px;margin:24px 0;text-align:center;overflow-x:auto}

/* FIGURES (specific to this report) */
.fig{margin:28px 0;text-align:center}
.fig img{max-width:100%;height:auto;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.06)}
.fig figcaption{font-family:'Space Grotesk',sans-serif;font-size:12px;color:var(--g700);margin-top:10px;letter-spacing:.3px}
.fig.full img{width:100%}
.figpair{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:24px 0}
.figpair .fig{margin:0}

/* FORMULA */
.formula{font-family:'JetBrains Mono','Consolas',monospace;background:var(--cream);border-radius:6px;padding:14px 18px;margin:14px 0;font-size:14px;color:var(--dark);overflow-x:auto;border-left:3px solid var(--forest)}

/* REFS */
.rl{font-size:12px;color:var(--g700);line-height:1.9}
.rl li{margin-bottom:4px}

/* FOOTER */
.footer{margin-top:60px;padding:30px 0;border-top:2px solid var(--g200);text-align:center;color:var(--g500);font-size:12px}
.footer img{width:120px;opacity:.5;margin-bottom:10px}

@media print{.cover{page-break-after:always}.sh{page-break-before:always;margin-left:0;margin-right:0}body{font-size:13px}.page{padding:0 20px}}
</style>"""


def _b64_image(path: Path, mime: str = "image/png") -> str:
    payload = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def _logo_data_uri(logo_uri_path: Path | None) -> str:
    if logo_uri_path is None:
        return ""
    text = Path(logo_uri_path).read_text(encoding="utf-8").strip()
    if text.startswith("data:"):
        return text
    return _b64_image(Path(text))


def _format_number(value: float, decimals: int = 1) -> str:
    return f"{value:,.{decimals}f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def _climatology_table_rows(climatology: dict) -> str:
    rows = []
    sectors = climatology["sectors"]
    total_count = sum(s["count"] for s in sectors) or 1
    for s in sectors:
        freq_pct = 100.0 * s["count"] / total_count
        weight_pct = 100.0 * s["weight"]
        strong_pct = 100.0 * s["strong_count"] / s["count"] if s["count"] else 0.0
        rows.append(
            "<tr>"
            f"<td><strong>{s['label']}</strong></td>"
            f"<td>{int(s['from_degrees'])}°</td>"
            f"<td>{freq_pct:.1f} %</td>"
            f"<td>{s['mean_speed_mps']:.2f}</td>"
            f"<td>{s['max_speed_mps']:.2f}</td>"
            f"<td>{strong_pct:.2f} %</td>"
            f"<td><strong>{weight_pct:.1f} %</strong></td>"
            "</tr>"
        )
    return "\n".join(rows)


def build_report(
    *,
    output_dir: Path,
    climatology_json: Path,
    pipeline_outputs_json: Path,
    timeseries_csv: Path,
    exposure_tif: Path,
    terrain_tif: Path,
    figures_dir: Path,
    output_html: Path,
    logo_data_path: Path | None = None,
    report_date: str | None = None,
    municipality_label: str = "Cáceres",
) -> Path:
    figures_dir = Path(figures_dir)
    figures_dir.mkdir(parents=True, exist_ok=True)

    rose_freq = figures_dir / "rose_frequency.png"
    rose_weights = figures_dir / "rose_weights.png"
    render_full = figures_dir / "render_full.png"
    render_urban = figures_dir / "render_urban.png"
    render_periphery = figures_dir / "render_periphery.png"

    if not rose_freq.exists():
        make_wind_rose_frequency(timeseries_csv=timeseries_csv, output_path=rose_freq)
    if not rose_weights.exists():
        make_wind_rose_weights(climatology_json=climatology_json, output_path=rose_weights)
    if not render_full.exists():
        make_exposure_render(
            exposure_tif=exposure_tif,
            terrain_tif=terrain_tif,
            output_path=render_full,
            title=f"Exposición al viento — término municipal de {municipality_label}",
        )
    if not render_urban.exists():
        make_exposure_render(
            exposure_tif=exposure_tif,
            terrain_tif=terrain_tif,
            output_path=render_urban,
            bbox=(726200, 4372000, 729000, 4374600),
            title=f"Casco urbano de {municipality_label}",
        )
    if not render_periphery.exists():
        make_exposure_render(
            exposure_tif=exposure_tif,
            terrain_tif=terrain_tif,
            output_path=render_periphery,
            bbox=(727000, 4369000, 730000, 4372000),
            title="Cerros del SE — divisorias expuestas",
        )

    climatology = json.loads(Path(climatology_json).read_text(encoding="utf-8"))
    pipeline_meta = json.loads(Path(pipeline_outputs_json).read_text(encoding="utf-8"))

    table_rows = _climatology_table_rows(climatology)

    rose_freq_uri = _b64_image(rose_freq)
    rose_weights_uri = _b64_image(rose_weights)
    render_full_uri = _b64_image(render_full)
    render_urban_uri = _b64_image(render_urban)
    render_periphery_uri = _b64_image(render_periphery)
    logo_uri = _logo_data_uri(logo_data_path) if logo_data_path else ""

    today = report_date or _spanish_date(date.today())
    period = f"{climatology['start_year']}–{climatology['end_year']}"
    n_samples = climatology["total_samples"]
    threshold = climatology["strong_wind_threshold_mps"]
    lon = climatology["longitude"]
    lat = climatology["latitude"]
    lidar_code = pipeline_meta.get("lidar_product_code", "LIDA3")
    surface_resolution_m = pipeline_meta.get("surface_resolution_m", "1")

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<title>Mapa de exposición al viento — {municipality_label} — Metodología y resultados</title>
{_STYLE_BLOCK}
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>document.addEventListener("DOMContentLoaded",function(){{mermaid.initialize({{startOnLoad:true,theme:"base",themeVariables:{{primaryColor:"#fcf5e3",primaryBorderColor:"#426331",primaryTextColor:"#1b373f",lineColor:"#879753",fontFamily:"Inter,sans-serif"}}}})}});</script>
</head>
<body>

<section class="cover">
  {f'<img class="cover-logo" src="{logo_uri}" alt="Darwin Geospatial" />' if logo_uri else ''}
  <div class="cover-label">Informe técnico</div>
  <h1>Mapa de exposición al viento de {municipality_label}</h1>
  <div class="cover-sub">Metodología y resultados</div>
  <div class="cover-meta">
    <div class="cover-meta-item"><div class="lbl">Cliente</div>INFFE Ingeniería para el Medio Ambiente, S.L.</div>
    <div class="cover-meta-item"><div class="lbl">Preparado por</div>Darwin Geospatial</div>
    <div class="cover-meta-item"><div class="lbl">Referencia</div>26.03-INFFE — Actividad 1</div>
    <div class="cover-meta-item"><div class="lbl">Fecha</div>{today}</div>
    <div class="cover-meta-item"><div class="lbl">Versión</div>1.0</div>
    <div class="cover-meta-item"><div class="lbl">Resolución</div>{surface_resolution_m} m / píxel</div>
  </div>
</section>

<div class="page">

<section class="sh"><div class="sn">§ 1</div><h2>Resumen ejecutivo</h2></section>
<p>Este documento recoge la metodología y los resultados de la <strong>capa de exposición relativa al viento</strong> producida por Darwin Geospatial para el término municipal de {municipality_label}, primer entregable del encargo <strong>26.03-INFFE</strong>. El producto es un ráster continuo a <strong>{surface_resolution_m} m/píxel</strong> que asigna a cada punto del territorio un índice normalizado en el rango <strong>0 (abrigado) — 100 (expuesto)</strong>, ponderado por la frecuencia y la intensidad de los vientos fuertes registrados en el área.</p>

<div class="sg">
  <div class="sc"><div class="cn">{surface_resolution_m} m</div><div class="ct">Resolución</div><div class="cl">MDS LiDAR PNOA</div></div>
  <div class="sc"><div class="cn">{period}</div><div class="ct">Climatología</div><div class="cl">ERA5-Land · {n_samples:,} muestras horarias</div></div>
  <div class="sc"><div class="cn">8</div><div class="ct">Sectores direccionales</div><div class="cl">N · NE · E · SE · S · SW · W · NW</div></div>
</div>

<div class="hb">
  <strong>Cómo leer el mapa.</strong> El producto es un <strong>índice topográfico relativo</strong>, no una velocidad absoluta del viento. Las zonas rojas son posiciones que el modelo identifica como expuestas a los flujos dominantes (crestas, divisorias, vertientes a barlovento de la dirección crítica); las zonas azules son posiciones abrigadas por el relieve circundante (fondos de valle, vertientes a sotavento). Los píxeles que caen sobre <strong>edificación según Catastro</strong> se han fijado a <em>NoData</em> y no se pintan: el producto se interpreta sobre suelo abierto y arbolado.
</div>

<section class="sh"><div class="sn">§ 2</div><h2>Datos de partida</h2></section>

<div class="phase">
<div class="pn">Fase 1</div><h4>Ámbito de estudio</h4>
<p>El estudio se centra en el <strong>entorno urbano de {municipality_label}</strong> y su periferia inmediata, un área de aproximadamente <strong>10 × 11 km</strong> en torno al casco urbano (centroide ≈ <strong>{lon:.3f}° E, {lat:.3f}° N</strong>). Toda la cadena de cálculo trabaja en UTM ETRS89 zona 29 (<strong>EPSG:25829</strong>) y todas las salidas se entregan en ese mismo sistema de coordenadas.</p>
</div>

<div class="phase">
<div class="pn">Fase 2</div><h4>Modelo digital de superficie</h4>
<p>Como base topográfica se utiliza el modelo digital de superficie más reciente del <strong>Plan Nacional de Ortofotografía Aérea (PNOA-LiDAR)</strong>, accesible a través del CNIG. A partir de él se construye un raster a <strong>1 m de resolución</strong> que combina el terreno desnudo con la huella de los edificios y deja fuera la vegetación, de modo que el cálculo posterior responde solo al efecto del relieve y de las masas construidas sobre el flujo del viento.</p>
</div>

<div class="phase">
<div class="pn">Fase 3</div><h4>Climatología del viento</h4>
<p>El régimen del viento se caracteriza con el reanálisis climático <strong>ERA5-Land</strong> (Copernicus / ECMWF), considerado el estándar europeo para análisis climáticos de este tipo. Se recupera la serie horaria de viento a 10 m sobre {municipality_label} para el periodo <strong>{period}</strong> ({n_samples:,} registros), de la que se obtiene la velocidad y la dirección de procedencia hora a hora.</p>
</div>

<div class="phase">
<div class="pn">Fase 4</div><h4>Máscara de edificios (Catastro INSPIRE)</h4>
<p>La capa <strong>INSPIRE Buildings</strong> de la <em>Dirección General del Catastro</em> se descarga directamente del feed Atom municipal (<code>A.ES.SDGC.BU.10900.zip</code> para {municipality_label}, EPSG:25829) y se rasteriza al mismo grid que la superficie. Esos píxeles se fuerzan a <strong>−9999</strong> (NoData) en la salida final.</p>
</div>

<div class="mc">
<pre class="mermaid">
flowchart TD
  A[AOI municipal IGN] --> B[CRS proyectado UTM ETRS89]
  C[Catalogo CNIG / PNOA LiDAR] --> D[LAZ ground + building]
  D --> E[MDS terreno+edificios 1 m]
  F[ERA5-Land u10, v10 horario] --> G[velocidad + direccion FROM]
  G --> H[Climatologia 8 sectores]
  H --> I[Pesos strong-wind]
  E --> J[SAGA Wind Effect por sector]
  I --> J
  J --> K[Composicion ponderada + normalizacion]
  L[Catastro INSPIRE Buildings] --> M[Mascara edificios 1 m]
  M --> N[Indice exposicion 0-100]
  K --> N
</pre>
</div>

<section class="sh"><div class="sn">§ 3</div><h2>Climatología del viento en {municipality_label}</h2></section>

<p>La caracterización climática se hace sobre <strong>{n_samples:,} muestras horarias</strong> del periodo {period} en el punto ERA5-Land más próximo a {municipality_label}. La tabla siguiente resume, por sector de procedencia, su frecuencia, sus velocidades media y máxima, la frecuencia con la que se observan vientos fuertes (≥ <strong>{threshold:.2f} m/s</strong>, percentil 90 de la serie), y el peso final que cada sector recibe en el cálculo del índice de exposición.</p>

<table>
<thead><tr>
<th>Sector</th><th>Origen</th><th>Frecuencia</th><th>V. media (m/s)</th><th>V. máx (m/s)</th><th>% viento fuerte</th><th>Peso modelo</th>
</tr></thead>
<tbody>
{table_rows}
</tbody>
</table>

<div class="figpair">
  <figure class="fig"><img src="{rose_freq_uri}" alt="Roseta de frecuencias por bins de velocidad" /><figcaption>Figura 1 — Rosa de frecuencias horarias agrupadas en bins de velocidad (8 sectores).</figcaption></figure>
  <figure class="fig"><img src="{rose_weights_uri}" alt="Roseta de pesos del modelo" /><figcaption>Figura 2 — Pesos finales asignados a cada sector en el índice de exposición.</figcaption></figure>
</div>

<div class="hb">
<strong>Lectura del régimen.</strong> La rosa de frecuencias muestra que las direcciones más habituales son <strong>W (≈ 21 %)</strong>, <strong>NW (≈ 18 %)</strong> y <strong>SW (≈ 13 %)</strong>. Sin embargo, los <strong>vientos fuertes</strong> (≥ {threshold:.1f} m/s) se concentran de forma muy marcada en el sector <strong>SW</strong> y, en menor medida, en <strong>W</strong>. Por eso el modelo asigna a SW <strong>≈ 38 %</strong> y a W <strong>≈ 28 %</strong> del peso total: dos tercios del índice de exposición resultante están dirigidos por flujos del cuadrante suroeste–oeste, que es donde se concentran las situaciones meteorológicas más relevantes para la integridad mecánica del arbolado.
</div>

<section class="sh"><div class="sn">§ 4</div><h2>Cálculo del índice de exposición</h2></section>

<h3>4.1 SAGA Wind Effect por sector</h3>
<p>Para cada uno de los 8 sectores se ejecuta la herramienta <strong>SAGA <em>Wind Effect</em></strong> (módulo <code>ta_morphometry</code>, tool <code>15</code>) sobre la superficie MDS terreno+edificios. El algoritmo evalúa, en cada píxel, el grado de <em>abrigo topográfico</em> respecto a un flujo idealizado que llega desde una dirección dada, comparando la altura del píxel con la del horizonte que ve desde esa dirección a una distancia máxima dada. Parámetros utilizados:</p>
<ul>
  <li><strong>MAXDIST</strong>: 1.0 km (distancia máxima de búsqueda del horizonte).</li>
  <li><strong>ACCEL</strong>: 1.5 (factor de aceleración por convexidad local).</li>
  <li><strong>PYRAMIDS</strong>: activadas (acelera el cálculo en grids grandes).</li>
</ul>

<h3>4.2 Convención de direcciones</h3>
<p>ERA5-Land devuelve direcciones <em>de procedencia</em> (FROM) en convención meteorológica. SAGA <em>Wind Effect</em> espera direcciones <em>hacia donde sopla</em> (TO). La pipeline aplica la conversión:</p>
<div class="formula">dir_TO = (dir_FROM + 180°) mod 360°</div>

<h3>4.3 Ponderación por viento fuerte</h3>
<p>Cada hora de la serie ERA5-Land se asigna a su sector más cercano (45° de paso). El peso de cada sector se construye no como una frecuencia simple, sino realzando los <strong>episodios de viento fuerte</strong>, que son los relevantes para los daños mecánicos. Se define el umbral <code>τ = max(0, P90)</code>, donde P90 es el percentil 90 de toda la serie de velocidades en el AOI. Para {municipality_label}, <strong>τ = {threshold:.2f} m/s</strong>. El peso bruto de un sector <em>s</em> es:</p>
<div class="formula">w_raw[s] = Σ<sub>i ∈ s</sub> max(0, speed<sub>i</sub> − τ)<sup>3</sup></div>
<p>y los pesos finales se normalizan a 1:</p>
<div class="formula">w[s] = w_raw[s] / Σ<sub>k</sub> w_raw[k]</div>
<p>El exponente cúbico es coherente con el hecho de que la fuerza ejercida por el viento sobre una estructura escala aproximadamente con el cubo de la velocidad (potencia eólica ∝ v³), de manera que las pocas horas con velocidades altas contribuyen al peso mucho más que las muchas horas de viento moderado.</p>

<h3>4.4 Composición del índice y normalización</h3>
<p>Para cada sector con peso no nulo se calcula su raster Wind Effect, se normaliza al rango [0, 1] mediante <strong>recorte por percentiles 2–98</strong> (para evitar que valores extremos del relieve dominen la escala), y se acumula con su peso correspondiente. El sumatorio resultante se vuelve a normalizar 2–98 y se escala al rango <strong>0–100</strong>:</p>
<div class="formula">exposure(x) = norm<sub>2-98</sub>( Σ<sub>s</sub> w[s] · norm<sub>2-98</sub>(WindEffect<sub>s</sub>(x)) ) × 100</div>
<p>SAGA Wind Effect es originalmente un índice de <em>abrigo</em> (mayor valor → más abrigado): la doble normalización por percentiles invierte de forma estable la escala para que los valores altos del producto final correspondan a posiciones <strong>expuestas</strong>.</p>

<h3>4.5 Máscara de edificios</h3>
<p>El SAGA Wind Effect es un índice estrictamente <strong>topográfico</strong>: representa el efecto del relieve sobre el flujo, pero <em>no</em> el flujo a escala de fachada o de calle. Aplicado con la superficie terreno+edificios, los valores que se obtienen sobre cubiertas y muros responden a la geometría de los volúmenes edificados, no al microclima urbano real, y pueden inducir interpretaciones engañosas en estudios de arbolado urbano. Por ese motivo el producto final se enmascara con la <strong>capa Catastro INSPIRE Buildings</strong> ({municipality_label}, código municipal 10900): los píxeles que caen dentro de un polígono de edificación se fijan a <strong>−9999 (NoData)</strong> y no se pintan en la cartografía. La interpretación queda restringida a calles, espacios libres, parques y zonas no edificadas, que es donde el inventario arbóreo se materializa.</p>

<div class="mc">
<pre class="mermaid">
flowchart LR
  A[MDS terreno+edificios 1 m] --> B[SAGA Wind Effect 8 direcciones]
  C[Climatologia ERA5-Land] --> D[Pesos strong-wind v3]
  B --> E[Normalizacion P2-P98 por sector]
  E --> F[Suma ponderada por sector]
  D --> F
  F --> G[Renormalizacion P2-P98]
  G --> H[Escalado 0-100]
  I[Catastro Buildings] --> J[Mascara edificios]
  J --> H
  H --> K[wind_exposure_1m.tif]
</pre>
</div>

<section class="sh"><div class="sn">§ 5</div><h2>Resultados</h2></section>

<p>La capa final se entrega como GeoTIFF de 32 bits en EPSG:25829, con <em>NoData</em> = −9999. Las figuras siguientes muestran tres lecturas representativas del producto sobre {municipality_label}: vista municipal completa, casco urbano y un cerro periférico al sureste de la ciudad.</p>

<figure class="fig full"><img src="{render_full_uri}" alt="Render municipal completo" /><figcaption>Figura 3 — Vista municipal de la capa de exposición al viento. Las divisorias y las vertientes orientadas al SW–W aparecen en tonos rojos; los fondos de valle y los reversos topográficos respecto a las direcciones dominantes aparecen en tonos azules.</figcaption></figure>

<figure class="fig full"><img src="{render_urban_uri}" alt="Render casco urbano" /><figcaption>Figura 4 — Detalle del casco urbano. Los polígonos de edificación procedentes de Catastro se representan como NoData (sin color) sobre el sombreado del relieve; el índice solo se interpreta sobre viario, plazas, parques y espacios libres.</figcaption></figure>

<figure class="fig full"><img src="{render_periphery_uri}" alt="Render cerros del sureste" /><figcaption>Figura 5 — Sector periférico al sureste. La cresta principal del relieve (orientación SW–NE) aparece marcada en tonos rojos por su exposición a los flujos del SW; la vertiente de sotavento, en azul.</figcaption></figure>

<div class="hb">
<strong>Interpretación rápida.</strong> Valores próximos a <strong>0</strong> (azules) corresponden a posiciones donde el modelo identifica un fuerte abrigo topográfico respecto al régimen ponderado de Cáceres (fondos de valle, vertientes a sotavento del SW–W). Valores próximos a <strong>100</strong> (rojos) corresponden a posiciones expuestas (crestas, divisorias, hombros topográficos a barlovento de los flujos críticos). Valores intermedios indican exposición moderada; conviene leerlos con el sombreado del relieve para identificar el motivo geométrico que los explica.
</div>

<section class="sh"><div class="sn">§ 6</div><h2>Limitaciones e interpretación</h2></section>

<ul>
  <li><strong>Índice topográfico relativo.</strong> El producto cuantifica exposición geométrica al flujo dominante, no la velocidad absoluta del viento ni una probabilidad de daño. Dos píxeles con el mismo valor en distintas zonas del municipio reciben la misma calificación de exposición <em>relativa</em> dentro de {municipality_label}.</li>
  <li><strong>Modelado de mayor detalle.</strong> Para profundizar en zonas concretas (calles del casco antiguo, divisorias arboladas, hotspots identificados a posteriori) sería conveniente complementar este índice con un <strong>modelado CFD</strong> sobre áreas reducidas, capaz de resolver el flujo a escala de calle y de edificio.</li>
</ul>

<div class="footer">
  Darwin Geospatial · {today} · Documento 26.03-INFFE / 1.0
</div>

</div>
</body>
</html>
"""

    output_html = Path(output_html)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    output_html.write_text(html, encoding="utf-8")
    return output_html
