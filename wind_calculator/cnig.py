from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

import requests


_BASE_URL = "https://centrodedescargas.cnig.es/CentroDescargas"
_TOTAL_RE = re.compile(r'id="totalArchivos" name="totalArchivos" value="(?P<total>\d+)"')
_ROW_SPLIT = '<tr class="fontSize08em row100">'
_SEC_RE = re.compile(r'linkDescDir_(?P<sec>\d+)"')
_NAME_RE = re.compile(r'txtLeftCenterTablas">(?P<name>[^<]+)</div>')
_FORMAT_RE = re.compile(r'<td data-th="Formato">.*?displayInlineBlock">(?P<format>[^<]+)</div>', re.S)


@dataclass(frozen=True)
class CnigDownload:
    sequential_id: str
    name: str
    format: str


class CnigClient:
    def __init__(self, timeout: int = 60) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "wind-calculator/0.1 (+https://github.com/mario/wind_calculator)",
            }
        )

    def _url(self, path: str) -> str:
        return f"{_BASE_URL}/{path.lstrip('/')}"

    def _warm_product_search(self, product_group: str, product_code: str) -> None:
        response = self.session.get(
            self._url("buscar-mapa"),
            params={"codAgr": product_group, "codSerie": product_code},
            timeout=self.timeout,
        )
        response.raise_for_status()

    @staticmethod
    def _tile_key(name: str) -> str:
        parts = name.split("-")
        if len(parts) >= 3:
            return "-".join(parts[-3:])
        return name

    @staticmethod
    def _preference(name: str) -> int:
        upper_name = name.upper()
        if "REGCAN95" in upper_name:
            return 0
        if "ETRS89" in upper_name:
            return 1
        if "WGS84" in upper_name:
            return 2
        return 99

    def _parse_page_downloads(self, page_html: str) -> list[CnigDownload]:
        downloads: list[CnigDownload] = []
        for row in page_html.split(_ROW_SPLIT)[1:]:
            sec_match = _SEC_RE.search(row)
            name_match = _NAME_RE.search(row)
            format_match = _FORMAT_RE.search(row)
            if not sec_match or not name_match or not format_match:
                continue
            downloads.append(
                CnigDownload(
                    sequential_id=sec_match.group("sec"),
                    name=html.unescape(name_match.group("name")).strip(),
                    format=html.unescape(format_match.group("format")).strip(),
                )
            )
        return downloads

    def search_files(
        self,
        *,
        product_group: str,
        product_code: str,
        geometry_geojson: str,
        file_format: str = "COG",
    ) -> list[CnigDownload]:
        self._warm_product_search(product_group=product_group, product_code=product_code)

        response = self.session.post(
            self._url("resultados-busqueda-visor"),
            data={
                "series": product_code,
                "codSerie": product_code,
                "codAgr": product_group,
                "coordenadas": geometry_geojson,
                "unProducto": "",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()

        downloads: dict[str, CnigDownload] = {}
        expected_total: int | None = None
        page_number = 1

        while True:
            page = self.session.get(
                self._url("archivosTotalesSerie"),
                params={
                    "numPagina": str(page_number),
                    "codAgr": product_group,
                    "codSerie": product_code,
                    "series": product_code,
                    "coordenadas": geometry_geojson,
                    "codTipoArchivo": file_format,
                },
                timeout=self.timeout,
            )
            page.raise_for_status()
            page_html = page.text

            total_match = _TOTAL_RE.search(page_html)
            if total_match:
                expected_total = int(total_match.group("total"))

            page_downloads = self._parse_page_downloads(page_html)

            if not page_downloads:
                break

            previous_count = len(downloads)
            for download in page_downloads:
                downloads[download.sequential_id] = download

            if len(downloads) == previous_count:
                break
            if expected_total is not None and len(downloads) >= expected_total:
                break

            page_number += 1

        preferred_tiles: dict[str, CnigDownload] = {}
        for download in downloads.values():
            key = self._tile_key(download.name)
            current = preferred_tiles.get(key)
            if current is None or self._preference(download.name) < self._preference(current.name):
                preferred_tiles[key] = download

        result = sorted(preferred_tiles.values(), key=lambda item: item.name.lower())
        if not result:
            raise RuntimeError(
                f"CNIG no ha devuelto ficheros para {product_code} con la geometria indicada."
            )
        return result

    def download_file(self, download: CnigDownload, target_path: str | Path) -> Path:
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.stat().st_size > 0:
            return target

        init_response = self.session.get(
            self._url("initDescargaDir"),
            params={"secuencial": download.sequential_id},
            timeout=self.timeout,
        )
        init_response.raise_for_status()
        payload = init_response.json()

        if payload.get("muestraLic") == "SI":
            raise RuntimeError(
                f"El fichero {download.name} requiere aceptacion de licencia interactiva y no puede descargarse automaticamente."
            )

        download_response = self.session.post(
            self._url("descargaDir"),
            data={"secDescDirLA": payload["secuencialDescDir"]},
            stream=True,
            timeout=self.timeout,
        )
        download_response.raise_for_status()

        with target.open("wb") as dst:
            for chunk in download_response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    dst.write(chunk)

        return target

    def search_and_download_mdt02(
        self,
        *,
        geometry_geojson: str,
        target_dir: str | Path,
    ) -> list[Path]:
        downloads = self.search_files(
            product_group="MOMDT",
            product_code="MDT02",
            geometry_geojson=geometry_geojson,
            file_format="COG",
        )
        output_dir = Path(target_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        local_paths: list[Path] = []
        for download in downloads:
            local_paths.append(self.download_file(download, output_dir / download.name))
        return local_paths
