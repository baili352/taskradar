"""应用配置：统一从环境变量 / .env 读取。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend 目录（app/core/config.py -> app/core -> app -> backend）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """项目配置项，字段名与环境变量名一一对应。"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "办事雷达 TaskRadar AI"
    app_version: str = "0.1.0"
    app_env: str = "development"

    host: str = "127.0.0.1"
    port: int = 8000
    api_prefix: str = "/api"

    database_path: str = "./data/taskradar.db"
    # 材料文件受控存储目录（不对外静态暴露）
    material_upload_dir: str = "./data/uploads/materials"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 统一业务时区：风险判断中的“今天”和截止时间都按该时区计算
    app_timezone: str = "Asia/Shanghai"

    # 文档上传限制（第三阶段）
    max_upload_mb: int = 10

    # OpenAI 兼容大模型；API Key 仅从此处读取，不进入接口响应或前端状态。
    ai_provider: str = "OpenAI 兼容服务"
    ai_api_key: str = ""
    ai_model: str = ""
    ai_base_url: str = ""
    ai_timeout_seconds: float = 60
    ai_max_retries: int = 1
    ai_max_input_chars: int = 60000

    # 本地 RapidOCR；不上传图片或扫描件到第三方 OCR 服务。
    ocr_enabled: bool = True
    ocr_max_pages: int = 50
    ocr_pdf_dpi: int = 200
    ocr_pdf_text_threshold: int = 20
    ocr_max_image_pixels: int = 20000000
    ocr_min_confidence: float = 0.5

    @property
    def base_dir(self) -> Path:
        return BASE_DIR

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def ai_configured(self) -> bool:
        """OpenAI 兼容服务只需地址和模型；Ollama 等本地服务可无密钥。"""
        return bool(self.ai_base_url.strip() and self.ai_model.strip())


@lru_cache
def get_settings() -> Settings:
    """缓存配置实例，避免重复解析 .env。"""
    return Settings()


settings = get_settings()
