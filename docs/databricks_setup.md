# Tutorial Paso 1: Databricks Free Edition + GitHub Actions

Esta guía configura la plataforma de datos en **Databricks Free Edition** (100% gratuito, sin tarjeta) y automatiza la descarga y transformación diaria desde **GitHub Actions**.

## Limitaciones contempladas de Databricks Free Edition
- **Solo cómputo Serverless:** [counterbuild_pipeline](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/data_pipeline/src/counterbuild_pipeline) usa exclusivamente la API de DataFrames (sin `.rdd`, `.cache()`, `.persist()`, `sparkContext` ni `input_file_name()`).
- **Egress restringido:** como los notebooks gratuitos suelen bloquear llamadas salientes hacia `api.deadlock-api.com`, la ingesta corre en un runner gratuito de **GitHub Actions** y sube los archivos al Volume `workspace.deadlock.raw`.
- **Auto-stop del SQL Warehouse:** el *Serverless Starter Warehouse* se apaga automáticamente tras unos minutos de inactividad y se enciende solo (**auto-start**) cuando el bot le pide datos cada 12 h. No necesitas ni debes intentar mantenerlo encendido 24/7.

---

## Paso 1: Crear el esquema y el volumen en Unity Catalog
1. Crea o abre tu workspace en **Databricks Free Edition** (`https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`).
2. En el menú lateral izquierdo abre **SQL Editor** y ejecuta:
   ```sql
   CREATE SCHEMA IF NOT EXISTS workspace.deadlock;
   CREATE VOLUME IF NOT EXISTS workspace.deadlock.raw;
   ```
3. Confirma en **Catalog** → `workspace` → `deadlock` → **Volumes** que aparece `raw`.

---

## Paso 2: Generar los 2 Personal Access Tokens (PATs)
Abre tu avatar (esquina superior derecha) → **Settings** → **Developer** → en **Access tokens** pulsa **Manage**.

> **¿Por qué 2 tokens y por qué 90 días?** Separar tokens garantiza que el servidor del bot nunca tenga permisos para modificar jobs o archivos en Databricks. Cambiar **Lifetime (days)** del valor por defecto (`14`) a **`90`** (o el máximo que permita tu workspace) evita tener que regenerarlos cada dos semanas.

### Token 1: `deadlock-bot-sql` *(solo para el `.env` del Bot)*
1. Pulsa **Generate new token** y rellena:
   - **Name:** `deadlock-bot-sql`
   - **Lifetime (days):** `90` *(o el máximo permitido)*
   - **Auto-scope tokens:** `Off`
   - **Scope:** cambia a la pestaña **`BI Tools`** *(limita el token exclusivamente a consultas SQL Warehouses)*
2. Pulsa **Generate** y **copia el token (`dapi...`) de inmediato** (no volverá a mostrarse). Este valor irá en `DATABRICKS_TOKEN` dentro del `.env` del servidor ([deployment.md](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/docs/deployment.md)).

### Token 2: `deadlock-github-actions` *(solo para GitHub Secrets)*
1. Pulsa nuevamente **Generate new token** y rellena:
   - **Name:** `deadlock-github-actions`
   - **Lifetime (days):** `90` *(o el máximo permitido)*
   - **Auto-scope tokens:** **`On`** *(otorga `all-apis` durante 30 días para que el CLI no falle al usar Unity Catalog, Volumes y Asset Bundles, y después Databricks restringe automáticamente el token solo a los endpoints usados)*
   - **Scope:** deja seleccionada la pestaña **`Other APIs`** *(si el botón Generate aún exige elegir un scope manual en `Add scope`, selecciona `all-apis`)*
2. Pulsa **Generate** y **copia el token (`dapi...`) de inmediato**.

---

## Paso 3: Obtener la conexión del SQL Warehouse Serverless
1. En el menú lateral izquierdo de Databricks abre **SQL Warehouses**.
2. Selecciona el warehouse serverless por defecto (`Serverless Starter Warehouse`) → pestaña **Connection details**.
3. Copia estos dos valores (se usarán en el `.env` del Bot):
   - **Server hostname:** ej. `dbc-xxxxxxxx-xxxx.cloud.databricks.com` *(sin `https://`)* → `DATABRICKS_SERVER_HOSTNAME`.
   - **HTTP path:** ej. `/sql/1.0/warehouses/0123456789abcdef` → `DATABRICKS_HTTP_PATH`.

---

## Paso 4: Configurar GitHub Actions y lanzar la primera ingesta
1. Sube este proyecto a un repositorio **público** en GitHub *(incluye minutos gratuitos de GitHub Actions sin tarjeta; asegúrate de nunca subir `.env` ni archivos locales con tokens)*.
2. En GitHub entra a **Settings** → **Secrets and variables** → **Actions** → **New repository secret** y añade:
   | Secret | Valor |
   |---|---|
   | `DATABRICKS_HOST` | URL completa con `https://` (ej. `https://dbc-xxxxxxxx-xxxx.cloud.databricks.com`) |
   | `DATABRICKS_TOKEN` | El **Token 2 (`deadlock-github-actions`)** |
   | `DEADLOCK_API_KEY` | *(Opcional)* Solo si tienes clave para `api.deadlock-api.com` |
3. **¿Cómo se ejecuta el workflow?** [daily_ingest_and_pipeline.yml](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/.github/workflows/daily_ingest_and_pipeline.yml) funciona de dos formas:
   - **Automáticamente:** cada día a las **`05:00 UTC`** (00:00 UTC-5) sobre la rama `main`.
   - **Manualmente:** desde **Actions** → **Daily Deadlock Ingest & Databricks Pipeline** → **Run workflow** *(no corre automáticamente en cada `git push`)*.
4. Lanza la primera ejecución manual haciendo clic en **Run workflow** (puedes dejar `pages = 10` y `limit_per_request = 100`, o subir `pages` a `30` para acumular más muestra el primer día). El workflow descargará héroes/ítems y partidas, los subirá al Volume y desplegará/ejecutará [databricks.yml](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/data_pipeline/databricks.yml) (`01 → 02 → 03`).

---

## Paso 5: Confirmar que `gold_counter_items` tiene datos
En el **SQL Editor** de Databricks ejecuta:
```sql
SELECT enemy_hero_name, item_name, win_rate_delta, item_cost, games_with_item
FROM workspace.deadlock.gold_counter_items
WHERE ally_hero_id = 0 AND rank <= 3
ORDER BY enemy_hero_name, rank
LIMIT 20;
```
Si ves filas recomendadas, la capa de datos está lista. *(Si el primer día aparecen pocas filas por el umbral `min_games_with_item = 50`, lanza otra corrida manual del workflow o espera a que el `MERGE` incremental en `bronze_matches` acumule más partidas).*

Continúa con [docs/discord_setup.md](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/docs/discord_setup.md).
