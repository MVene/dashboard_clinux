"""Clinux: respaldo MySQL -> indicadores -> PostgreSQL para Grafana.

Uso:
    python -m scripts.etl --file /ruta/respaldo.sql --dry-run
    python -m scripts.etl  # descargas desde Drive con rclone; escribe PostgreSQL

Nunca ejecuta SQL del respaldo; extrae tablas selectivas con parser de solo lectura.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from .drive_sync import sync_latest
from .metrics import get_items, get_sales, monthly_growth_equivalent, mark_wholesale
from .sql_dump import read_tables

# Incrementar al cambiar reglas de cálculo, para reprocesar el mismo respaldo.
ETL_RULES_VERSION = "v3-cliente-identificado-ticket-venta"


TABLES_DDL = [
    """CREATE TABLE IF NOT EXISTS clinux_ventas_diarias (
        dia DATE NOT NULL, ventas NUMERIC(19,2), comprobantes BIGINT,
        ganancia_registrada NUMERIC(19,2))""",
    """CREATE TABLE IF NOT EXISTS clinux_ventas_mensuales (
        mes DATE NOT NULL, ventas NUMERIC(19,2), comprobantes BIGINT,
        ganancia_registrada NUMERIC(19,2))""",
    """CREATE TABLE IF NOT EXISTS clinux_productos_diarios (
        dia DATE NOT NULL, item TEXT, producto TEXT, unidades NUMERIC(19,3),
        facturacion NUMERIC(19,2), ganancia_registrada NUMERIC(19,2))""",
    """CREATE TABLE IF NOT EXISTS clinux_clientes_diarios (
        dia DATE NOT NULL, cliente TEXT, nombre_cliente TEXT, mayorista BOOLEAN,
        ventas NUMERIC(19,2), comprobantes BIGINT)""",
    """CREATE TABLE IF NOT EXISTS clinux_canales_mensuales (
        mes DATE NOT NULL, canal TEXT, ventas NUMERIC(19,2), comprobantes BIGINT)""",
    """CREATE TABLE IF NOT EXISTS clinux_stock (
        item TEXT, producto TEXT, existencia NUMERIC(19,3),
        umbral_alerta NUMERIC(19,3), bajo_umbral BOOLEAN)""",
    """CREATE TABLE IF NOT EXISTS clinux_resumen (
        fecha_ultima_venta TIMESTAMPTZ, ventas_mes_actual NUMERIC(19,2),
        ventas_mes_previo_equivalente NUMERIC(19,2), crecimiento_pct NUMERIC(12,3),
        ganancia_mes_actual_registrada NUMERIC(19,2),
        cobertura_ganancia_pct NUMERIC(9,2), comprobantes_mes_actual BIGINT,
        ventas_mayoristas_mes_actual NUMERIC(19,2))""",
    """CREATE TABLE IF NOT EXISTS clinux_actualizacion (
        fecha_actualizacion TIMESTAMPTZ, respaldo_nombre TEXT,
        respaldo_sha256 TEXT, fecha_ultima_venta TIMESTAMPTZ)""",
]
TABLES = [
    "clinux_ventas_diarias", "clinux_ventas_mensuales", "clinux_productos_diarios",
    "clinux_clientes_diarios", "clinux_canales_mensuales", "clinux_stock",
    "clinux_resumen", "clinux_actualizacion",
]
INDEXES = [
    'CREATE INDEX IF NOT EXISTS clinux_ventas_diarias_dia ON clinux_ventas_diarias (dia)',
    'CREATE INDEX IF NOT EXISTS clinux_ventas_mensuales_mes ON clinux_ventas_mensuales (mes)',
    'CREATE INDEX IF NOT EXISTS clinux_productos_diarios_dia ON clinux_productos_diarios (dia)',
    'CREATE INDEX IF NOT EXISTS clinux_clientes_diarios_dia ON clinux_clientes_diarios (dia)',
    'CREATE INDEX IF NOT EXISTS clinux_canales_mensuales_mes ON clinux_canales_mensuales (mes)',
]


def env_values(name: str, default: str) -> set[str]:
    return {s.strip().upper() for s in (os.getenv(name) or default).split(',') if s.strip()}


def frame_num(df, cols):
    for col in cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df


def create_indicators(path: Path) -> dict[str, pd.DataFrame]:
    data = read_tables(path)
    # Solo documentos de venta: excluye presupuestos y remitos.
    sales = get_sales(data, tipos=('FC', 'FN', 'FX', 'NC', 'ND'))
    if sales.empty:
        raise ValueError('No hay comprobantes válidos para calcular indicadores')
    sales['dia'] = sales['fecha'].dt.date
    sales['mes_fecha'] = sales['fecha'].dt.to_period('M').dt.to_timestamp().dt.date
    # Regla comercial Clinux: nombre/ID de cliente distinto de CF -> mayorista;
    # Consumidor Final o cliente ausente -> minorista.
    # La regla no usa el tipo de comprobante: FC y FX aparecen en ambos canales.
    sales = mark_wholesale(sales)
    sales['canal'] = sales['mayorista'].map({True: 'Mayoristas', False: 'Minoristas'})
    sales['ticket_venta'] = sales['tipo'].isin(('FC', 'FN', 'FX')).astype(int)
    sales['cliente_id'] = sales['cliente'].fillna('').astype(str)
    sales['nombre_cliente'] = sales['nombre_cliente'].fillna('Sin identificar').astype(str)

    daily = sales.groupby('dia', as_index=False).agg(
        ventas=('ventas_netas','sum'), comprobantes=('ticket_venta','sum'),
        ganancia_registrada=('ganancia_registrada','sum'))
    monthly = sales.groupby('mes_fecha', as_index=False).agg(
        ventas=('ventas_netas','sum'), comprobantes=('ticket_venta','sum'),
        ganancia_registrada=('ganancia_registrada','sum'))
    monthly.rename(columns={'mes_fecha':'mes'}, inplace=True)

    items = get_items(data, sales)
    items['dia'] = items['fecha'].dt.date
    items['item'] = items['item'].fillna('SIN_CODIGO').astype(str)
    items['nombre_producto'] = items['nombre_producto'].fillna('Sin descripción').astype(str)
    product_daily = items.groupby(['dia','item','nombre_producto'], as_index=False).agg(
        unidades=('unidades','sum'), facturacion=('importe_linea','sum'),
        ganancia_registrada=('ganancia_linea','sum'))
    product_daily.rename(columns={'nombre_producto':'producto'},inplace=True)

    client_daily = sales.groupby(['dia','cliente_id','nombre_cliente','mayorista'], as_index=False).agg(
        ventas=('ventas_netas','sum'), comprobantes=('ticket_venta','sum'))
    client_daily.rename(columns={'cliente_id':'cliente'},inplace=True)
    channel_monthly = sales.groupby(['mes_fecha','canal'],as_index=False).agg(
        ventas=('ventas_netas','sum'), comprobantes=('ticket_venta','sum'))
    channel_monthly.rename(columns={'mes_fecha':'mes'},inplace=True)

    # El respaldo de ejemplo no registra mínimos de stock en las columnas consultadas.
    # Por eso usamos un umbral visual CONFIGURABLE: no es un stock mínimo real.
    threshold = float((os.getenv('STOCK_ALERT_THRESHOLD') or '10'))
    st = data['stk_existencia'][['item','cantidad']].copy()
    st['cantidad'] = pd.to_numeric(st['cantidad'],errors='coerce').fillna(0)
    st = st.groupby('item',as_index=False)['cantidad'].sum()
    prod = data['stk_item'][['id','descripcion']].copy().rename(columns={'id':'item','descripcion':'producto'})
    stock = prod.merge(st,on='item',how='left')
    stock['existencia'] = stock['cantidad'].fillna(0)
    stock['umbral_alerta'] = threshold
    stock['bajo_umbral'] = stock['existencia'] < threshold
    stock = stock[['item','producto','existencia','umbral_alerta','bajo_umbral']]

    equivalent = monthly_growth_equivalent(sales)
    current_month = sales['fecha'].max().to_period('M')
    smonth = sales[sales['fecha'].dt.to_period('M') == current_month]
    kpis = pd.DataFrame([{
        'fecha_ultima_venta': equivalent['fecha'].to_pydatetime(),
        'ventas_mes_actual': float(equivalent['actual']),
        'ventas_mes_previo_equivalente':float(equivalent['anterior']),
        'crecimiento_pct':equivalent['cambio'],
        'ganancia_mes_actual_registrada':float(smonth['ganancia_registrada'].sum()),
        'cobertura_ganancia_pct':float(smonth['ganancia_registrada'].notna().mean()*100),
        'comprobantes_mes_actual':int(smonth['ticket_venta'].sum()),
        'ventas_mayoristas_mes_actual':float(smonth.loc[smonth['mayorista'],'ventas_netas'].sum()),
    }])
    # Datetime timezone: fecha venta es local sin timezone en el sistema; se explicita -03:00.
    kpis['fecha_ultima_venta'] = pd.to_datetime(kpis['fecha_ultima_venta']).dt.tz_localize('America/Argentina/Cordoba')

    sha = hashlib.sha256(ETL_RULES_VERSION.encode() + b"\n" + path.read_bytes()).hexdigest()
    last_sale = kpis.iloc[0]['fecha_ultima_venta']
    source = pd.DataFrame([{
        'fecha_actualizacion': datetime.now(timezone.utc),
        'respaldo_nombre':path.name,
        'respaldo_sha256':sha,
        'fecha_ultima_venta':last_sale,
    }])
    return {
        'clinux_ventas_diarias': daily,
        'clinux_ventas_mensuales': monthly,
        'clinux_productos_diarios': product_daily,
        'clinux_clientes_diarios': client_daily,
        'clinux_canales_mensuales': channel_monthly,
        'clinux_stock': stock,
        'clinux_resumen': kpis,
        'clinux_actualizacion':source,
    }


def normalized_db_url(value: str) -> str:
    if value.startswith('postgresql://'):
        return value.replace('postgresql://','postgresql+psycopg://',1)
    if value.startswith('postgres://'):
        return value.replace('postgres://','postgresql+psycopg://',1)
    return value


def write_postgresql(data: dict[str,pd.DataFrame], url: str) -> str:
    if not url:
        raise ValueError('Falta DATABASE_URL en Secrets')
    engine = create_engine(normalized_db_url(url), pool_pre_ping=True, connect_args={'connect_timeout':20})
    try:
        with engine.begin() as conn:
            for statement in TABLES_DDL:
                conn.execute(text(statement))
            # Evita reescrituras innecesarias si el respaldo no cambió.
            current = conn.execute(text('SELECT respaldo_sha256 FROM clinux_actualizacion LIMIT 1')).scalar()
            new = str(data['clinux_actualizacion'].iloc[0]['respaldo_sha256'])
            if current == new:
                return 'sin cambios: el respaldo ya estaba procesado'
            for name in TABLES:
                conn.execute(text(f'DELETE FROM {name}'))  # Nombres constantes propios.
            for name in TABLES:
                data[name].to_sql(name, conn, if_exists='append',index=False,chunksize=500,method='multi')
            for index in INDEXES:
                conn.execute(text(index))
        return 'datos actualizados correctamente'
    finally:
        engine.dispose()


def main() -> None:
    parser=argparse.ArgumentParser(description='Pipeline Clinux para Grafana')
    parser.add_argument('--file',help='SQL local, para desarrollo/pruebas')
    parser.add_argument('--dry-run',action='store_true',help='No escribe en PostgreSQL')
    args=parser.parse_args()
    if args.file:
        path=Path(args.file)
    else:
        folder=os.getenv('DRIVE_FOLDER','')
        if not folder:
            raise ValueError('Falta DRIVE_FOLDER, p.ej. gdrive:Clinux/Respaldos')
        path, _, _ = sync_latest(folder, '/tmp/clinux_respaldo.sql')
    frames=create_indicators(path)
    if args.dry_run:
        print(json.dumps({
            'modo':'prueba local sin subir datos',
            'tablas_publicacion':{k:len(v) for k,v in frames.items()},
            'fecha_ultima_venta':str(frames['clinux_resumen'].iloc[0]['fecha_ultima_venta']),
            'cobertura_ganancia_pct':round(float(frames['clinux_resumen'].iloc[0]['cobertura_ganancia_pct']),1),
            'nota':'No se imprimen clientes ni importes en los logs',
        },ensure_ascii=False,indent=2))
    else:
        print(write_postgresql(frames,os.getenv('DATABASE_URL','')))

if __name__=='__main__':
    main()
