"""登录注册与接口鉴权测试。

覆盖：邀请码注册、登录、注销、接口 401、密码与会话令牌落库形态。
"""

import hashlib
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault(
    "DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="taskradar-auth-")) / "taskradar.db"),
)
os.environ.setdefault(
    "MATERIAL_UPLOAD_DIR",
    str(Path(tempfile.mkdtemp(prefix="taskradar-auth-up-")) / "materials"),
)

from fastapi.testclient import TestClient

from app.core.config import settings
from app.db import database
from app.main import app

INVITE = "TEAM-INVITE-2026"
PASSWORD = "Passw0rd!2026"


class AuthEnabledTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="taskradar-auth-")
        root = Path(self._temp.name)
        self.db_path = root / "taskradar.db"
        self._patches = [
            mock.patch.object(database.settings, "database_path", str(self.db_path)),
            mock.patch.object(
                database.settings, "material_upload_dir", str(root / "uploads" / "materials")
            ),
            mock.patch.object(settings, "auth_enabled", True),
            mock.patch.object(settings, "auth_invite_code", INVITE),
        ]
        for patch in self._patches:
            patch.start()
        database.init_database()
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        for patch in reversed(self._patches):
            patch.stop()
        self._temp.cleanup()

    def _register(self, username: str = "demo_user") -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"username": username, "password": PASSWORD, "invite_code": INVITE},
        )
        self.assertEqual(response.status_code, 200, response.text)
        # 注册即登录：响应体必须直接反映登录成功，不能等下一次 /auth/me。
        state = response.json()
        self.assertTrue(state["authenticated"])
        self.assertEqual(state["user"]["username"], username)

    def test_register_then_me_and_logout(self):
        self._register()
        state = self.client.get("/api/auth/me").json()
        self.assertTrue(state["enabled"])
        self.assertTrue(state["authenticated"])
        self.assertEqual(state["user"]["username"], "demo_user")

        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        state = self.client.get("/api/auth/me").json()
        self.assertFalse(state["authenticated"])
        self.assertIsNone(state["user"])

    def test_register_rejects_wrong_invite_code(self):
        response = self.client.post(
            "/api/auth/register",
            json={"username": "intruder", "password": PASSWORD, "invite_code": "WRONG"},
        )
        self.assertEqual(response.status_code, 403)
        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        self.assertEqual(count, 0)

    def test_duplicate_username_rejected(self):
        self._register()
        response = self.client.post(
            "/api/auth/register",
            json={"username": "DEMO_USER", "password": PASSWORD, "invite_code": INVITE},
        )
        self.assertEqual(response.status_code, 409)

    def test_login_with_wrong_password_rejected(self):
        self._register()
        self.client.post("/api/auth/logout")
        response = self.client.post(
            "/api/auth/login",
            json={"username": "demo_user", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_and_protected_api_requires_session(self):
        self.assertEqual(self.client.get("/api/matters").status_code, 401)

        self._register()
        self.assertEqual(self.client.get("/api/matters").status_code, 200)

        self.client.post("/api/auth/logout")
        self.assertEqual(self.client.get("/api/matters").status_code, 401)

        response = self.client.post(
            "/api/auth/login",
            json={"username": "demo_user", "password": PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/matters").status_code, 200)

    def test_password_and_session_token_are_hashed(self):
        self._register()
        raw_token = self.client.cookies.get("taskradar_session")
        self.assertTrue(raw_token)

        with closing(sqlite3.connect(self.db_path)) as conn:
            password_hash = conn.execute(
                "SELECT password_hash FROM users WHERE username = ?", ("demo_user",)
            ).fetchone()[0]
            token_hash = conn.execute(
                "SELECT token_hash FROM sessions"
            ).fetchone()[0]

        self.assertTrue(password_hash.startswith("pbkdf2_sha256$"))
        self.assertNotIn(PASSWORD, password_hash)
        self.assertNotEqual(token_hash, raw_token)
        self.assertEqual(token_hash, hashlib.sha256(raw_token.encode()).hexdigest())

    def test_register_requires_configured_invite_code(self):
        with mock.patch.object(settings, "auth_invite_code", ""):
            response = self.client.post(
                "/api/auth/register",
                json={"username": "demo_user", "password": PASSWORD, "invite_code": "x"},
            )
        self.assertEqual(response.status_code, 503)


class AuthDisabledTest(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix="taskradar-auth-off-")
        root = Path(self._temp.name)
        self._patches = [
            mock.patch.object(
                database.settings, "database_path", str(root / "taskradar.db")
            ),
            mock.patch.object(
                database.settings, "material_upload_dir", str(root / "uploads" / "materials")
            ),
            mock.patch.object(settings, "auth_enabled", False),
        ]
        for patch in self._patches:
            patch.start()
        database.init_database()
        self._client_ctx = TestClient(app)
        self.client = self._client_ctx.__enter__()

    def tearDown(self):
        self._client_ctx.__exit__(None, None, None)
        for patch in reversed(self._patches):
            patch.stop()
        self._temp.cleanup()

    def test_api_stays_open_and_auth_reports_disabled(self):
        self.assertFalse(self.client.get("/api/auth/me").json()["enabled"])
        self.assertEqual(self.client.get("/api/matters").status_code, 200)
        self.assertEqual(
            self.client.post(
                "/api/auth/login",
                json={"username": "nobody", "password": "whatever"},
            ).status_code,
            403,
        )


if __name__ == "__main__":
    unittest.main()
