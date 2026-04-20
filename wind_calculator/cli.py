from __future__ import annotations

import argparse
from datetime import datetime, timezone


def build_parser() -> argparse.ArgumentParser:
    current_year = datetime.now(timezone.utc).year
    default_end_year = current_year - 1
    default_start_year = default_end_year - 9

    parser = argparse.ArgumentParser(
        description="Pipeline AOI -> MDS02 CNIG -> climatologia ERA5-Land -> mapa de exposicion al viento"
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
        "--keep-temp",
        action="store_true",
        help="Conserva los rasters direccionales temporales generados por SAGA",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.end_year < args.start_year:
        parser.error("--end-year debe ser mayor o igual que --start-year")

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
        keep_temp=args.keep_temp,
    )

    for key, value in outputs.items():
        print(f"{key}: {value}")
    return 0
