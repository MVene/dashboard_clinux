"""Dashboard Grafana JSON importable, datasource PostgreSQL seleccionable en Import."""
from __future__ import annotations
import json
from pathlib import Path

DS={'type':'postgres','uid':'${DS_CLINUX}'}


def target(sql:str,ref='A',fmt='table'):
    return {'refId':ref,'datasource':DS, 'rawSql':sql,'format':fmt,'editorMode':'code'}


def panel(pid,title,panel_type,x,y,w,h,sql,fmt='table',unit=None,description=None,**kwargs):
    field = {'defaults':{'color':{'mode':'palette-classic'},'custom':{}},'overrides':[]}
    if unit:
        field['defaults']['unit']=unit
        if unit == 'currency:financial:$':
            field['defaults']['decimals']=0
    p={
        'id':pid,'title':title,'type':panel_type,
        'gridPos':{'x':x,'y':y,'w':w,'h':h},
        'datasource':DS,'targets':[target(sql,fmt=fmt)],
        'fieldConfig':field,
        'options':{},
    }
    if description:p['description']=description
    p.update(kwargs)
    return p

panels=[]
panels.append(panel(1,'Ventas del período','stat',0,0,6,4,
    'SELECT SUM(ventas) AS "Ventas" FROM clinux_ventas_diarias WHERE $__timeFilter(dia::timestamp)',unit='currency:financial:$',
    description='Ventas netas del período seleccionado, incluyendo notas de crédito. $ARS nominales.'))
panels.append(panel(2,'Ganancia registrada (parcial)','stat',6,0,6,4,
    'SELECT SUM(ganancia_registrada) AS "Ganancia registrada" FROM clinux_ventas_diarias WHERE $__timeFilter(dia::timestamp)',unit='currency:financial:$',
    description='Ganancia registrada por Nacional Sistema; NO incluye necesariamente todos los costos ni gastos y NO es ganancia neta.'))
panels.append(panel(3,'Tickets de venta del período','stat',12,0,6,4,
    'SELECT SUM(comprobantes) AS "Comprobantes" FROM clinux_ventas_diarias WHERE $__timeFilter(dia::timestamp)',unit='none'))
panels.append(panel(4,'Crecimiento último mes vs anterior*','stat',18,0,6,4,
    'SELECT crecimiento_pct AS "Crecimiento mensual" FROM clinux_resumen LIMIT 1',unit='percent',
    description='Último mes con datos hasta el mismo día del mes anterior. Este indicador no depende del filtro de fechas.'))
panels.append(panel(5,'Ventas diarias','timeseries',0,4,16,9,
    'SELECT dia::timestamp AS time, ventas AS "Ventas" FROM clinux_ventas_diarias WHERE $__timeFilter(dia::timestamp) ORDER BY 1',fmt='time_series',unit='currency:financial:$'))
panels.append(panel(6,'Participación mayorista vs minorista','piechart',16,4,8,9,
    '''SELECT COALESCE(SUM(ventas) FILTER (WHERE mayorista), 0) AS "Mayoristas",
             COALESCE(SUM(ventas) FILTER (WHERE NOT mayorista), 0) AS "Minoristas"
        FROM clinux_clientes_diarios WHERE $__timeFilter(dia::timestamp)''',
    options={'legend':{'displayMode':'table','placement':'right','showLegend':True},
             'pieType':'donut','displayLabels':['name','percent'],
             'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False}},
    description='Mayorista si el comprobante está asociado a un cliente identificado; CF o sin cliente es minorista. FC/FX no deciden por sí solas el canal. Las notas de crédito restan.'))
panels.append(panel(7,'Evolución mensual de ventas y ganancia registrada','timeseries',0,13,12,9,
    'SELECT mes::timestamp AS time, ventas AS "Ventas", ganancia_registrada AS "Ganancia registrada" FROM clinux_ventas_mensuales WHERE $__timeFilter(mes::timestamp) ORDER BY 1',fmt='time_series',unit='currency:financial:$',
    description='Ganancia registrada no equivale a ganancia neta.'))
panels.append(panel(8,'Top 10 productos por unidades','barchart',12,13,12,9,
    '''SELECT producto AS "Producto", ROUND(SUM(unidades)::numeric,2) AS "Unidades"
       FROM clinux_productos_diarios WHERE $__timeFilter(dia::timestamp)
       GROUP BY producto ORDER BY "Unidades" DESC LIMIT 10''',
    options={'orientation':'horizontal','xField':'Producto','showValue':'always',
             'xTickLabelMaxLength':40,'xTickLabelSpacing':0,'legend':{'showLegend':False},
             'tooltip':{'mode':'single','sort':'none'}},
    description='Unidades netas vendidas por artículo; con notas de crédito descontadas.'))
panels.append(panel(9,'Top clientes mayoristas','table',0,22,12,9,
    '''SELECT nombre_cliente AS "Cliente", COUNT(DISTINCT dia) AS "Días con compras",
       SUM(comprobantes) AS "Comprobantes", ROUND(SUM(ventas)::numeric,2) AS "Total ARS"
       FROM clinux_clientes_diarios
       WHERE mayorista AND $__timeFilter(dia::timestamp)
       GROUP BY cliente,nombre_cliente ORDER BY "Total ARS" DESC LIMIT 15''',
    description='Muestra información comercial sensible. Restringí acceso a quienes la necesiten.'))
panels.append(panel(10,'Stock por debajo del umbral configurable','table',12,22,12,9,
    '''SELECT producto AS "Producto", ROUND(existencia::numeric,2) AS "Existencias",
       ROUND(umbral_alerta::numeric,2) AS "Umbral de visualización"
       FROM clinux_stock WHERE bajo_umbral ORDER BY existencia ASC LIMIT 25''',
    description='El respaldo no trae stock mínimo cargado; se usa un umbral global configurable (ej.: 10). No es una recomendación de reposición.'))
panels.append(panel(11,'Facturación mayorista del último mes','stat',0,31,8,4,
    'SELECT ventas_mayoristas_mes_actual AS "Mayoristas" FROM clinux_resumen LIMIT 1',unit='currency:financial:$',
    description='Último mes disponible; no sigue el filtro global de fechas.'))
panels.append(panel(12,'Cobertura de ganancia registrada','stat',8,31,8,4,
    'SELECT cobertura_ganancia_pct AS "Cobertura" FROM clinux_resumen LIMIT 1',unit='percent',
    description='Porcentaje de comprobantes del último mes con campo de ganancia registrado.'))
panels.append(panel(13,'Última actualización disponible','table',16,31,8,4,
    "SELECT (fecha_actualizacion AT TIME ZONE 'America/Argentina/Cordoba') AS \"Sincronizado (Córdoba)\", (fecha_ultima_venta AT TIME ZONE 'America/Argentina/Cordoba') AS \"Última venta (Córdoba)\" FROM clinux_actualizacion LIMIT 1",
    description='La actualización depende de cuándo Nacional Sistema genere el respaldo y de que GitHub Actions se ejecute.'))

dashboard={
    '__inputs':[{'name':'DS_CLINUX','label':'PostgreSQL Clinux','description':'Seleccioná el datasource PostgreSQL conectado a la base en la nube','type':'datasource','pluginId':'postgres','pluginName':'PostgreSQL'}],
    '__requires':[{'type':'datasource','id':'postgres','name':'PostgreSQL','version':'1.0.0'},{'type':'panel','id':'stat','name':'Stat','version':''}],
    'id':None,'uid':'clinux-gerencia-v3','title':'Clinux | Gerencia: ventas y mayoristas (v3)',
    'description':'Panel gerencial sobre respaldo SQL de Nacional Sistema procesado por GitHub Actions; importes nominales en ARS, ganancias parciales.',
    'tags':['clinux','ventas','mayoristas','stock'],
    'timezone':'America/Argentina/Cordoba','schemaVersion':39,'version':3,
    'refresh':'1h','time':{'from':'now-180d','to':'now'},
    'timepicker':{'refresh_intervals':['5m','15m','1h']},
    'templating':{'list':[
        {'name':'DS_CLINUX','label':'PostgreSQL Clinux','type':'datasource','query':'postgres',
         'current':{'text':'grafana-postgresql-datasource','value':'dg30kcghd1hj4c'},
         'refresh':1,'options':[],'hide':0,'multi':False,'includeAll':False},
    ]},
    'panels':panels,'editable':True,
    'annotations':{'list':[]},
    'graphTooltip':0,'style':'dark',
}
output=Path(__file__).resolve().parents[1]/'grafana'/'dashboard_clinux.json'
output.write_text(json.dumps(dashboard,ensure_ascii=False,indent=2),encoding='utf-8')
print(output)
