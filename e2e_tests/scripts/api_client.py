"""E2E 测试用最小 HTTP 客户端（仅标准库），支持 JSON 与 multipart 上传。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE_URL = "http://127.0.0.1:8020/api"


class ApiResult:
    def __init__(self, status: int, body, raw: bytes):
        self.status = status
        self.body = body
        self.raw = raw

    def __repr__(self) -> str:
        return f"ApiResult(status={self.status}, body={self.body!r})"


def _decode(raw: bytes):
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return raw.decode("utf-8", errors="replace")


def request(
    method: str,
    path: str,
    payload=None,
    params: dict | None = None,
    timeout: int = 60,
) -> ApiResult:
    url = BASE_URL + path
    if params:
        from urllib.parse import urlencode

        url += "?" + urlencode({k: v for k, v in params.items() if v is not None})
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return ApiResult(resp.status, _decode(raw), raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return ApiResult(exc.code, _decode(raw), raw)


def upload_file(path: str, file_path: Path, field: str = "file") -> ApiResult:
    boundary = "----taskradar-e2e-" + uuid.uuid4().hex
    content = file_path.read_bytes()
    filename = file_path.name
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: application/octet-stream\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    body = head + content + tail
    req = urllib.request.Request(
        BASE_URL + path,
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read()
            return ApiResult(resp.status, _decode(raw), raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        return ApiResult(exc.code, _decode(raw), raw)
