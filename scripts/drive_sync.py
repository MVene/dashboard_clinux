"""Lee el archivo SQL más reciente de una carpeta privada de Drive vía rclone.

Requiere que el dueño configure rclone OAuth. No hace público el archivo ni
necesita acceso a Nacional Sistema. Nunca ejecuta el contenido SQL.
"""
from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


def _command(cmd: list[str], timeout=120):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        # Don't display credentials or dump content in error messages.
        msg = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'error desconocido'
        raise RuntimeError(f'Error de sincronización con Drive: {msg[:250]}')
    return result.stdout


def sync_latest(remote_folder: str, dest: str | Path) -> tuple[Path, bool, str]:
    """Descarga el .sql de fecha más reciente si cambió. Devuelve ruta, actualizado, nombre."""
    if not remote_folder or ':' not in remote_folder:
        raise ValueError('Configurá CLINUX_DRIVE_REMOTE con la carpeta rclone (ej: gdrive:Clinux/Respaldos)')
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    entries = json.loads(_command(['rclone','lsjson',remote_folder,'--files-only','--max-depth','1']))
    files = [f for f in entries if not f.get('IsDir',False) and str(f.get('Name','')).lower().endswith('.sql')]
    if not files:
        raise ValueError('No encontré archivos .sql en la carpeta indicada de Drive')
    latest = max(files, key=lambda f: (f.get('ModTime',''),f.get('Name','')))
    manifest = dest.with_suffix('.source.json')
    stamp = {'name':latest['Name'], 'modified':latest.get('ModTime'), 'size':latest.get('Size')}
    if dest.exists() and manifest.exists() and json.loads(manifest.read_text('utf-8')) == stamp:
        return dest, False, latest['Name']
    source = remote_folder.rstrip('/')+'/'+latest['Name']
    tmp = dest.with_suffix('.partial')
    if tmp.exists(): tmp.unlink()
    try:
        _command(['rclone','copyto',source,str(tmp)])
        # Verify complete MySQL dump before replacing last working backup.
        with tmp.open('rb') as fh:
            first=fh.read(500)
            if b'-- MySQL dump' not in first:
                raise ValueError('Drive contiene un archivo que no es un respaldo MySQL esperado')
            fh.seek(max(0,tmp.stat().st_size-500))
            if b'-- Dump completed on ' not in fh.read():
                raise ValueError('La descarga parece incompleta; se conservó el respaldo anterior')
        os.chmod(tmp,0o600)
        os.replace(tmp,dest)
        manifest.write_text(json.dumps(stamp,ensure_ascii=False), encoding='utf-8')
        os.chmod(manifest,0o600)
    finally:
        if tmp.exists():tmp.unlink()
    return dest, True, latest['Name']
