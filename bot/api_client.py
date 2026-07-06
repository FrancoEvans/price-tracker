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

    async def create_user(self, username: str, email: str, telegram_id: int) -> dict:
        resp = await self._client.post(
            "/users/",
            json={"username": username, "email": email, "telegram_id": telegram_id},
        )
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def find_product_by_url(self, url: str) -> dict | None:
        resp = await self._client.get("/products/", params={"url": url})
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        products = resp.json()
        return products[0] if products else None

    async def create_product(self, name: str, url: str) -> dict:
        resp = await self._client.post("/products/", json={"name": name, "url": url})
        if resp.status_code == 409:
            raise ApiError(409, resp.text)
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def add_product_to_user(self, user_id: int, product_id: int) -> dict:
        resp = await self._client.post(
            f"/users/{user_id}/products", json={"product_id": product_id}
        )
        if resp.status_code == 409:
            raise ApiError(409, resp.text)
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def get_user_products(self, user_id: int) -> list[dict]:
        resp = await self._client.get(f"/users/{user_id}/products")
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def get_price_history(self, product_id: int) -> list[dict] | None:
        resp = await self._client.get(f"/products/{product_id}/prices")
        if resp.status_code == 404:
            return None
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def create_alert(
        self, user_id: int, product_id: int, condition: str, threshold: str
    ) -> dict:
        resp = await self._client.post(
            f"/users/{user_id}/products/{product_id}/alerts",
            json={"condition": condition, "threshold": threshold},
        )
        if resp.status_code == 404:
            raise ApiError(404, resp.text)
        if not resp.is_success:
            raise ApiError(resp.status_code, resp.text)
        return resp.json()

    async def close(self) -> None:
        await self._client.aclose()
