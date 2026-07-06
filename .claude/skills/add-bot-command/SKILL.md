---
name: add-bot-command
description: >
  Use when adding a new Telegram bot command. Triggers on: "add a bot command",
  "new command", "implement /track", "add /<anything> to the bot", "the bot
  should do X". Walks through API gaps → api_client method → handler → registration,
  enforcing decisions before code.
---

# Add a Telegram bot command

Work through each step in order. Settle the design decision at the top of each
step before writing any code — every step depends on the previous one.

---

## 1. Map the command to API calls

Decide before writing anything:
- What does this command need from the API? (reads, writes, both)
- Which endpoints already exist that cover it?
- Which endpoints are missing and must be added first?

The bot **never touches the DB directly** — everything goes through the API over
HTTP. If an endpoint is missing, add it first (use the `add-resource` skill if
it implies a new entity; otherwise add it to the relevant existing router).

---

## 2. Add the API client method (`bot/api_client.py`)

For each new API call the command needs, add a typed method to `ApiClient`.

Conventions to match exactly:
- Return `dict | None` when 404 is a valid non-error state (e.g. lookup by id)
- Return `dict` when the call must succeed (e.g. POST that creates a resource)
- On any non-success, non-404 status: `raise ApiError(resp.status_code, resp.text)`
- Use `resp.is_success` (not `resp.status_code == 200`) for the success check
- The shared `self._client` instance is already configured with `base_url` and
  `timeout` — do not create new clients inside methods

---

## 3. Resolve the user (decide whether the command requires it)

Every command that acts on behalf of a user must call
`api.get_user_by_telegram(update.effective_user.id)` first.

- If the command **requires** a registered user: decorate the handler with
  `@require_user`. The decorator short-circuits with a message if the user is
  absent and passes the resolved user as a third positional argument to the
  handler. The handler signature must accept it:
  `async def <name>(update, context, user: dict) -> None`
- If the command **does not** require a user (e.g. informational, public):
  omit the decorator and use the standard two-argument signature.

Do not call `get_user_by_telegram` manually inside a handler decorated with
`@require_user`, and do not read the user from `context.user_data` — it is not
stored there. The decorator passes it directly as an argument.

---

## 3.5. Referencing "the user's Nth product" — never accept a raw `product_id`

If the command lets the user pick one of *their own* products (like `/prices <n>`
or `/alerta <n> ...`), the number the user types is a **position** in their own
`/list`, not the real `product_id` in the database — real ids are global and
shared across users (`user_products.user_id`/`product_id` is many-to-many).

Always translate position → real id with the existing helper before calling any
other API method:

```python
product_id = await resolve_product_id(api, user["id"], position)
if product_id is None:
    await update.effective_message.reply_text(f"No tenés un producto #{position}. Usá /list.")
    return
```

`resolve_product_id` (in `bot/main.py`) calls `api.get_user_products(user_id)` —
which is ordered by `user_products.id` server-side, so the position always
matches what `/list` last showed — and indexes into it. Do not invent a second
way to resolve "the Nth product"; reuse this helper.

---

## 4. Write the handler (`bot/main.py`)

Decide before writing:
- Does the command take arguments? (`context.args` is a list of strings)
- What are the error cases visible to the user (bad input, API errors, not found)?
- What does a success reply look like?

Conventions to match exactly:
- Handler signature without `@require_user`: `async def <name>(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None`
- Handler signature with `@require_user`: `async def <name>(update: Update, context: ContextTypes.DEFAULT_TYPE, user: dict) -> None`
- Get the API client: `api: ApiClient = context.bot_data["api"]`
- Reply with: `await update.effective_message.reply_text("...")`
- Use `update.effective_message` (not `update.message`) — it works in both
  direct messages and group chats
- Catch `ApiError` explicitly when you need to translate it to a user-facing
  message; otherwise let it propagate to the global error handler

---

## 5. Register the handler in `main()` (`bot/main.py`)

Add the handler **before** the catch-all `MessageHandler(filters.COMMAND, unknown)`:

```python
app.add_handler(CommandHandler("<command_name>", <handler_function>))
```

The catch-all must stay last.

---

## Do NOT

- Access the database directly from the bot — use the API.
- Instantiate `httpx.AsyncClient` inside a handler — use `context.bot_data["api"]`.
- Call `get_user_by_telegram` manually in a handler decorated with `@require_user`.
- Register a handler after the `MessageHandler(filters.COMMAND, unknown)` catch-all.
