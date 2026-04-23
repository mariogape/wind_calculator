from __future__ import annotations

import argparse

from .cfd_dataset import create_cfd_test_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline CFD independiente para crear un dataset pequeno de terrain+buildings"
    )
    parser.add_argument("--source-dir", required=True, help="Directorio con terrain/buildings/surface ya generados")
    parser.add_argument("--output-dir", required=True, help="Directorio de salida del dataset CFD")
    parser.add_argument(
        "--window-size",
        type=int,
        default=512,
        help="Tamano del recorte cuadrado en pixeles. Por defecto: 512",
    )
    parser.add_argument(
        "--stride",
        type=int,
        default=None,
        help="Paso de busqueda en pixeles. Si se omite, se calcula automaticamente.",
    )
    parser.add_argument(
        "--min-building-height-m",
        type=float,
        default=2.0,
        help="Altura minima para considerar un pixel como edificio. Por defecto: 2.0 m",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    outputs = create_cfd_test_dataset(
        source_dir=args.source_dir,
        output_dir=args.output_dir,
        window_size=args.window_size,
        stride=args.stride,
        min_building_height_m=args.min_building_height_m,
    )

    print(f"terrain_model: {outputs.terrain_path.resolve()}")
    print(f"building_heights: {outputs.building_heights_path.resolve()}")
    print(f"surface_model: {outputs.surface_model_path.resolve()}")
    print(f"bounds_geojson: {outputs.bounds_geojson_path.resolve()}")
    print(f"metadata: {outputs.metadata_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
