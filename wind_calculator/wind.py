from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, num2date


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
    sectors: list[WindSector]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["sectors"] = [asdict(sector) for sector in self.sectors]
        return payload


def _year_request(year: int, latitude: float, longitude: float) -> dict:
    return {
        "variable": ["10m_u_component_of_wind", "10m_v_component_of_wind"],
        "year": [str(year)],
        "month": [f"{month:02d}" for month in range(1, 13)],
        "day": [f"{day:02d}" for day in range(1, 32)],
        "time": [f"{hour:02d}:00" for hour in range(24)],
        "area": [latitude + 0.05, longitude - 0.05, latitude - 0.05, longitude + 0.05],
        "data_format": "netcdf",
        "download_format": "unarchived",
    }


def _legacy_year_request(year: int, latitude: float, longitude: float) -> dict:
    request = _year_request(year, latitude, longitude).copy()
    request.pop("data_format", None)
    request.pop("download_format", None)
    request["format"] = "netcdf"
    return request


def _find_variable(dataset: Dataset, candidates: list[str]):
    for name in candidates:
        if name in dataset.variables:
            return dataset.variables[name]
    raise KeyError(f"No se ha encontrado ninguna variable entre: {candidates}")


def _to_numpy(variable) -> np.ndarray:
    data = variable[:]
    if hasattr(data, "filled"):
        data = data.filled(np.nan)
    return np.asarray(data, dtype=np.float64)


def _collapse_spatial(array: np.ndarray) -> np.ndarray:
    if array.ndim <= 1:
        return array
    axes = tuple(range(1, array.ndim))
    return np.nanmean(array, axis=axes)


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


def _download_year(
    *,
    year: int,
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

    target.parent.mkdir(parents=True, exist_ok=True)
    credentials = _load_cds_credentials()
    if credentials is None:
        raise RuntimeError(
            "No se han encontrado credenciales CDS. Crea 'config/cdsapi.credentials' en el repo "
            "o '%USERPROFILE%\\\\.cdsapirc' con las lineas 'url: ...' y 'key: ...'."
        )
    client = cdsapi.Client(url=credentials["url"], key=credentials["key"])

    request = _year_request(year, latitude, longitude)
    try:
        client.retrieve("reanalysis-era5-land", request, str(target))
    except Exception:
        if target.exists():
            target.unlink()
        legacy_request = _legacy_year_request(year, latitude, longitude)
        client.retrieve("reanalysis-era5-land", legacy_request, str(target))

    return target


def build_wind_climatology(
    *,
    longitude: float,
    latitude: float,
    start_year: int,
    end_year: int,
    cache_dir: str | Path,
    timeseries_csv: str | Path | None = None,
    summary_json: str | Path | None = None,
) -> WindClimatology:
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    counts = np.zeros(8, dtype=np.int64)
    speed_sums = np.zeros(8, dtype=np.float64)
    timeseries_rows: list[tuple[str, float, float, float, float, str]] = []
    total_samples = 0

    for year in range(start_year, end_year + 1):
        nc_path = _download_year(
            year=year,
            latitude=latitude,
            longitude=longitude,
            target=cache_path / f"era5land_u10_v10_{year}.nc",
        )

        with Dataset(nc_path) as dataset:
            u_var = _find_variable(dataset, ["u10", "10m_u_component_of_wind"])
            v_var = _find_variable(dataset, ["v10", "10m_v_component_of_wind"])
            time_var = dataset.variables["time"]

            u = _collapse_spatial(_to_numpy(u_var))
            v = _collapse_spatial(_to_numpy(v_var))
            speed = np.sqrt(u**2 + v**2)
            direction = _direction_from_uv(u, v)
            valid = np.isfinite(u) & np.isfinite(v) & np.isfinite(speed) & np.isfinite(direction)
            sector_idx = _sector_index(direction)

            counts += np.bincount(sector_idx[valid], minlength=8)
            speed_sums += np.bincount(sector_idx[valid], weights=speed[valid], minlength=8)
            total_samples += int(valid.sum())

            datetimes = num2date(
                time_var[:],
                units=time_var.units,
                calendar=getattr(time_var, "calendar", "standard"),
            )

            for timestamp, u_value, v_value, speed_value, direction_value, is_valid in zip(
                datetimes, u, v, speed, direction, valid
            ):
                if not is_valid:
                    continue
                if hasattr(timestamp, "strftime"):
                    timestamp_text = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    timestamp_text = datetime.fromtimestamp(
                        float(timestamp), tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                idx = int(_sector_index(np.asarray([direction_value]))[0])
                timeseries_rows.append(
                    (
                        timestamp_text,
                        float(u_value),
                        float(v_value),
                        float(speed_value),
                        float(direction_value),
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
    raw_weights = frequencies * mean_speeds
    weight_sum = float(raw_weights.sum())
    normalized_weights = raw_weights / weight_sum if weight_sum > 0 else raw_weights

    summary = WindClimatology(
        provider="ERA5-Land hourly",
        longitude=float(longitude),
        latitude=float(latitude),
        start_year=int(start_year),
        end_year=int(end_year),
        total_samples=int(total_samples),
        sectors=[
            WindSector(
                label=label,
                from_degrees=angle,
                count=int(counts[idx]),
                frequency=float(frequencies[idx]),
                mean_speed_mps=float(mean_speeds[idx]),
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
