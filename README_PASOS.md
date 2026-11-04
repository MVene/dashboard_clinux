# Clinux: migración a cuenta de servicio Google Drive (WIF)

**Meta:** pasar de rclone con OAuth personal a Google Workload Identity Federation para GitHub Actions, conservando el ETL v4 y Neon/Grafana.

## Antes de modificar nada
- Comprobaste que **Probar acceso seguro a Drive** terminó **verde**.
- GitHub Actions → Settings → Secrets and variables → Actions → Variables contiene:
  - `GCP_WORKLOAD_IDENTITY_PROVIDER` (identificador completo)
  - `GCP_SERVICE_ACCOUNT` (correo de `clinux-dashboard-reader`)
  - `GCP_DRIVE_FOLDER_ID` (ID de la carpeta compartida `clinux`, no una URL).
- GitHub Secrets tiene `DATABASE_URL`.
- No se debe publicar el respaldo `.sql`, ningún token, ni el archivo `gha-creds-*.json`.

## 1) Actualizar el repositorio desde Ubuntu

Descomprimí `Clinux_WIF_actualizacion_segura.zip` **dentro** de `~/Escritorio/dashboard_clinux`:

```bash
cd ~/Escritorio/dashboard_clinux
unzip -o ~/Descargas/Clinux_WIF_actualizacion_segura.zip
source .venv/bin/activate
python -m unittest discover -s tests -v
```

**Importante:** este ZIP **NO** reemplaza el workflow principal; añade uno nuevo manual de prueba. El archivo `paso_final/actualizar_dashboard.yml` queda fuera de `.github/workflows/` de forma intencional.

Actualizá `.gitignore` añadiendo, si faltan, estas líneas:
```
gha-creds-*.json
*.sql.partial
```

Subí solamente lo nuevo, nunca `.sql` ni claves:

```bash
git add scripts/drive_wif.py tests/test_drive_wif.py .github/workflows/actualizar_dashboard_wif_prueba.yml .gitignore
# Revisá siempre git status antes del commit.
git status
git commit -m "Prueba WIF para actualización de datos Clinux"
git push origin main
```

Si `.gitignore` no cambió, Git lo omitirá sin problema.

## 2) Probar sin tocar el workflow actual

GitHub → Actions → **Actualizar dashboard Clinux (prueba WIF)** → Run workflow (`main`).

Debe quedar verde, pasando por:
1. Autenticar Google Cloud.
2. Descargar último respaldo con cuenta de servicio.
3. Procesar respaldo y actualizar PostgreSQL.

Puede decir **sin cambios** si el último SQL ya estaba procesado: también es válido.

Si falla, conservás sin cambios el workflow original `Actualizar dashboard Clinux`.

## 3) Solamente después de una prueba WIF verde

Reemplazá el workflow principal por el archivo de `paso_final`:

```bash
cp paso_final/actualizar_dashboard.yml .github/workflows/actualizar_dashboard.yml
git add .github/workflows/actualizar_dashboard.yml
git commit -m "Usar WIF en actualización automática de Clinux"
git push origin main
```

Opcionalmente, eliminá el workflow WIF de prueba (ya no es necesario). Conservá solo **un workflow programado**.

## 4) Cierre y seguridad

Luego de confirmar que el workflow principal ejecuta en verde (manual o programado):
- Eliminá de GitHub Secrets `RCLONE_CONFIG_BASE64`, porque deja de utilizarse.
- Revocá desde tu cuenta de Google la autorización personal de rclone usada para Clinux. **Solo después** de comprobar la migración.
- Si el proveedor OAuth personal ya no tiene otros usos, podés deshabilitarlo o eliminarlo.
- Conservá el repo privado; otorgá en Grafana rol Viewer a los patrones.

## Cómo se elige el archivo

El nuevo lector consulta **solo la carpeta compartida** por ID, recorre todas las páginas de Drive, selecciona el `.sql` más reciente según fecha/hora en el nombre de Clinux, descarga en el directorio temporal del runner, verifica encabezado y final del dump, ejecuta el ETL existente con `--file` y borra la copia temporal. No cambia Nacional Sistema ni las tablas originales.
