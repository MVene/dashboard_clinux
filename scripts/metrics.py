"""Métricas de Clinux a partir de tablas seleccionadas de una copia MySQL."""
from __future__ import annotations
import pandas as pd

VENTAS_DEFAULT = ('FC', 'FX', 'NC')  # Facturas, documentos de venta y notas de crédito


def numerics(df: pd.DataFrame, cols: tuple | list) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors='coerce')
    return out


def get_sales(tables: dict[str, pd.DataFrame], tipos=VENTAS_DEFAULT) -> pd.DataFrame:
    sales = numerics(tables['vta_comprobante'], ['total', 'neto', 'ganancia$', 'cantidad', 'iva'])
    sales['fecha'] = pd.to_datetime(sales['fecha'], errors='coerce')
    sales = sales[sales['tipo'].isin(tipos) & (sales['anulado'].fillna('0').astype(str) != '1') & sales['fecha'].notna()].copy()
    # sign comes from metadata of type, not guessed from the document number.
    docs = tables['vta_tipo_comprobante'].set_index('id')
    sign_by_tipo = {'SUMA': 1, 'RESTA': -1, 'NO_CALCULA': 0}
    sales['signo'] = sales['tipo'].map(docs['saldo']).map(sign_by_tipo).fillna(0)
    sales['ventas_netas'] = sales['total'].fillna(0) * sales['signo']
    sales['ganancia_registrada'] = sales['ganancia$'] * sales['signo']
    clients = tables['vta_cliente'][['id','razon_social','nombre_comercial','grupo']].copy()
    clients.columns = ['cliente', 'razon_social_cliente', 'nombre_comercial_cliente','grupo_cliente']
    sales = sales.merge(clients, on='cliente', how='left', validate='many_to_one')
    sales['nombre_cliente'] = sales['nombre_comercial_cliente'].fillna('').where(
        sales['nombre_comercial_cliente'].fillna('').ne(''),
        sales['razon_social_cliente'].fillna(''))
    sales['nombre_cliente'] = sales['nombre_cliente'].replace('', 'Sin identificar')
    sales['mes'] = sales['fecha'].dt.to_period('M').astype(str)
    return sales


def get_items(tables: dict[str, pd.DataFrame], sales: pd.DataFrame) -> pd.DataFrame:
    items = numerics(tables['vta_comprobante_item'],['cantidad','importe', 'ganancia$','precio'])
    items = items[items['anulado'].fillna('0').astype(str) != '1'].copy()
    keys = sales[['tipo','comprobante','fecha','mes','signo','lista']].drop_duplicates(['tipo','comprobante'])
    items = items.merge(keys,on=['tipo','comprobante'],how='inner',validate='many_to_one')
    items['unidades'] = items['cantidad'].fillna(0) * items['signo']
    items['importe_linea'] = items['importe'].fillna(0) * items['signo']
    items['ganancia_linea'] = items['ganancia$'] * items['signo']
    products = tables['stk_item'][['id','descripcion','grupo','subgrupo','stock_minimo']].copy().rename(
        columns={'id':'item','descripcion':'producto_catalogo'})
    items = items.merge(products,on='item',how='left',validate='many_to_one')
    items['nombre_producto'] = items['producto_catalogo'].fillna(items['descripcion']).fillna(items['item'])
    return items


def mark_wholesale(sales: pd.DataFrame, wholesale_lists=None, wholesale_groups=None) -> pd.DataFrame:
    """Regla Clinux: cliente nominal = mayorista; CF o ausente = minorista.

    Los parámetros obsoletos se aceptan para compatibilidad, pero se ignoran.
    """
    out = sales.copy()
    # La factura a nombre de un cliente identificado es mayorista.
    # CF y los comprobantes sin cliente identificado son minoristas.
    # FC/FX por sí solos no distinguen el canal en el respaldo de Clinux.
    cliente = out['cliente'].fillna('').astype(str).str.strip().str.upper()
    out['mayorista'] = ~cliente.isin({'', 'CF', 'CONSUMIDOR FINAL'})
    return out


def top_products(items: pd.DataFrame, by='unidades', limit=10) -> pd.DataFrame:
    out = items.groupby(['item','nombre_producto'],dropna=False).agg(
        unidades=('unidades','sum'), facturacion_lineas=('importe_linea','sum'),
        ganancia_registrada=('ganancia_linea','sum')).reset_index()
    out = out.sort_values(by, ascending=False).head(limit)
    return out


def monthly_sales(sales: pd.DataFrame) -> pd.DataFrame:
    return sales.groupby('mes',as_index=False).agg(
        ventas=('ventas_netas','sum'), comprobantes=('comprobante','count'),
        ganancia=('ganancia_registrada','sum'))


def coverage_profit(sales: pd.DataFrame) -> float:
    if sales.empty:
        return 0.0
    return float(sales['ganancia_registrada'].notna().mean())


def monthly_growth_equivalent(sales: pd.DataFrame):
    """Compare current latest month through latest day with same calendar days prior month."""
    if sales.empty:
        return None
    mx = sales['fecha'].max()
    this_month_start = mx.replace(day=1, hour=0,minute=0,second=0,microsecond=0)
    prev_month_start = this_month_start - pd.DateOffset(months=1)
    prev_end = (prev_month_start + pd.DateOffset(months=1) - pd.Timedelta(days=1)).day
    cutoff_day = min(mx.day,prev_end)
    current = sales[(sales['fecha']>=this_month_start)&(sales['fecha']<=mx)]['ventas_netas'].sum()
    previous = sales[(sales['fecha']>=prev_month_start)&(sales['fecha']<prev_month_start+pd.Timedelta(days=cutoff_day))]['ventas_netas'].sum()
    change = ((current / previous)-1)*100 if previous > 0 else None
    return {'fecha':mx,'actual':float(current),'anterior':float(previous),'cambio':change}
