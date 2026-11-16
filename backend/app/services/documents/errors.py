"""文档读取相关异常，统一携带中文提示与 HTTP 状态码。"""


class DocumentError(Exception):
    """可预期的文档错误，例如格式不支持、文件为空、内容损坏。"""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
