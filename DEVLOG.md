# DEVLOG — Price Tracker

Registro cronológico del desarrollo del proyecto. Cada entrada documenta qué se hizo, por qué, y qué decisiones se tomaron.

---

## 2026-03-18 — Inicio del proyecto

**Qué se hizo:** Primer commit. API básica con FastAPI, modelos SQLAlchemy, esquemas Pydantic, y conexión a PostgreSQL.

**Stack elegido:**
- FastAPI: async nativo, documentación automática con Swagger, tipado fuerte con Pydantic
- SQLAlchemy (async): ORM maduro, soporte para asyncpg en runtime
- PostgreSQL: necesitamos persistencia real con tipos numéricos precisos para precios
- asyncpg: driver async para PostgreSQL en runtime
- psycopg2: driver sync para Alembic (Alembic no soporta async en su env.py)

**Modelos iniciales:**
- `Product`: id, name, url (unique), category, created_at
- `PriceRecord`: id, product_id FK, price, currency (default ARS), recorded_at

**Decisión — `url` único en `products`:** Si dos usuarios quieren trackear el mismo producto, no queremos dos filas con la misma URL. El producto existe una sola vez; la relación con el usuario se maneja por separado. Esto también simplifica el scraper (no raspa duplicados).

**Decisión — `last_price` no es columna:** Se calcula en el router con una subquery. Es un campo derivado de `price_records`, no un dato que el modelo necesita almacenar ni mantener sincronizado.

---

## 2026-04-19 — Alembic y tests

**Qué se hizo:** Se configuró Alembic para migraciones y se escribió el primer conjunto de tests de integración.

**Decisión — tests contra PostgreSQL real, no mocks:** Los mocks de DB dan falsa confianza. Si cambia el esquema o hay una constraint que no simulamos, el test pasa igual. Con la DB real, los tests fallan cuando la app falla. Usamos una base separada (`price_tracker_test`) para no pisar datos de dev.

**Estrategia de fixtures:**
- `engine_test` + `create_tables`: scope de sesión — crea todas las tablas una vez, las dropea al final
- `clean_tables`: scope de función, autouse — borra filas después de cada test en orden FK-safe (`price_records` antes de `products`)
- `client`: scope de función — sobreescribe la dependencia `get_db` con el session factory de test

**Decisión — Alembic usa psycopg2:** El runtime usa asyncpg, pero Alembic corre sincrónico. No vale la pena la complejidad de hacerlo async. El `env.py` importa todos los módulos de modelos explícitamente para que el autogenerate funcione.

---

## 2026-05-13 — Restructura a multi-dominio

**Qué se hizo:** Reorganización del layout del proyecto de un flat layout a una estructura por dominio.

**Antes:**
```
app/
  models/product.py
  models/price.py
  routers/products.py
  routers/prices.py
  schemas/product.py
  schemas/price.py
```

**Después:**
```
app/
  products/
    models/
    schemas/
    routers/
    tests/
  users/
    models/
    schemas/
    routers/
```

**Por qué:** El proyecto iba a crecer con el dominio `users`. Tener todo mezclado en carpetas por tipo (`models/`, `routers/`) no escala bien. Con la estructura por dominio, todo lo relacionado con un concepto vive junto y es más fácil de navegar.

---

## 2026-05-14 — Dominio de usuarios

**Qué se hizo:** Modelos, esquemas y router para usuarios. Se agregó la relación `users` ↔ `products` via tabla pivot `user_products`.

**Modelos:**
- `User`: id, username (unique), email (unique), created_at
- `UserProduct`: id, user_id FK, product_id FK, added_at

**Decisión — many-to-many via `user_products`:** Un producto existe una sola vez en la DB. Múltiples usuarios pueden seguir el mismo producto. La tabla pivot permite eso sin duplicar filas en `products`.

**Decisión — `cascade="all, delete-orphan"` en `User.user_products`:** Si se borra un usuario, sus filas en `user_products` se borran automáticamente. Idem con `ondelete="CASCADE"` en FK para que lo maneje la DB también (doble seguro).

**Circular import en modelos:** `User` necesita saber sobre `UserProduct` y viceversa. Solución: `from __future__ import annotations` hace que los type hints sean lazy (strings en runtime, no se evalúan al importar), y el import real va al final del archivo después de definir la clase.

**Dependencia agregada:** `pydantic[email]` para validar `EmailStr` en los esquemas de usuario.

---

## 2026-05-17 — Scraper

**Qué se hizo:** Proceso independiente de scraping. Fetcher HTTP + loop principal + parsers para Frávega y Jumbo.

**Arquitectura del scraper:**
```
scraper/
  main.py     → entry point, loop cada 30 min, deduplica URLs, asyncio.gather
  fetcher.py  → descarga HTML con httpx
  parsers/products/
    fravega.py  → extrae precio de __NEXT_DATA__ (Apollo/Next.js)
    jumbo.py    → extrae precio de JSON-LD (schema.org)
```

**Decisión — el scraper habla con la API, no directamente con la DB:** El scraper es un proceso separado (`python -m scraper.main <user_id>`). En lugar de conectarse directo a PostgreSQL, hace requests HTTP a nuestra propia API. Esto mantiene la lógica de negocio centralizada en un solo lugar y permite escalar el scraper de forma independiente.

**Decisión — deduplicación de URLs antes de scrapear:** Si dos usuarios siguen el mismo producto (misma URL), el scraper lo fetcha una sola vez. La respuesta se guarda para ambos. Ahorro de requests y de potenciales bloqueos por IP.

**Decisión — `asyncio.gather` para scrapear en paralelo:** El cuello de botella del scraping es la red (esperar respuestas HTTP). Con gather, mandamos todos los requests al mismo tiempo en lugar de uno por uno. Ganancia significativa cuando hay muchos productos.

**Frávega — parser con `__NEXT_DATA__`:** Frávega usa Next.js, que embebe todos los datos de la página en un tag `<script id="__NEXT_DATA__">` como JSON. Es más estable que buscar por clase CSS porque los field names semánticos (`sellingPrice`) cambian menos que los class names de CSS.

**Jumbo — parser con JSON-LD:** Jumbo embebe los datos del producto en `<script type="application/ld+json">` siguiendo el estándar schema.org. Campo `offers.price`.

**Agregar un parser nuevo:** Crear `scraper/parsers/products/nombre_sitio.py` e importar la función `parse_price` en el dict `PARSERS` en `scraper/main.py`.

---

## 2026-06-12 — Infraestructura del bot + skills de desarrollo

### Qué se hizo

**Migración aplicada:** `3c8a1f0e2d94` — agrega `telegram_id BIGINT` (nullable, unique) a `users` y crea la tabla `alerts` (user_product_id FK, condition, threshold, created_at).

**API — endpoint puente:**
- `GET /users/by-telegram/{telegram_id}` en el router de users — prerequisito de todos los comandos del bot
- `UserRead` actualizado para exponer `telegram_id`
- Tests de integración nuevos: `app/users/tests/` con `conftest.py` + `test_users.py` (200 y 404)

**Bot — infraestructura base (`python-telegram-bot` 21.10):**
- `bot/config.py` — `BotSettings` con pydantic-settings, mismo patrón que `app/core/config.py`
- `bot/api_client.py` — `ApiClient` con un solo `httpx.AsyncClient` (base_url + timeout), `ApiError` exception, `get_user_by_telegram` como primer método tipado
- `bot/main.py` — reescrito: lifecycle hooks `post_init`/`post_shutdown` que crean/cierran el cliente en `bot_data["api"]`; global error handler que loguea y responde; `require_user` decorator; `/ping` como smoke test; catch-all con `filters.COMMAND`
- `.env.example` creado con todos los placeholders

**Skills de desarrollo:**
- `.claude/skills/add-resource/SKILL.md` — checklist para agregar un recurso nuevo a la API
- `.claude/skills/add-bot-command/SKILL.md` — checklist para agregar un comando al bot

### Decisiones

**`require_user` pasa el user como argumento, no lo guarda en `context.user_data`:**
Los handlers decorados reciben `(update, context, user: dict)`. Guardar el user en `user_data` sería un bug: ese store persiste entre mensajes del mismo chat, por lo que un handler podría leer un user stale de una request anterior.

**`bot/config.py` separado de `app/core/config.py`:**
El bot es un proceso independiente. Tiene sus propias variables (`API_BASE_URL`, `API_TIMEOUT`, `LOG_LEVEL`) que la app no necesita. Un `BotSettings` propio evita contaminar `app.core.config` con settings que no le pertenecen.

**`httpx.AsyncClient` creado una vez en `post_init`, no por request:**
Reusar el cliente aprovecha connection pooling y evita el overhead de crear/cerrar conexiones TCP en cada comando.

**La skill `add-bot-command` es todavía una hipótesis:**
El flujo completo (args → resolve user → llamar API → traducir ApiError → responder) no fue ejecutado en un comando real. La skill se valida cuando se escriba `/track`.

### Próximos pasos (superado, ver entrada 2026-07-06)

---

## 2026-07-06 — `/track`, `/list`, `/prices` y auto-registro

### Qué se hizo

**`telegram_id` en `UserCreate`:** ya no falta — el schema lo expone (`int | None = None`) y `create_user` en el router chequea duplicado también por `telegram_id` (además de username/email) para evitar un 500 por unique constraint en creaciones concurrentes.

**`GET /products/?url=<url>`:** agregado como query param opcional sobre el `list_products` existente (no como endpoint nuevo). Devuelve `list[ProductRead]`, vacía si no hay match — se trata "no existe todavía" como caso esperado, no como 404.

**`/start` auto-registra al usuario:** busca primero por `telegram_id` (mismo lookup que ya usaba `require_user`); si no existe, crea el `User` con username/email placeholder derivados del `telegram_id` (determinístico, idempotente — correr `/start` dos veces no duplica nada).

**`/track <url>`:** primer comando de negocio real del bot. Busca el producto por URL; si no existe lo crea con un nombre placeholder (URL truncada — el nombre real se corrige después cuando el scraper lo levante); asocia el producto al usuario. Distingue los dos 409 posibles: URL duplicada (recuperación silenciosa por carrera) vs. producto ya trackeado por ese usuario (mensaje explícito al usuario).

**`/list` y `/prices <id>`:** el bloque "ver estado" completo.
- `/list` → `GET /users/{id}/products`, una línea por producto con su último precio (o "sin precio registrado").
- `/prices <id>` → `GET /products/{id}/prices`, historial en texto (se descartó gráfico de imagen) con variación %/flecha (↑/↓/→) entre registros consecutivos, leído en orden cronológico ascendente (la API devuelve DESC).

**Bug encontrado y corregido:** `GET /users/{id}/products` nunca calculaba `last_price` (siempre `null`), a diferencia de `GET /products/` y `GET /products/{id}` que sí usan `_last_price()`. Se corrigió reusando esa misma función en `get_user_products`. Sin este fix, `/list` no tenía sentido (su columna principal siempre habría estado vacía).

**Tests nuevos:** `test_create_user_with_telegram_id_ok`, `test_create_user_duplicate_telegram_id`, `test_get_user_products_empty`, `test_get_user_products_includes_last_price` (regresión del bug), `test_list_products_filter_by_url_match`, `test_list_products_filter_by_url_no_match`. Suite completa: 32/32.

**Verificación:** no hay tests automatizados para `bot/` (no se armó infraestructura nueva para esto). Se verificó todo el flujo simulando con `curl` contra un servidor real lo que el bot llamaría — mismo criterio que ya se venía usando: crear usuario, filtrar por URL, crear/asociar producto, forzar los dos casos de 409, poblar varios `PriceRecord` y confirmar a mano que la variación % calculada coincide con la del código. Datos de prueba limpiados de la DB de dev al final de cada verificación.

### Decisiones

**`/prices` no valida ownership del producto:** cualquier `product_id` válido devuelve su historial sin chequear que pertenezca a quien pregunta. Es consistente con el resto del sistema (no hay autenticación real; `/track` ya comparte productos entre usuarios) y evita una llamada extra sin beneficio de seguridad real. Si se agrega autenticación en el futuro, este es el punto donde iría el chequeo de ownership.

**Nombre placeholder al crear producto desde `/track`:** se usa la URL truncada a 60 caracteres. Se decidió no pedirle el nombre al usuario para no sumar fricción — se corrige más adelante cuando el scraper pueda extraer el nombre real de la página (fuera de alcance de esta sesión).

**Username/email placeholder en `/start`:** `username = tg_username or f"tg{telegram_id}"`, `email = f"tg{telegram_id}@telegram.example.com"`. Determinístico y sin colisión de unique constraint por diseño; si el username real choca con un registro preexistente no-Telegram (409), se reintenta una vez con `f"tg{telegram_id}"`.

### Bugs encontrados corriendo el bot real

**Email placeholder con dominio `.local` rechazado por `EmailStr`:** al levantar el bot contra Telegram real, `/start` tiraba "Ocurrió un error inesperado". El placeholder original (`tg{id}@placeholder.local`) usaba un TLD reservado (RFC 2606: `.local`, `.invalid`, `.test`), que `email-validator` rechaza explícitamente. Cambiado a `tg{id}@telegram.example.com` (`example.com` sí es aceptado). Corregido en `bot/main.py`.

**`bot/config.py` sin `extra: "ignore"`:** el bot y la API comparten el mismo `.env`. Como `BotSettings` no toleraba campos extra, `DATABASE_URL` (que pertenece a `app/core/config.py`) rompía el arranque del bot con `ValidationError: extra_forbidden`. Agregado `"extra": "ignore"` al `model_config` de `BotSettings`.

### Próximos pasos (consolidado con ideas nuevas del 2026-07-06, ver siguiente entrada para 1-4)

5. **Botones inline en Telegram (prioridad baja)** — reemplazar comandos de texto por `InlineKeyboardMarkup` donde tenga sentido (ej. elegir un producto de `/list` tocando un botón).
6. **Dashboard web personal** — página propia, no pública, para visualización/pruebas: estado del sistema, productos, precios, interacción básica. Uso personal de monitoreo, no reemplaza al bot.
7. **Búsqueda inteligente de productos** — comando `/buscar <término>` que dispare scraping de *búsqueda* (no de una URL conocida) contra las tiendas relevantes en paralelo, filtrando por categoría de tienda (ej. no buscar notebooks en Jumbo), devolviendo resultados combinados como botones inline para elegir uno o varios. Requiere un segundo tipo de parser por tienda (`parse_search_results`, distinto del `parse_price` actual), un registro de categorías por tienda, y un endpoint nuevo `POST /search`.
8. **Expansión a nuevos dominios** — ejemplos: vuelos de avión, activos financieros. Son recursos con forma distinta a "producto con precio" (campos y fuentes de datos propios); cada uno probablemente necesita su propio modelo/schema/router siguiendo la skill `add-resource`, y su propia fuente de datos/scraper.

---

## 2026-07-06 (cont.) — Alertas, nombre real vía scraper, IDs por-usuario, limpieza de índices

### Qué se hizo

**Bloque 4 — Limpieza de índices redundantes:** se quitó el `index=True` redundante en la PK de los 5 modelos (`Product`, `PriceRecord`, `User`, `UserProduct`, `Alert`) — cada uno ya tiene su propio índice único vía `_pkey`. Migración `eaf1a705802d` (`DROP INDEX` de los 5 `ix_<table>_id`), aplicada y verificada contra Postgres real.

**Bloque 3 — IDs de producto por-usuario:** `GET /users/{id}/products` ahora ordena por `UserProduct.id` (antes sin `ORDER BY` explícito). El bot deja de mostrar el `product_id` real: `/list` numera 1, 2, 3... por posición, y `/prices <n>` traduce esa posición al `product_id` real vía el helper nuevo `resolve_product_id` (`bot/main.py`) antes de llamar a la API.

**Bloque 2 — Nombre real de producto vía scraper:** cada parser (`fravega.py`, `jumbo.py`) gana una función `parse_name(html) -> str | None` (nunca lanza, `parse_price` no se toca). El scraper, tras registrar un precio, si el nombre actual del producto sigue siendo el placeholder de `/track` (`nombre == url[:60]`), extrae el nombre real y hace `PATCH /products/{id}`. La clave exacta del nombre en el Apollo state de Frávega no está confirmada con HTML real — se prueban varias claves candidatas (`name`/`title`/`productName`) con fallback a `None`.

**Bloque 1 — Sistema de alertas:** migración `45a343679b6f` agrega `triggered_at` a `Alert`. Nuevo schema (`app/users/schemas/alert.py`, `condition` como `Literal["percent_drop", "price_below"]`) y router (`app/users/routers/alerts.py`, anidado bajo `/users/{user_id}/products/{product_id}/alerts`). La evaluación de alertas ocurre **dentro** de `POST /products/{id}/prices` (no un endpoint separado) — el scraper sigue llamando exactamente lo mismo que ya llamaba. Si una alerta dispara, la API misma manda el mensaje de Telegram vía un cliente httpx liviano nuevo (`app/core/telegram.py::send_telegram_message`), sin agregar `python-telegram-bot` al proceso de la API. Nuevo comando de bot `/alerta <n> <condicion> <valor>`.

**Tests nuevos:** `test_get_user_products_stable_order`; 8 tests en `app/users/tests/test_alerts.py` (creación, validación, listado, y 3 escenarios de evaluación end-to-end con `send_telegram_message` mockeado vía `monkeypatch`). Suite completa: 41/41.

**Verificación manual end-to-end con Telegram real:** se creó una alerta `price_below` real contra el propio usuario de Telegram del desarrollador, se posteó un precio que la disparó, y se confirmó en los logs de la API un `POST .../sendMessage "HTTP/1.1 200 OK"` real — el mensaje llegó. Se confirmó también que un segundo precio que cumple la misma condición NO reenvía (un solo `sendMessage` en total). Datos de prueba limpiados de la DB de dev al finalizar.

### Decisiones

**Evaluación de alertas vive en `app/users/routers/alerts.py`, no en una carpeta `services/` nueva** — se mantiene junto al router del mismo recurso, consistente con que el resto del proyecto no tiene esa capa de abstracción.

**`percent_drop` se calcula contra el precio inmediatamente anterior**, no el mínimo histórico ni el primero registrado — más simple de calcular (ya se tiene `_last_price()` antes del insert) y más intuitivo para "avisame si bajó ahora".

**Alertas se desactivan tras dispararse** (`triggered_at` se setea una vez, no se re-evalúa). Limitación conocida: si dos instancias del scraper (distinto `user_id`, mismo producto compartido) postean casi simultáneamente, es posible un doble disparo por lectura de `triggered_at IS NULL` antes de que el otro commitee — riesgo bajo (mensaje duplicado, no corrupción), no se agregó locking todavía.

### Bug encontrado: mismo problema de `.env` compartido, en sentido inverso

Al agregar `API_BASE_URL=http://localhost:8001` al `.env` (para esquivar el proceso zombie, ver nota abajo), `pytest` empezó a fallar: `app.core.config.Settings` no tenía `extra: "ignore"`, así que un campo que le pertenece solo al bot rompía la carga de settings de la API. Es el mismo bug que ya se había arreglado en `BotSettings` (sesión anterior, con `DATABASE_URL`), ahora en la dirección opuesta. Agregado `extra: "ignore"` también a `Settings` (`app/core/config.py`). Ambas clases comparten un único `.env` pero cada una solo declara su propio subconjunto de variables — cualquier variable nueva puede volver a disparar esto del lado que no la declara.

### Nota operativa — proceso zombie en el puerto 8000

Durante la verificación manual, un proceso `uvicorn` anterior (arrancado en una sesión previa con `disown`) quedó "zombie": seguía escuchando en el puerto 8000 y respondiendo correctamente, pero ni PowerShell (`Stop-Process`) ni bash (`kill`) podían verlo o matarlo — probablemente quedó en un namespace de proceso distinto al que ambas shells consultan en este entorno. Se resolvió sin perseguir el PID: se levantó la API nueva en el puerto 8001 y se actualizó `API_BASE_URL=http://localhost:8001` en `.env` para que el bot apunte ahí. El proceso viejo del 8000 se dejó vivo (no interfiere, corre código desactualizado sin nadie que le hable).

### Próximos pasos

Quedan pendientes de la lista consolidada: botones inline (prioridad baja), dashboard web personal, búsqueda inteligente de productos, expansión a nuevos dominios (vuelos, activos financieros). Adicional de esta sesión:
- Confirmar con HTML real de Frávega la clave exacta del nombre del producto en `__NEXT_DATA__` (hoy `parse_name` es defensivo pero no validado en producción).
- Considerar `.with_for_update()` en `evaluate_alerts` si el doble-disparo por concurrencia del scraper se vuelve un problema real (hoy es una limitación documentada, no bloqueante).
