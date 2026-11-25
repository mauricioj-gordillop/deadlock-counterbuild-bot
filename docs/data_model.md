# Modelo de Datos y Métrica `win_rate_delta`

## 1. Definición de `win_rate_delta`

Para cada jugador-partida con héroe `ally_hero_id` y cada héroe rival `enemy_hero_id` en el equipo opuesto:

- `games` / `wins`: total de apariciones y victorias del par `(ally_hero_id, enemy_hero_id)`.
- `games_with_item` / `wins_with_item`: subconjunto donde ese jugador compró al menos una vez el `item_id` (deduplicado por `(match_id, account_id, item_id)`).
- `win_rate_with_item = wins_with_item / games_with_item`
- `win_rate_without_item = (wins - wins_with_item) / (games - games_with_item)`
- `win_rate_delta = round((win_rate_with_item - win_rate_without_item) * 100, 2)` (en puntos porcentuales).

Además se genera el agregado `ally_hero_id = 0` (**Any**), que consolida a todos los héroes aliados para consultas `/counter <enemigo>` sin aliado específico o como *fallback* automático cuando un enfrentamiento `(aliado, enemigo)` concreto no alcanza el mínimo estadístico (`MIN_GAMES_WITH_ITEM=50`, `MIN_GAMES_WITHOUT_ITEM=50`).

## 2. Tablas Delta Lake en Databricks (`workspace.deadlock`)

| Capa | Tabla | Contenido principal |
|---|---|---|
| Bronze | `bronze_matches` | `match_id`, `raw_json`, `source_file`, `ingested_at` (actualizada incrementalmente con `MERGE`) |
| Bronze | `bronze_reference_heroes`, `bronze_reference_items` | Snapshots JSON crudos de `api.deadlock-api.com/v1/assets/heroes` y `/v1/assets/items` |
| Silver | `silver_matches` | Partidas válidas (`duration_s >= 900`, `not_scored != true`, 12 jugadores, sin abandonos, `start_time` y equipos normalizados, deduplicadas) |
| Silver | `silver_player_matches` | 1 fila por `(match_id, account_id)` con `hero_id`, `team`, `won` |
| Silver | `silver_player_items` | Compras únicas de ítems de tienda (`type='upgrade' AND shopable=true`) |
| Silver | `silver_dim_heroes`, `silver_dim_items` | Dimensiones limpias con `name_normalized` y costos en almas |
| Gold | `gold_counter_items` | Top `N` ítems por `(ally_hero_id, enemy_hero_id)` ordenados por `win_rate_delta DESC` (`OPTIMIZE ... ZORDER BY (enemy_hero_id)`) |

## 3. Estructura en Memoria (`CounterSnapshot` en `bot/bot/store.py`)

El bot se autentica con el token `deadlock-bot-sql` (*BI Tools*) contra el SQL Warehouse de Databricks y descarga en RAM tres colecciones inmutables (solo consultas `SELECT`):
- `heroes`: tupla ordenada alfabéticamente de `HeroRecord(hero_id, name, name_normalized)`.
- `items_by_id`: diccionario `item_id -> ItemRecord(item_id, name, cost, tier, slot_type)`.
- `counters_by_pair`: diccionario `(enemy_hero_id, ally_hero_id) -> tuple[CounterRuleRecord, ...]` preordenado por `rank ASC` para búsquedas `O(1)`.

## 4. Compatibilidad con endpoints reales de `api.deadlock-api.com`

* **Catálogos estáticos (`ingestion/fetch_reference.py`):** usa `https://api.deadlock-api.com/v1/assets/heroes` y `https://api.deadlock-api.com/v1/assets/items` *(el antiguo subdominio `assets.deadlock-api.com` dejó de resolver por DNS)*.
* **Metadatos de partidas (`ingestion/fetch_matches.py`):** consulta `https://api.deadlock-api.com/v1/matches/metadata?include_player_items=true` paginando por `min_match_id` con manejo de `Retry-After` en códigos `429`/`503`.
* **Particularidades manejadas en [schemas.py](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/data_pipeline/src/counterbuild_pipeline/schemas.py) y [silver.py](file:///c:/Users/Mauricio/Mi%20unidad/Ing.%20Informatica/Proyectos/deadlock-counterbuild-bot/data_pipeline/src/counterbuild_pipeline/silver.py):**
  - `start_time` acepta tanto enteros Unix epoch como cadenas UTC (`"2024-04-29 06:28:34"`), convirtiéndolos de forma segura bajo modo ANSI de Spark 4.0 mediante `try_to_timestamp`.
  - `not_scored`: descarta partidas marcadas con `not_scored = true`.
  - `abandon_match_time_s`: usa `coalesce(..., 0)` cuando el endpoint público omite este campo en `players[]`.
  - `item_id`: usa `LongType` en Spark e `int` en Python para soportar hashes `uint32` (ej. `3561817145`).
