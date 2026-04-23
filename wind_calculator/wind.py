from __future__ import annotations

import csv
import json
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


SECTOR_LABELS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
SECTOR_FROM_DEGREES = [0, 45, 90, 135, 180, 225, 270, 315]
REPO_ROOT = Path(__file__).resolve().parent.parent
LOCAL_CDS_CONFIG = REPO_ROOT / "config" / "cdsapi.credentials"


@dataclass(frozen=True)
class WindSector:
    label: str
    from_degrees: int
    count: int
    frequency: float
    mean_speed_mps: float
    max_speed_mps: float
    strong_count: int
    strong_frequency: float
    weight_raw: float
    weight: float


@dataclass(frozen=True)
class WindClimatology:
    provider: str
    longitude: float
    latitude: float
    start_year: int
    end_year: int
    total_samples: int
    weighting_method: str
    strong_wind_percentile: float
    strong_wind_threshold_mps: float
    strong_wind_exponent: float
    sectors: list[WindSector]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["sectors"] = [asdict(sector) for sector in self.sectors]
        return payload


def _timeseries_request(
    start_year: int,
    end_year: int,
    latitude: float,
    longitude: float,
) -> dict:
    return {
        "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
        "location": {
            "latitude": float(latitude),
            "longitude": float(longitude),
        },
        "date": f"{start_year:04d}-01-01/{end_year:04d}-12-31",
        "data_format": "csv",
    }


def _direction_from_uv(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return (180.0 + np.degrees(np.arctan2(u, v))) % 360.0


def _sector_index(direction_from: np.ndarray) -> np.ndarray:
    return (((direction_from + 22.5) % 360.0) // 45.0).astype(np.int16)


def _write_timeseries_csv(rows: list[tuple[str, float, float, float, float, str]], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "timestamp_utc",
                "u10_mps",
                "v10_mps",
                "speed_mps",
                "direction_from_deg",
                "sector",
            ]
        )
        writer.writerows(rows)


def _write_summary_json(summary: WindClimatology, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")


def _parse_cds_credentials(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            continue
        values[key.strip().lower()] = value.strip()

    url = values.get("url")
    access_key = values.get("key")
    if not url or not access_key:
        raise ValueError(
            f"El fichero de credenciales {path} debe contener las lineas 'url: ...' y 'key: ...'."
        )
    return {"url": url, "key": access_key}


def _load_cds_credentials() -> dict[str, str] | None:
    local_path = LOCAL_CDS_CONFIG
    if local_path.exists():
        return _parse_cds_credentials(local_path)

    home_path = Path.home() / ".cdsapirc"
    if home_path.exists():
        return _parse_cds_credentials(home_path)

    return None


def _download_timeseries(
    *,
    start_year: int,
    end_year: int,
    latitude: float,
    longitude: float,
    target: Path,
) -> Path:
    if target.exists() and target.stat().st_size > 0:
        return target

    try:
        import cdsapi  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Falta la dependencia 'cdsapi'. Instala requirements.txt y configura el acceso al Climate Data Store."
        ) from exc

    def is_license_error(exc: Exception) -> bool:
        return "required licences not accepted" in str(exc).lower()

    def retrieve(request: dict, file_path: Path) -> Path:
        if file_path.exists() and file_path.stat().st_size > 0:
            return file_path
        try:
            client.retrieve("reanalysis-era5-land-timeseries", request, str(file_path))
        except Exception as exc:
            if file_path.exists():
                file_path.unlink()
            if is_license_error(exc):
                raise RuntimeError(
                    "No se ha aceptado la licencia de ERA5-Land time-series en CDS. "
                    "Abre https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land-timeseries?tab=download#manage-licences "
                    "y acepta la licencia antes de reintentar."
                ) from exc
            raise
        return file_path

    target.parent.mkdir(parents=True, exist_ok=True)
    credentials = _load_cds_credentials()
    if credentials is None:
        raise RuntimeError(
            "No se han encontrado credenciales CDS. Crea 'config/cdsapi.credentials' en el repo "
            "o '%USERPROFILE%\\\\.cdsapirc' con las lineas 'url: ...' y 'key: ...'."
        )
    client = cdsapi.Client(url=credentials["url"], key=credentials["key"])
    return retrieve(
        _timeseries_request(start_year=start_year, end_year=end_year, latitude=latitude, longitude=longitude),
        target,
    )


def _read_timeseries_rows(path: Path) -> list[dict[str, str]]:
    if not zipfile.is_zipfile(path):
        raise RuntimeError(f"Se esperaba un ZIP CSV de CDS en {path.name}, pero el fichero no es un zip valido.")

    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise RuntimeError(f"El ZIP {path.name} no contiene ningun CSV.")
        with archive.open(members[0], "r") as handle:
            text_handle = (line.decode("utf-8") for line in handle)
            return list(csv.DictReader(text_handle))


def build_wind_climatology(
    *,
    longitude: float,
    latitude: float,
    start_year: int,
    end_year: int,
    cache_dir: str | Path,
    timeseries_csv: str | Path | None = None,
    summary_json: str | Path | None = None,
    weighting_method: str = "strong_wind",
    strong_wind_percentile: float = 90.0,
    strong_wind_min_mps: float = 0.0,
    strong_wind_exponent: float = 3.0,
) -> WindClimatology:
    if weighting_method not in {"mean_speed", "strong_wind"}:
        raise ValueError("weighting_method debe ser 'mean_speed' o 'strong_wind'.")
    if not (0.0 <= strong_wind_percentile <= 100.0):
        raise ValueError("strong_wind_percentile debe estar entre 0 y 100.")
    if strong_wind_min_mps < 0.0:
        raise ValueError("strong_wind_min_mps no puede ser negativo.")
    if strong_wind_exponent <= 0.0:
        raise ValueError("strong_wind_exponent debe ser mayor que 0.")

    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    counts = np.zeros(8, dtype=np.int64)
    speed_sums = np.zeros(8, dtype=np.float64)
    max_speeds = np.zeros(8, dtype=np.float64)
    sample_speeds: list[float] = []
    sample_sectors: list[int] = []
    timeseries_rows: list[tuple[str, float, float, float, float, str]] = []
    total_samples = 0

    archive_path = _download_timeseries(
        start_year=start_year,
        end_year=end_year,
        latitude=latitude,
        longitude=longitude,
        target=cache_path / f"era5land_timeseries_u10_v10_{start_year}_{end_year}.zip",
    )

    raw_rows = _read_timeseries_rows(archive_path)
    for row in raw_rows:
        try:
            timestamp = datetime.fromisoformat(row["valid_time"]).replace(tzinfo=timezone.utc)
            u_value = float(row["u10"])
            v_value = float(row["v10"])
        except (KeyError, TypeError, ValueError):
            continue

        speed_value = float(np.sqrt(u_value**2 + v_value**2))
        direction_value = float(_direction_from_uv(np.asarray([u_value]), np.asarray([v_value]))[0])
        if not np.isfinite(speed_value) or not np.isfinite(direction_value):
            continue

        idx = int(_sector_index(np.asarray([direction_value]))[0])
        counts[idx] += 1
        speed_sums[idx] += speed_value
        max_speeds[idx] = max(max_speeds[idx], speed_value)
        sample_speeds.append(speed_value)
        sample_sectors.append(idx)
        total_samples += 1
        timeseries_rows.append(
            (
                timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
                u_value,
                v_value,
                speed_value,
                direction_value,
                SECTOR_LABELS[idx],
            )
        )

    if total_samples == 0:
        raise RuntimeError("No se han podido obtener muestras validas de viento para el periodo solicitado.")

    frequencies = counts / float(total_samples)
    mean_speeds = np.divide(
        speed_sums,
        counts,
        out=np.zeros_like(speed_sums),
        where=counts > 0,
    )
    strong_threshold = float(
        max(
            strong_wind_min_mps,
            np.nanpercentile(np.asarray(sample_speeds, dtype=np.float64), strong_wind_percentile),
        )
    )

    strong_counts = np.zeros(8, dtype=np.int64)
    raw_weights = np.zeros(8, dtype=np.float64)
    if weighting_method == "mean_speed":
        raw_weights = frequencies * mean_speeds
        strong_counts = counts.copy()
    else:
        for idx, speed_value in zip(sample_sectors, sample_speeds):
            if speed_value < strong_threshold:
                continue
            strong_counts[idx] += 1
            raw_weights[idx] += (speed_value - strong_threshold) ** strong_wind_exponent

        if float(raw_weights.sum()) <= 0.0:
            for idx, speed_value in zip(sample_sectors, sample_speeds):
                raw_weights[idx] += speed_value**strong_wind_exponent
            strong_counts = counts.copy()

    strong_frequencies = strong_counts / float(total_samples)
    weight_sum = float(raw_weights.sum())
    normalized_weights = raw_weights / weight_sum if weight_sum > 0 else raw_weights

    summary = WindClimatology(
        provider="ERA5-Land hourly time-series",
        longitude=float(longitude),
        latitude=float(latitude),
        start_year=int(start_year),
        end_year=int(end_year),
        total_samples=int(total_samples),
        weighting_method=weighting_method,
        strong_wind_percentile=float(strong_wind_percentile),
        strong_wind_threshold_mps=float(strong_threshold),
        strong_wind_exponent=float(strong_wind_exponent),
        sectors=[
            WindSector(
                label=label,
                from_degrees=angle,
                count=int(counts[idx]),
                frequency=float(frequencies[idx]),
                mean_speed_mps=float(mean_speeds[idx]),
                max_speed_mps=float(max_speeds[idx]),
                strong_count=int(strong_counts[idx]),
                strong_frequency=float(strong_frequencies[idx]),
                weight_raw=float(raw_weights[idx]),
                weight=float(normalized_weights[idx]),
            )
            for idx, (label, angle) in enumerate(zip(SECTOR_LABELS, SECTOR_FROM_DEGREES))
        ],
    )

    if timeseries_csv is not None:
        _write_timeseries_csv(timeseries_rows, Path(timeseries_csv))
    if summary_json is not None:
        _write_summary_json(summary, Path(summary_json))

    return summary
