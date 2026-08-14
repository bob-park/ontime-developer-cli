from __future__ import annotations

import httpx

from . import auth

DEFAULT_BASE_URL = "http://localhost:8080/api"


class ApiError(Exception):
    pass


def format_problem(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        return f"{body['code']}: {body['detail']}"
    except (ValueError, KeyError):
        return f"HTTP {resp.status_code}: {resp.text[:200]}"


class ApiClient:
    def __init__(self) -> None:
        self.config = auth.load_config()
        tokens = auth.load_tokens()
        if tokens is None:
            raise auth.AuthError("로그인이 필요합니다: `ontime login` 을 먼저 실행하세요.")
        if auth.is_expired(tokens):
            tokens = auth.refresh_tokens(self.config, tokens)
        self.tokens = tokens
        self.base_url = self.config.get("api_base_url", DEFAULT_BASE_URL)

    def request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._send(method, path, **kwargs)
        if resp.status_code == 401:
            self.tokens = auth.refresh_tokens(self.config, self.tokens)
            resp = self._send(method, path, **kwargs)
        if resp.status_code >= 400:
            raise ApiError(format_problem(resp))
        return resp.json()

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        return httpx.request(
            method,
            self.base_url + path,
            headers={"Authorization": f"Bearer {self.tokens['access_token']}"},
            **kwargs,
        )
