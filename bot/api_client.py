import httpx


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


class ApiClient:
    def __init__(self, base_url: str, timeout: float) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout)

    async def get_user_by_telegram(self, telegram_id: int) -> dict | None:
        resp = await self._client.get(f"/users/by-telegram/{telegram_id}")
        if resp.status_code == 404:
            return None
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()
