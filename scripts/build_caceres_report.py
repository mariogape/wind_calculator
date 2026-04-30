"""Build the Cáceres wind exposure methodology + results HTML report.

Generates the 5 figures (2 wind roses + 3 map renders) into the report
directory and assembles a self-contained HTML at the configured destination.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from wind_calculator.report import build_report


DEFAULT_OUTPUT_DIR = Path("outputs/caceres_lidar_1m")
DEFAULT_REPORT_HTML = Path(
    "G:/Unidades compartidas/6. Projects/Projects/26.03 INFFE/"
    "Caceres_Mapa_Exposicion_Viento_Metodologia.html"
)
DEFAULT_LOGO = Path("c:/tmp/darwin_logo.txt")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pipeline-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--output-html", default=str(DEFAULT_REPORT_HTML))
    parser.add_argument("--logo", default=str(DEFAULT_LOGO))
    parser.add_argument("--municipality", default="Cáceres")
    parser.add_argument("--report-date", default=None)
    args = parser.parse_args(argv)

    pdir = Path(args.pipeline_dir).resolve()
    figures_dir = pdir / "_report"
    figures_dir.mkdir(parents=True, exist_ok=True)

    out = build_report(
        output_dir=pdir,
        climatology_json=pdir / "wind_climatology.json",
        pipeline_outputs_json=pdir / "pipeline_outputs.json",
        timeseries_csv=pdir / "wind_timeseries.csv",
        exposure_tif=pdir / "wind_exposure_1m.tif",
        terrain_tif=pdir / "terrain_1m.tif",
        figures_dir=figures_dir,
        output_html=Path(args.output_html),
        logo_data_path=Path(args.logo) if args.logo and Path(args.logo).exists() else None,
        report_date=args.report_date,
        municipality_label=args.municipality,
    )
    print(f"Report written to: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
