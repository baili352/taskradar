"""登录注册接口的请求与响应模型。"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    invite_code: str = Field(min_length=1, max_length=64)

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("用户名至少 2 个字符")
        if any(char.isspace() for char in cleaned):
            raise ValueError("用户名不能包含空格")
        return cleaned


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class AuthUser(BaseModel):
    id: int
    username: str


class AuthState(BaseModel):
    """登录状态：enabled 为 false 时前端不展示登录页。"""

    enabled: bool = False
    authenticated: bool = False
    user: AuthUser | None = None
