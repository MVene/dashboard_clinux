"""Descarga, solo lectura, el respaldo Clinux más reciente desde Drive usando
credenciales temporales de GitHub Actions (Workload Identity Federation).

Ejemplo:
    python -m scripts.drive_wif --folder-id 'ID_CARPETA' --output /tmp/clinux.sql

No registra secretos, IDs de archivos ni contenido comercial en la salida.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import os
from pathlib import Path
import re

_FOLDER_ID = re.compile(r"^[a-zA-Z0-9_-]+$")
_BACKUP_NAME = re.compile(r"^clinux_(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})_.*\.sql$", re.IGNORECASE)


def backup_sort_key(item: dict) -> tuple:
    """Prioriza fecha/hora en nombre, con modifiedTime como desempate."""
    name = str(item.get("name", ""))
    match = _BACKUP_NAME.fullmatch(name)
    if match:
        try:
            date = datetime.strptime(f"{match.group(1)} {match.group(2)}:{match.group(3)}", "%Y-%m-%d %H:%M")
            return (1, date.isoformat(), str(item.get("modifiedTime", "")), name)
        except ValueError:
            pass
    return (0, str(item.get("modifiedTime", "")), "", name)


def choose_latest(files: list[dict]) -> dict:
    sql = [f for f in files if str(f.get("name", "")).lower().endswith(".sql")]
    if not sql:
        raise ValueError("No se encontraron archivos .sql en la carpeta compartida")
    return max(sql, key=backup_sort_key)


def list_folder_files(service, folder_id: str) -> list[dict]:
    if not _FOLDER_ID.fullmatch(folder_id):
        raise ValueError("ID de carpeta inválido")
    files = []
    page_token = None
    while True:
        response = service.files().list(
            q=f"'{folder_id}' in parents and trashed = false",
            fields="nextPageToken,files(id,name,mimeType,size,modifiedTime)",
            pageSize=1000,
            pageToken=page_token,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return files


def assert_mysql_dump(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValueError("El respaldo descargado está vacío")
    with path.open("rb") as fh:
        first = fh.read(500)
        if b"-- MySQL dump" not in first:
            raise ValueError("El archivo no tiene el encabezado esperado de un respaldo MySQL")
        fh.seek(max(0, path.stat().st_size - 500))
        if b"-- Dump completed on " not in fh.read():
            raise ValueError("La descarga podría estar incompleta")


def download_latest(folder_id: str, output: str | Path) -> None:
    import google.auth
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    files = list_folder_files(service, folder_id)
    latest = choose_latest(files)
    if not latest.get("id"):
        raise ValueError("El respaldo no tiene ID de Drive")

    dest = Path(output)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    if tmp.exists():
        tmp.unlink()
    try:
        request = service.files().get_media(fileId=latest["id"])
        with tmp.open("wb") as stream:
            os.chmod(tmp, 0o600)
            downloader = MediaIoBaseDownload(stream, request, chunksize=4 * 1024 * 1024)
            finished = False
            while not finished:
                _status, finished = downloader.next_chunk(num_retries=3)
        assert_mysql_dump(tmp)
        os.replace(tmp, dest)
        os.chmod(dest, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()
    print("Respaldo más reciente descargado y validado (sin publicar su contenido).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    download_latest(args.folder_id, args.output)


if __name__ == "__main__":
    main()
