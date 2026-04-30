"""One-shot: apply the Catastro INSPIRE buildings mask to an existing wind exposure raster.

Side effects:
- Creates `<exposure>.unmasked.tif` as backup of the original raster (only the first time).
- Overwrites `<exposure>` with building pixels set to NoData (-9999).
- Caches the Catastro zip and GML in `<output_dir>/_cache/catastro/`.
- Writes the rasterized building mask alongside the exposure raster as
  `buildings_catastro_mask_1m.tif`.

Usage:
    python scripts/apply_buildings_mask.py \
        --exposure outputs/caceres_lidar_1m/wind_exposure_1m.tif \
        --municipality CACERES --province 10
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from wind_calculator.catastro import (
    apply_mask_to_raster,
    fetch_buildings_gml,
    rasterize_buildings_to_template,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exposure", required=True, help="Path al wind_exposure_*.tif")
    parser.add_argument("--municipality", required=True, help="Nombre del municipio (p.ej. CACERES)")
    parser.add_argument("--province", type=int, required=True, help="Codigo provincia (p.ej. 10)")
    parser.add_argument("--mask-name", default="buildings_catastro_mask_1m.tif")
    args = parser.parse_args(argv)

    exposure = Path(args.exposure).resolve()
    if not exposure.exists():
        parser.error(f"No existe: {exposure}")
    out_dir = exposure.parent
    cache = out_dir / "_cache" / "catastro"
    mask_tif = out_dir / args.mask_name
    backup = exposure.with_suffix(".unmasked.tif")

    print(f"[1/4] Resolviendo y descargando edificios Catastro para {args.municipality} (prov {args.province:02d})...")
    gml = fetch_buildings_gml(args.municipality, province_code=args.province, cache_dir=cache)
    print(f"      GML: {gml}")

    print(f"[2/4] Rasterizando edificios sobre la rejilla de {exposure.name}...")
    rasterize_buildings_to_template(gml_path=gml, template_raster=exposure, output_path=mask_tif)
    print(f"      Mascara: {mask_tif}")

    if not backup.exists():
        print(f"[3/4] Backup del raster original -> {backup.name}")
        shutil.copy2(exposure, backup)
    else:
        print(f"[3/4] Backup ya existe ({backup.name}), saltando.")

    print(f"[4/4] Aplicando mascara y reescribiendo {exposure.name} con edificios = -9999")
    apply_mask_to_raster(
        source_raster=backup,
        mask_raster=mask_tif,
        output_raster=exposure,
        nodata_value=-9999.0,
    )
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
