"""CORS 回归测试：前端端口回落到 5174 / 5175 时，后端仍允许跨域访问。

注意：本文件不在模块顶层导入 app 包。其他测试模块依赖「先设置临时数据库环境变量、
再导入配置」的顺序，顶层导入 app.core.config 会提前固化全局配置，导致它们的
临时目录保护检查失败；因此所有 app 相关导入都放在测试方法内部。
"""

import importlib
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))


def build_app(cors_origins: str):
    """按 main.py 的真实中间件配置重建应用，仅替换允许来源。

    CORSMiddleware 在创建时固化来源列表，因此必须重新加载入口模块；
    加载完成后立即按原配置重载一次，避免影响其他测试。
    """
    from app.core import config as config_module
    from app.core.config import Settings

    import app.main as main_module

    with mock.patch.object(
        config_module, "settings", Settings(cors_origins=cors_origins)
    ):
        app = importlib.reload(main_module).app
    importlib.reload(main_module)
    return app


class CorsFallbackOriginTest(unittest.TestCase):
    """P5：前端端口回落后不应因 CORS 被浏览器拦截。"""

    def test_origin_5174_allowed(self) -> None:
        from fastapi.testclient import TestClient

        origin = "http://127.0.0.1:5174"
        client = TestClient(build_app("http://127.0.0.1:5174,http://localhost:5174"))
        response = client.get("/api/health", headers={"Origin": origin})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"),
            origin,
            "5174 来源应通过 CORS 校验",
        )

    def test_origin_5174_preflight_allowed(self) -> None:
        from fastapi.testclient import TestClient

        origin = "http://127.0.0.1:5174"
        client = TestClient(build_app("http://127.0.0.1:5174,http://localhost:5174"))
        response = client.options(
            "/api/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.headers.get("access-control-allow-origin"), origin
        )

    def test_default_config_covers_fallback_ports(self) -> None:
        from app.core.config import Settings

        # 忽略 .env，只验证代码里的默认值。
        origins = Settings(_env_file=None).cors_origin_list
        for port in ("5174", "5175"):
            self.assertIn(f"http://127.0.0.1:{port}", origins)
            self.assertIn(f"http://localhost:{port}", origins)


if __name__ == "__main__":
    unittest.main()
