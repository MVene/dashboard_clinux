# Clinux | Dashboard gerencial en Grafana Cloud

Este repositorio convierte el respaldo `.sql` de Nacional Sistema guardado en Google Drive en indicadores consultables por **Grafana** desde cualquier lugar.

**No restaura ni ejecuta el SQL original.** Lee INSERTs de tablas específicas del respaldo, agrupa indicadores y los publica en PostgreSQL. No se comparte el respaldo original con Grafana ni se sube a GitHub.

## Arquitectura

`Nacional Sistema -> copia SQL en Google Drive -> GitHub Actions (Python y rclone) -> PostgreSQL gestionado -> Grafana Cloud (usuarios Viewer)`

- **Grafana Cloud** hospeda el dashboard permanentemente; GitHub Actions **no es un servidor**.
- **PostgreSQL** conserva los indicadores entre ejecuciones; opciones: una instancia gestionada en Neon, Supabase u otro proveedor compatible.
- **GitHub Actions** programa el procesamiento cuatro veces por día: **09:23, 12:23, 15:23 y 18:23 (Argentina)**. El disparo programado de GitHub puede sufrir retrasos.
- El panel solo se actualiza hasta la **última copia SQL** que Nacional Sistema haya generado y sincronizado en Drive.

## Qué incluye el dashboard

| Panel | Fuente | Observación |
| --- | --- | --- |
| Ventas del período | Documentos FC, FN, FX, NC, ND | Incluye notas de crédito como resta; excluye presupuestos y remitos |
| Crecimiento mes comparable | Ventas del último mes hasta día último dato vs. mismos días mes anterior | Crecimiento **nominal**, no ajustado por inflación; no sigue el filtro de fechas |
| Ganancia registrada | Columna `ganancia$` en Nacional Sistema | **NO es ganancia neta**: falta validación de costos, gastos y cobertura |
| Ranking de productos | Detalle de comprobantes | Unidades netas por producto |
| Mayoristas | Listas/grupos seleccionados | Requiere validar criterios comerciales |
| Stock | Existencias por producto | Umbral global configurable, **no mínimo real de stock** |
| Última actualización | Descarga, cálculo y publicación | Informa de qué fecha son los datos |

En el respaldo de prueba, el campo de mínimo de stock no tenía valores; por eso el panel de stock usa como referencia un umbral general configurable (por defecto, 10 unidades). En octubre de 2026 la cobertura de `ganancia$` de ventas era aproximadamente del **87,4 %**.

## 1. Crear PostgreSQL gestionado

1. Crear una **base exclusivamente para los indicadores de Clinux** en un proveedor compatible con PostgreSQL (p. ej. Neon o Supabase).
2. Guardar la cadena de conexión TLS del usuario que pueda crear y actualizar las tablas (será el secreto `DATABASE_URL` en GitHub).
3. Para Grafana, crear **otro usuario** exclusivo de lectura (no reutilizar el usuario escritor). Ejemplo para ejecutar como administrador de esa base:

```sql
CREATE ROLE grafana_lector LOGIN PASSWORD 'ELEGIR_CONTRASENA_SEGURA';
GRANT CONNECT ON DATABASE nombre_de_la_base TO grafana_lector;
GRANT USAGE ON SCHEMA public TO grafana_lector;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO grafana_lector;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO grafana_lector;
```

Realizar esta configuración **solo en la nueva base analítica**, nunca en la base de Nacional Sistema. Si la base tiene otro nombre/esquema, ajustar estas instrucciones. **No publicar contraseñas**.

## 2. Preparar acceso privado a Google Drive con `rclone`

En tu computadora Linux (o una temporal de confianza):

```bash
sudo apt update
sudo apt install rclone
rclone config
```

Crear un remoto llamado **`gdrive`** de tipo Google Drive y completar la autorización OAuth. Comprobar que la carpeta se ve, reemplazando la ruta por la real:

```bash
rclone lsf 'gdrive:Clinux/Respaldos' --files-only
```

Buscar el archivo `rclone.conf` con `rclone config file`. Si está en `~/.config/rclone/rclone.conf`, generar el valor para GitHub:

```bash
base64 -w0 ~/.config/rclone/rclone.conf
```

**El resultado es una credencial muy sensible**: copiarlo directamente al secreto de GitHub, no enviarlo por chat, email ni ponerlo en código. Base64 **no es cifrado**. Opcionalmente usar una cuenta de Google con acceso únicamente a la carpeta de respaldos.

## 3. Crear un repositorio PRIVADO en GitHub

1. Crear un repositorio privado, por ejemplo `clinux-dashboard`.
2. Subir solo los archivos de esta carpeta, conservando `.github/workflows/actualizar_dashboard.yml`.
3. En **Settings → Secrets and variables → Actions → Secrets**, configurar:
   - `RCLONE_CONFIG_BASE64`: contenido del `rclone.conf` codificado como se muestra arriba.
   - `DATABASE_URL`: cadena TLS de PostgreSQL con un usuario autorizado a escribir indicadores.
4. En **Variables** del mismo menú, configurar:
   - `DRIVE_FOLDER`: por ejemplo `gdrive:Clinux/Respaldos` (camino real de la carpeta).
   - `WHOLESALE_LISTS`: `LISTA EMPRESAS,SEIQ MAYORISTA` (opcional; adaptar a las listas correctas).
   - `WHOLESALE_GROUPS`: `EMPRESAS` (opcional).
   - `STOCK_ALERT_THRESHOLD`: `10` (opcional; un umbral visual global, no mínimo real de reposición).
5. En **Actions → Actualizar dashboard Clinux → Run workflow**, ejecutarlo manualmente una vez. Una vez configurado, se ejecutará automáticamente también.

**Importante:** no subir nunca respaldos `.sql`, archivos `.env`, `rclone.conf` ni credenciales. `.gitignore` ayuda pero no evita que alguien suba archivos manualmente.

## 4. Configurar Grafana Cloud

1. Abrir https://grafana.com/products/cloud/ y crear o ingresar a tu stack.
2. **Connections → Data sources → PostgreSQL**: ingresar host, puerto, base y el **usuario exclusivo de lectura** de la base analítica. Usar conexión SSL/TLS y verificar con **Save & test**. Nota: Grafana Cloud debe poder llegar al servidor PostgreSQL; los hosts solo locales no funcionan sin un túnel especial.
3. **Dashboards → New → Import**: importar `grafana/dashboard_clinux.json` y seleccionar el datasource PostgreSQL de Clinux cuando lo solicite. Si no aparece el selector del datasource, abrir el JSON y reemplazar `${DS_CLINUX}` por el UID del datasource creado.
4. Desde Grafana Cloud invitar a tus patrones como usuarios **Viewer**. No activar enlaces públicos ni compartir instantáneas públicas para información financiera.
5. El dashboard tiene refresco visual configurado cada hora. La fuente de verdad es la última copia de Drive procesada por GitHub Actions.

Documentación oficial:
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/postgres/configure/
- https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/account-management/cloud-portal/
- https://rclone.org/drive/

## 5. Probar SIN conectar la nube

En Linux, con Python 3.12 y un archivo local de respaldo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.etl --file '/ruta/al/respaldo.sql' --dry-run
```

No se publican clientes, montos ni copias SQL: el comando imprime únicamente cantidad de registros procesados y cobertura del dato de ganancia.

## Precauciones operativas

- La copia puede contener ventas, proveedores, clientes y otros datos sensibles; mantener Drive, GitHub y PostgreSQL **privados**.
- Un respaldo SQL completo no debe ejecutarse en PostgreSQL: el programa extrae estructuras seleccionadas y publica indicadores ya procesados.
- Al cambiar la versión de Nacional Sistema o los nombres de columnas, revisar el parser y las consultas.
- La ejecución programada puede retrasarse; revisar pestaña Actions y el panel **Última actualización**.
- La actualización de PostgreSQL se hace dentro de una transacción: si falla, la versión anterior no debe reemplazarse parcialmente.
- El programa reemplaza todas las tablas analíticas `clinux_...` en cada actualización de respaldo; no altera las tablas de Nacional Sistema.
- La clasificación mayorista depende de listas/grupos configurados y se debe validar con ejemplos reales de venta.
- Antes de tomar decisiones sobre ganancias netas, incorporar gastos, impuestos, costos y datos faltantes, y acordar una definición contable.

## Archivos

- `.github/workflows/actualizar_dashboard.yml`: automatización GitHub Actions.
- `scripts/drive_sync.py`: descarga la copia `.sql` más reciente de una carpeta Drive privada (rclone).
- `scripts/sql_dump.py`: lector selectivo de copias MySQL sin ejecutarlas.
- `scripts/metrics.py`: reglas de ventas y documentos.
- `scripts/etl.py`: genera agregados, actualiza PostgreSQL y valida cambios.
- `grafana/dashboard_clinux.json`: 13 paneles importables en Grafana Cloud.

