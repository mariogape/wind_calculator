from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def resolve_saga_cmd(value: str | None = None) -> str:
    if value:
        candidate = Path(value)
        if candidate.is_dir():
            exe_name = "saga_cmd.exe" if shutil.which("where") else "saga_cmd"
            candidate = candidate / exe_name
        if candidate.exists():
            return str(candidate)

    for executable in ("saga_cmd.exe", "saga_cmd"):
        found = shutil.which(executable)
        if found:
            return found

    raise FileNotFoundError(
        "No se ha encontrado 'saga_cmd'. Pasa --saga-cmd o añade SAGA GIS al PATH."
    )


def _run(command: list[str]) -> None:
    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        tail = "\n".join((process.stdout or "", process.stderr or "")).strip()
        raise RuntimeError(f"Fallo ejecutando SAGA:\n{tail}")


def from_direction_to_saga(direction_from: int) -> int:
    return (int(direction_from) + 180) % 360


def run_wind_effect(
    *,
    saga_cmd: str,
    dem_path: str | Path,
    out_base: str | Path,
    direction_to_deg: int,
    maxdist_km: float,
    accel: float,
    pyramids: bool = True,
    oldver: bool = False,
) -> Path:
    dem = Path(dem_path)
    base = Path(out_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    out_sgrd = base.with_suffix(".sgrd")
    out_tif = base.with_suffix(".tif")

    _run(
        [
            saga_cmd,
            "ta_morphometry",
            "15",
            "-DEM",
            str(dem),
            "-DIR_UNITS",
            "1",
            "-EFFECT",
            str(out_sgrd),
            "-DIR_CONST",
            f"{float(direction_to_deg):.6f}",
            "-MAXDIST",
            f"{float(maxdist_km):.6f}",
            "-ACCEL",
            f"{float(accel):.6f}",
            "-PYRAMIDS",
            "true" if pyramids else "false",
            "-OLDVER",
            "true" if oldver else "false",
        ]
    )

    _run(
        [
            saga_cmd,
            "io_gdal",
            "2",
            "-GRIDS",
            str(out_sgrd),
            "-FILE",
            str(out_tif),
        ]
    )

    return out_tif
