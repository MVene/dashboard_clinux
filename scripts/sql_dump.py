"""Extracción selectiva de un respaldo MySQL de Nacional Sistema.

No ejecuta el SQL ni restaura tablas en la base del negocio.
Solo interpreta INSERTs de tablas aprobadas y columnas necesarias.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator
import pandas as pd

COLUMNS = {
    'vta_comprobante': ['tipo', 'comprobante', 'cliente', 'fecha', 'anulado', 'total', 'neto', 'ganancia$', 'lista', 'estado', 'cantidad', 'cobrado', 'resultado', 'iva', 'ajuste', 'visible'],
    'vta_comprobante_item': ['tipo', 'comprobante', 'linea', 'item', 'descripcion', 'cantidad', 'importe', 'ganancia$', 'anulado', 'precio', 'iva'],
    'vta_tipo_comprobante': ['id', 'descripcion', 'documento', 'saldo'],
    'vta_cliente': ['id', 'razon_social', 'nombre_comercial', 'grupo', 'lista'],
    'stk_item': ['id', 'descripcion', 'grupo', 'subgrupo', 'stock_minimo', 'punto_pedido'],
    'stk_existencia': ['item', 'cantidad', 'deposito'],
    'stk_lista': ['id', 'descripcion'],
    'stk_grupo': ['grupo'],
    'cmp_comprobante': ['tipo', 'comprobante', 'fecha', 'anulado', 'total'],
    'fnd_caja_diaria': ['id', 'apertura', 'clausura', 'ventas', 'compras', 'salidas'],
}

# MySQL escaped string encoding per mysqldump; decode only selected fields.
MYSQL_ESCAPE = {ord('0'): b'\x00', ord('n'): b'\n', ord('r'): b'\r', ord('t'): b'\t',
                ord('b'): b'\b', ord('Z'): b'\x1a'}


def decode_token(token: bytes, quoted: bool):
    if not quoted:
        token = token.strip()
        if token == b'NULL':
            return None
        if token.startswith(b'0x'):
            return token.decode('ascii', errors='replace')
        return token.decode('ascii', errors='replace')
    try:
        return token.decode('utf-8')
    except UnicodeDecodeError:
        return token.decode('latin1')


def parse_values(src: bytes) -> Iterator[list]:
    """Interpret MySQL VALUES tuples, including commas/parentheses in quoted text."""
    row = None
    token = bytearray()
    quoted = False
    in_quote = False
    escaped = False
    for b in src:
        if row is None:
            if b == 40:  # (
                row = []
                token = bytearray()
                quoted = False
            continue
        if in_quote:
            if escaped:
                token.extend(MYSQL_ESCAPE.get(b, bytes([b])))
                escaped = False
            elif b == 92:  # backslash
                escaped = True
            elif b == 39:  # closing apostrophe
                in_quote = False
            else:
                token.append(b)
        else:
            if b == 39:  # opening apostrophe
                quoted = True
                in_quote = True
            elif b == 44:  # comma
                row.append(decode_token(bytes(token), quoted))
                token = bytearray()
                quoted = False
            elif b == 41:  # closing parenthesis
                row.append(decode_token(bytes(token), quoted))
                yield row
                row = None
                token = bytearray()
                quoted = False
            elif b not in (9, 10, 13) or token:
                token.append(b)
    if row is not None or in_quote:
        raise ValueError('VALUES SQL incompletos, respaldo posiblemente truncado')


def read_tables(path: str | Path) -> dict[str, pd.DataFrame]:
    p = Path(path)
    # Prevent accepting random incomplete files.
    if not p.is_file() or p.stat().st_size < 2000:
        raise ValueError('No se encontró un respaldo válido')
    raw = p.read_bytes()
    if b'-- MySQL dump' not in raw[:400] or b'-- Dump completed on ' not in raw[-500:]:
        raise ValueError('El respaldo no parece ser un dump MySQL completo')

    selected: dict[str, list] = {name: [] for name in COLUMNS}
    schema: dict[str, list[str]] = {}
    for match in re.finditer(rb'CREATE TABLE `([^`]+)` \((.*?)\) ENGINE=', raw, flags=re.S):
        table = match.group(1).decode('ascii', errors='replace')
        if table in COLUMNS:
            schema[table] = [x.decode('utf-8') for x in re.findall(rb'(?m)^  `([^`]+)` ', match.group(2))]
    lookup = {}
    for table, columns in COLUMNS.items():
        if table in schema:
            lookup[table] = [(name, schema[table].index(name)) for name in columns if name in schema[table]]

    for line in raw.splitlines():
        if not line.startswith(b'INSERT INTO `'):
            continue
        mat = re.match(rb'^INSERT INTO `([^`]+)` VALUES ', line)
        if not mat:
            continue
        table = mat.group(1).decode('ascii', errors='replace')
        if table not in lookup:
            continue
        vals = line[mat.end():].rstrip()
        if not vals.endswith(b';'):
            raise ValueError(f'Sentencia INSERT incompleta: {table}')
        for row in parse_values(vals[:-1]):
            expected = len(schema[table])
            if len(row) != expected:
                raise ValueError(f'Cantidad de columnas incorrecta en {table}: {len(row)} != {expected}')
            selected[table].append({name: row[i] for name, i in lookup[table]})

    tables = {name: pd.DataFrame(rows, columns=COLUMNS[name]) for name, rows in selected.items()}
    # Subset of the source must exist for this dashboard to make sense.
    for key in ('vta_comprobante','vta_comprobante_item', 'stk_item','vta_cliente'):
        if key not in schema:
            raise ValueError(f'Falta la tabla requerida: {key}')
    return tables
