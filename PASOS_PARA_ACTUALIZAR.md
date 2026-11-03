# Corrección v3 del dashboard Clinux

Esta carpeta contiene **solo los archivos corregidos** para reemplazar en el repositorio privado de GitHub. **No incluye respaldos ni credenciales.**

## Qué cambia

1. `scripts/metrics.py`: mayorista si la factura está asociada a un cliente distinto de `CF` / Consumidor Final. Facturas FC y FX pueden incluir ambos canales; el cliente identificado prevalece. Notas de crédito descuentan su canal.
2. `scripts/etl.py`: cuenta tickets de venta (FC, FN, FX) y no cuenta notas de crédito como tickets; sigue incluyendo su efecto monetario. Incrementa versión para **reprocesar el mismo respaldo SQL**, aunque no haya cambiado.
3. `grafana/dashboard_clinux.json`: unidades monetarias válidas, dona con dos porciones y top productos horizontal; títulos más claros.
4. `scripts/build_grafana_json.py`: fuente reproducible del dashboard JSON.
5. `tests/test_reglas.py`: pruebas de la regla mayorista.

## En Linux (desde tu repositorio local)

Copiar estas carpetas/archivos **encima** de los del repositorio (sin borrar los demás). Luego:

```bash
python -m unittest discover -s tests -v
git add scripts/metrics.py scripts/etl.py scripts/build_grafana_json.py grafana/dashboard_clinux.json tests/test_reglas.py
git commit -m "Corrige mayoristas, tickets y visualizaciones"
git push origin main
```

### Reprocesar datos

GitHub → Actions → Actualizar dashboard Clinux → Run workflow → `main`. El paso deberá finalizar verde. No modificar secretos.

### Actualizar Grafana

Grafana → Dashboards → New → Import → cargar `grafana/dashboard_clinux.json` desde la carpeta local → elegir el datasource de PostgreSQL de Clinux en `DS_CLINUX`. Se crea un tablero **v3**, sin sobrescribir el anterior. Seleccionar `Last 6 months`, guardar, comprobar la dona y el ranking.

**Importante:** ganancias = dato registrado parcial, no ganancia neta comprobada. El umbral de stock es una visualización general; no reemplaza un stock mínimo real. Evitá hacer público el dashboard de datos comerciales.
