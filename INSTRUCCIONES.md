# Dashboard Clinux · Crecimiento y rendimiento comercial (v4)

## Qué muestra

Exactamente 10 paneles, organizados en cuatro zonas:

- Fila de KPIs: venta mayorista del período, venta minorista del período, tickets del período.
- Fila de KPIs: ganancia registrada mayorista (parcial), ganancia registrada minorista (parcial), porcentaje de crecimiento vs. período anterior comparable.
- Tendencias: crecimiento y rendimiento mensual (ventas + ganancia registrada); ventas diarias.
- Detalle: principales clientes mayoristas y 10 productos más vendidos en unidades netas.

No contiene donut, ni stock, ni cobertura de ganancia ni indicadores que no solicitaste.

## Regla de clasificación

Cliente identificado (ID distinto de `CF` / `CONSUMIDOR FINAL`) = mayorista. Cliente CF o ausente = minorista. Un FC o FX puede tener un cliente nominal y se toma el cliente como criterio prioritario. Las notas de crédito restan importes. Esta es la regla utilizada en la versión v3 que veníamos trabajando; debe validarse con el negocio antes de tomar decisiones.

**Advertencia:** "Ganancia registrada" proviene del campo del respaldo de Nacional Sistema y puede ser incompleta. No debe interpretarse como ganancia neta (no incluye necesariamente gastos e impuestos). Los porcentajes sobre ARS nominales tampoco representan crecimiento descontada la inflación.

## 1. Actualizar el repositorio desde Linux

Usar la terminal:

```bash
cd ~/Escritorio/dashboard_clinux
unzip -o ~/Descargas/Clinux_dashboard_rendimiento_v4.zip
source .venv/bin/activate
python -m unittest discover -s tests -v
```

El resultado esperado es **OK**. Si no existe `.venv`, crear el entorno e instalar las dependencias del proyecto, como hicimos antes.

Luego:

```bash
git add scripts/etl.py scripts/metrics.py scripts/build_grafana_json.py \
  grafana/dashboard_clinux.json tests/test_dashboard_v4.py tests/test_reglas.py INSTRUCCIONES.md
git commit -m "Dashboard ejecutivo Clinux v4: ventas y ganancias por canal"
git push origin main
```

El ZIP contiene también `scripts/drive_sync.py`, `scripts/sql_dump.py` y `scripts/__init__.py` originales para que el proyecto pueda probarse aisladamente. No es necesario modificarlos; si Git no los marca como cambiados, está bien.

**No subir** SQL, `.env`, tokens, secretos, `.venv` ni archivos rclone.

## 2. Reprocesar en GitHub Actions

GitHub → Actions → **Actualizar dashboard Clinux** → **Run workflow** sobre `main`.

El ETL se identifica con una nueva versión de reglas (`v4-ganancias-por-canal`): vuelve a cargar los indicadores aunque la copia SQL más reciente no haya cambiado. Añade la columna `ganancia_registrada` a `clinux_clientes_diarios` si no existe, sin borrar la tabla. Los datos del dashboard anterior seguirán disponibles.

Esperar a que el workflow quede verde antes de usar los dos nuevos indicadores de ganancia.

## 3. Importar en Grafana

Grafana → Dashboards → **New → Import** → subir `grafana/dashboard_clinux.json`.

Al importar, seleccionar la fuente PostgreSQL de Neon, `grafana-postgresql-datasource`, para `DS_CLINUX`. Si aparece `No data`, arriba del dashboard verificar que **Base de datos Clinux** esté seleccionada. Si aparece `column ganancia_registrada does not exist`, volver a comprobar que la ejecución del workflow v4 fue verde.

La nueva versión se llama **Clinux | Crecimiento y rendimiento comercial (v4)** y tiene un UID distinto; el dashboard anterior no se reemplaza.

Elegí **Last 180 days** y luego **Save**.

## 4. Qué verifica cada gráfico

- Ventas mayoristas/minoristas: suma de `ventas` por cliente registrado / Consumidor Final en el rango.
- Tickets: facturas de venta, sin contar notas de crédito como tickets nuevos.
- Crecimiento: rango seleccionado vs. **igual número de días inmediatamente anteriores**; muestra "No data" cuando la base de comparación es 0.
- Ganancia registrada por canal: suma del campo de ganancia informado por Nacional Sistema y atribuible a cada canal (parcial).
- Crecimiento y rendimiento mensual: agrupa ventas y ganancia registrada para **solo los días del rango seleccionado**. Los meses de los extremos pueden ser parciales.
- Ventas diarias: facturación neta por día.
- Clientes mayoristas: top 20 con tickets, facturación neta y fecha de última compra.
- Productos más vendidos: top 10 por unidades netas con barras **horizontales**.

## Privacidad

Mantener privados los respaldos SQL y el repo. Darles acceso Viewer únicamente a usuarios autorizados del negocio. Las tablas y clientes contienen información comercial sensible.
