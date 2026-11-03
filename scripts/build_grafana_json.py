"""Genera el dashboard ejecutivo v4 de Clinux para Grafana con PostgreSQL.

Ejecutar desde la raíz del repositorio:
    python -m scripts.build_grafana_json
"""
from __future__ import annotations
import json
from pathlib import Path

SOURCE = {'type': 'postgres', 'uid': '${DS_CLINUX}'}
ARS = 'currency:financial:$'
TEAL = '#28B9B3'
GREEN = '#70C788'
BLUE = '#67A8F4'


def query(sql: str, fmt: str = 'table') -> dict:
    return {'refId': 'A', 'datasource': SOURCE, 'rawSql': sql, 'format': fmt, 'editorMode': 'code'}


def make_panel(pid: int, title: str, kind: str, grid: tuple[int, int, int, int],
               sql: str, *, fmt: str = 'table', unit: str = 'none', decimals: int | None = None,
               description: str = '', options: dict | None = None,
               overrides: list | None = None, color: str = TEAL) -> dict:
    x, y, w, h = grid
    default_field = {
        'color': {'mode': 'fixed', 'fixedColor': color},
        'unit': unit,
        'custom': {},
    }
    if decimals is not None:
        default_field['decimals'] = decimals
    base = {
        'id': pid, 'title': title, 'type': kind,
        'gridPos': {'x': x, 'y': y, 'w': w, 'h': h},
        'description': description,
        'datasource': SOURCE,
        'targets': [query(sql, fmt)],
        'fieldConfig': {'defaults': default_field, 'overrides': overrides or []},
        'options': options or {},
    }
    if kind == 'stat':
        base['options'] = {
            'reduceOptions': {'values': False, 'calcs': ['lastNotNull'], 'fields': ''},
            'orientation': 'auto', 'textMode': 'value', 'colorMode': 'value',
            'graphMode': 'none', 'justifyMode': 'auto',
        }
    return base


def field_override(name: str, properties: list[dict]) -> dict:
    return {'matcher': {'id': 'byName', 'options': name}, 'properties': properties}


channel_summary = '''
SELECT COALESCE(SUM(ventas), 0) AS "Total"
FROM clinux_clientes_diarios
WHERE mayorista = {channel}
  AND $__timeFilter(dia::timestamp)
'''

profit_channel = '''
SELECT SUM(ganancia_registrada) AS "Ganancia registrada"
FROM clinux_clientes_diarios
WHERE mayorista = {channel}
  AND $__timeFilter(dia::timestamp)
'''

# Comparación del intervalo elegido contra el período inmediatamente previo
# con exactamente la misma cantidad de días, sin depender de un KPI fijo.
growth = '''
WITH limites AS (
    SELECT ($__timeFrom())::date AS desde,
           ($__timeTo())::date AS hasta
), totales AS (
    SELECT
        SUM(d.ventas) FILTER (
            WHERE d.dia BETWEEN l.desde AND l.hasta
        ) AS actual,
        SUM(d.ventas) FILTER (
            WHERE d.dia >= l.desde - (l.hasta - l.desde + 1)
              AND d.dia < l.desde
        ) AS anterior
    FROM clinux_ventas_diarias d CROSS JOIN limites l
)
SELECT CASE WHEN anterior > 0
       THEN ROUND((actual - anterior) * 100.0 / anterior, 1)
       ELSE NULL END AS "Crecimiento (%)"
FROM totales
'''

monthly = '''
SELECT date_trunc('month', dia::timestamp) AS time,
       SUM(ventas)::double precision AS "Ventas",
       SUM(ganancia_registrada)::double precision AS "Ganancia registrada"
FROM clinux_ventas_diarias
WHERE $__timeFilter(dia::timestamp)
GROUP BY 1 ORDER BY 1
'''

daily = '''
SELECT dia::timestamp AS time,
       ventas::double precision AS "Ventas"
FROM clinux_ventas_diarias
WHERE $__timeFilter(dia::timestamp)
ORDER BY time
'''

customers = '''
SELECT nombre_cliente AS "Cliente mayorista",
       SUM(comprobantes)::bigint AS "Tickets",
       ROUND(SUM(ventas)::numeric, 2) AS "Compras netas (ARS)",
       MAX(dia) AS "Última compra"
FROM clinux_clientes_diarios
WHERE mayorista = TRUE
  AND $__timeFilter(dia::timestamp)
GROUP BY cliente, nombre_cliente
ORDER BY "Compras netas (ARS)" DESC
LIMIT 20
'''

products = '''
SELECT producto AS "Producto",
       ROUND(SUM(unidades)::numeric, 1) AS "Unidades"
FROM clinux_productos_diarios
WHERE $__timeFilter(dia::timestamp)
GROUP BY item, producto
HAVING SUM(unidades) > 0
ORDER BY "Unidades" DESC
LIMIT 10
'''

panels = [
    make_panel(1, 'Ventas mayoristas · período', 'stat', (0, 0, 8, 4),
        channel_summary.format(channel='TRUE'), unit=ARS, decimals=0, color=TEAL,
        description='Facturación neta de comprobantes asociados a clientes identificados, incluyendo devoluciones.'),
    make_panel(2, 'Ventas minoristas · período', 'stat', (8, 0, 8, 4),
        channel_summary.format(channel='FALSE'), unit=ARS, decimals=0, color=BLUE,
        description='Facturación neta a Consumidor Final o sin cliente identificado, incluyendo devoluciones.'),
    make_panel(3, 'Tickets totales · período', 'stat', (16, 0, 8, 4),
        'SELECT COALESCE(SUM(comprobantes), 0) AS "Tickets" FROM clinux_ventas_diarias WHERE $__timeFilter(dia::timestamp)',
        unit='none', decimals=0, color=GREEN,
        description='Cuenta facturas y tickets; no agrega notas de crédito como tickets nuevos.'),
    make_panel(4, 'Crecimiento vs. período anterior', 'stat', (16, 4, 8, 4),
        growth, unit='percent', decimals=1, color=GREEN,
        description='Crecimiento de facturación neta contra el intervalo inmediatamente anterior de igual cantidad de días. No equivale necesariamente a crecimiento real por inflación.'),
    make_panel(5, 'Ganancia registrada · mayoristas', 'stat', (0, 4, 8, 4),
        profit_channel.format(channel='TRUE'), unit=ARS, decimals=0, color=TEAL,
        description='Dato parcial de ganancia asociado a comprobantes mayoristas. No incluye necesariamente todos los costos ni gastos: NO es ganancia neta.'),
    make_panel(6, 'Ganancia registrada · minoristas', 'stat', (8, 4, 8, 4),
        profit_channel.format(channel='FALSE'), unit=ARS, decimals=0, color=BLUE,
        description='Dato parcial de ganancia asociado a comprobantes minoristas. No incluye necesariamente todos los costos ni gastos: NO es ganancia neta.'),
    make_panel(7, 'Crecimiento y rendimiento · evolución mensual', 'timeseries', (0, 8, 24, 9),
        monthly, fmt='time_series', unit=ARS, decimals=0,
        description='Ventas y ganancia registrada por mes, sumando únicamente los días incluidos en el período seleccionado. Los meses extremos pueden ser parciales.',
        options={
            'tooltip': {'mode': 'multi', 'sort': 'desc'},
            'legend': {'displayMode': 'list', 'placement': 'bottom', 'showLegend': True},
        },
        overrides=[
            field_override('Ventas', [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': TEAL}}]),
            field_override('Ganancia registrada', [{'id': 'color', 'value': {'mode': 'fixed', 'fixedColor': GREEN}}]),
        ]),
    make_panel(8, 'Ventas diarias', 'timeseries', (0, 17, 24, 9),
        daily, fmt='time_series', unit=ARS, decimals=0, color=TEAL,
        description='Ventas netas por día para el período seleccionado. El origen es el último respaldo disponible en Google Drive.',
        options={'tooltip': {'mode': 'single', 'sort': 'none'},
                 'legend': {'displayMode': 'list', 'placement': 'bottom', 'showLegend': False}}),
    make_panel(9, 'Detalle de clientes mayoristas', 'table', (0, 26, 12, 11),
        customers, fmt='table', unit='none',
        description='Hasta 20 clientes por monto comprado neto en el período. Datos comerciales sensibles: compartir solo con usuarios autorizados.',
        options={'showHeader': True, 'cellHeight': 'sm', 'footer': {'show': False}},
        overrides=[field_override('Compras netas (ARS)', [
            {'id': 'unit', 'value': ARS}, {'id': 'decimals', 'value': 0}])]),
    make_panel(10, 'Top 10 productos más vendidos · unidades', 'barchart', (12, 26, 12, 11),
        products, fmt='table', unit='none', decimals=1, color=TEAL,
        description='Ranking por cantidad de unidades netas vendidas durante el período; las devoluciones restan.',
        options={
            'orientation': 'horizontal', 'xField': 'Producto', 'showValue': 'always',
            'xTickLabelMaxLength': 42, 'xTickLabelSpacing': 0,
            'legend': {'displayMode': 'list', 'placement': 'bottom', 'showLegend': False},
            'tooltip': {'mode': 'single', 'sort': 'none'},
        }),
]

# La variable se selecciona una sola vez al importar el dashboard.
dashboard = {
    '__inputs': [{
        'name': 'DS_CLINUX', 'label': 'PostgreSQL Clinux',
        'description': 'Seleccioná la fuente de datos PostgreSQL de Clinux',
        'type': 'datasource', 'pluginId': 'postgres', 'pluginName': 'PostgreSQL',
    }],
    '__requires': [
        {'type': 'datasource', 'id': 'postgres', 'name': 'PostgreSQL', 'version': '1.0.0'},
        {'type': 'panel', 'id': 'stat', 'name': 'Stat', 'version': ''},
    ],
    'id': None, 'uid': 'clinux-rendimiento-v4',
    'title': 'Clinux | Crecimiento y rendimiento comercial (v4)',
    'description': 'Panel comercial de Clinux. Ventas nominales en ARS y ganancias registradas parciales, NO ganancias netas.',
    'tags': ['clinux', 'gerencia', 'ventas', 'rendimiento'],
    'timezone': 'America/Argentina/Cordoba',
    'schemaVersion': 39, 'version': 4,
    'refresh': '1h',
    'time': {'from': 'now-180d', 'to': 'now'},
    'timepicker': {'refresh_intervals': ['15m', '1h', '6h']},
    'templating': {'list': [{
        'name': 'DS_CLINUX', 'label': 'Base de datos Clinux',
        'type': 'datasource', 'query': 'postgres',
        'current': {'text': 'grafana-postgresql-datasource', 'value': 'dg30kcghd1hj4c'},
        'refresh': 1, 'options': [], 'hide': 0,
        'multi': False, 'includeAll': False,
    }]},
    'panels': panels, 'editable': True,
    'annotations': {'list': []}, 'graphTooltip': 0, 'style': 'dark',
}

if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'grafana' / 'dashboard_clinux.json'
    output.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
