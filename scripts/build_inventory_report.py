"""Build the inventory × wind exposure cross-analysis HTML report for Cáceres."""

from __future__ import annotations

import argparse
from pathlib import Path

from wind_calculator.report_inventory import build_inventory_report


DEFAULT_INVENTORY = Path(
    "G:/Unidades compartidas/6. Projects/Projects/26.03 INFFE/Datos INFFE/"
    "wetransfer_todo-arbolado-caceres-prueba1-cpg_2026-04-21_1427/"
    "todo arbolado caceres prueba1.shp"
)
DEFAULT_PIPELINE = Path("outputs/caceres_lidar_1m")
DEFAULT_OUTPUT_HTML = Path(
    "G:/Unidades compartidas/6. Projects/Projects/26.03 INFFE/"
    "Caceres_Inventario_Arbolado_x_Exposicion_Viento.html"
)
DEFAULT_LOGO = Path("c:/tmp/darwin_logo.txt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", default=str(DEFAULT_INVENTORY))
    parser.add_argument("--pipeline-dir", default=str(DEFAULT_PIPELINE))
    parser.add_argument("--output-html", default=str(DEFAULT_OUTPUT_HTML))
    parser.add_argument("--logo", default=str(DEFAULT_LOGO))
    parser.add_argument("--municipality", default="Cáceres")
    parser.add_argument("--report-date", default=None)
    args = parser.parse_args(argv)

    pdir = Path(args.pipeline_dir).resolve()
    figures_dir = pdir / "_report_inventario"
    figures_dir.mkdir(parents=True, exist_ok=True)

    out = build_inventory_report(
        inventory_shp=Path(args.inventory),
        exposure_tif=pdir / "wind_exposure_1m.tif",
        terrain_tif=pdir / "terrain_1m.tif",
        output_html=Path(args.output_html),
        figures_dir=figures_dir,
        logo_data_path=Path(args.logo) if args.logo and Path(args.logo).exists() else None,
        municipality_label=args.municipality,
        report_date=args.report_date,
    )
    print(f"Report written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
