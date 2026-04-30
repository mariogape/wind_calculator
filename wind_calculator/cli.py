from __future__ import annotations

import argparse
from datetime import datetime, timezone


def build_parser() -> argparse.ArgumentParser:
    current_year = datetime.now(timezone.utc).year
    default_end_year = current_year - 1
    default_start_year = default_end_year - 9

    parser = argparse.ArgumentParser(
        description="Pipeline AOI -> LiDAR/MDT+edificios -> climatologia ERA5-Land -> mapa de exposicion al viento"
    )
    parser.add_argument("--aoi", required=True, help="Ruta al AOI vectorial (.gpkg, .shp, .geojson, ...)")
    parser.add_argument("--output-dir", required=True, help="Directorio de salida")
    parser.add_argument(
        "--saga-cmd",
        default=None,
        help="Ruta a saga_cmd o al directorio que lo contiene. Si se omite, se busca en PATH.",
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Directorio opcional de cache para descargas CNIG y ERA5-Land",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=default_start_year,
        help=f"Ano inicial de la climatologia. Por defecto: {default_start_year}",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        default=default_end_year,
        help=f"Ano final de la climatologia. Por defecto: {default_end_year}",
    )
    parser.add_argument(
        "--maxdist-km",
        type=float,
        default=1.0,
        help="MAXDIST en km para SAGA Wind Effect. Por defecto: 1.0",
    )
    parser.add_argument(
        "--accel",
        type=float,
        default=1.5,
        help="Parametro ACCEL de SAGA Wind Effect. Por defecto: 1.5",
    )
    parser.add_argument(
        "--surface-source",
        choices=["lidar_latest", "cnig_raster"],
        default="lidar_latest",
        help="Fuente para construir la superficie terreno+edificios. Por defecto: lidar_latest",
    )
    parser.add_argument(
        "--wind-weighting",
        choices=["strong_wind", "mean_speed"],
        default="strong_wind",
        help="Metodo de ponderacion por direccion. Por defecto: strong_wind",
    )
    parser.add_argument(
        "--strong-wind-percentile",
        type=float,
        default=90.0,
        help="Percentil de velocidad usado como umbral de viento fuerte. Por defecto: 90",
    )
    parser.add_argument(
        "--strong-wind-min-mps",
        type=float,
        default=0.0,
        help="Umbral minimo absoluto en m/s para considerar viento fuerte. Por defecto: 0",
    )
    parser.add_argument(
        "--strong-wind-exponent",
        type=float,
        default=3.0,
        help="Exponente aplicado al exceso sobre el umbral de viento fuerte. Por defecto: 3",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Conserva los rasters direccionales temporales generados por SAGA",
    )
    parser.add_argument(
        "--mask-buildings",
        choices=["none", "catastro", "lidar"],
        default="catastro",
        help=(
            "Fuente de la mascara de edificios para fijar a NoData los pixeles que caen sobre edificacion."
            " 'catastro' descarga la capa INSPIRE Buildings; 'lidar' reusa el raster de alturas;"
            " 'none' desactiva. Por defecto: catastro"
        ),
    )
    parser.add_argument(
        "--catastro-municipality",
        default=None,
        help="Nombre del municipio Catastro (p.ej. CACERES). Obligatorio si --mask-buildings=catastro.",
    )
    parser.add_argument(
        "--catastro-province",
        type=int,
        default=None,
        help="Codigo de provincia Catastro (p.ej. 10). Obligatorio si --mask-buildings=catastro.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.end_year < args.start_year:
        parser.error("--end-year debe ser mayor o igual que --start-year")
    if args.strong_wind_exponent <= 0:
        parser.error("--strong-wind-exponent debe ser mayor que 0")
    if not 0 <= args.strong_wind_percentile <= 100:
        parser.error("--strong-wind-percentile debe estar entre 0 y 100")
    if args.strong_wind_min_mps < 0:
        parser.error("--strong-wind-min-mps no puede ser negativo")
    if args.mask_buildings == "catastro" and (args.catastro_municipality is None or args.catastro_province is None):
        parser.error(
            "--mask-buildings=catastro requiere --catastro-municipality y --catastro-province"
        )

    from .pipeline import run_pipeline

    outputs = run_pipeline(
        aoi_path=args.aoi,
        output_dir=args.output_dir,
        saga_cmd_path=args.saga_cmd,
        cache_dir=args.cache_dir,
        start_year=args.start_year,
        end_year=args.end_year,
        maxdist_km=args.maxdist_km,
        accel=args.accel,
        surface_source=args.surface_source,
        wind_weighting=args.wind_weighting,
        strong_wind_percentile=args.strong_wind_percentile,
        strong_wind_min_mps=args.strong_wind_min_mps,
        strong_wind_exponent=args.strong_wind_exponent,
        keep_temp=args.keep_temp,
        mask_buildings=args.mask_buildings,
        catastro_municipality=args.catastro_municipality,
        catastro_province=args.catastro_province,
    )

    for key, value in outputs.items():
        print(f"{key}: {value}")
    return 0
