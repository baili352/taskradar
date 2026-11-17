"""AI 与本地 OCR 的离线回归测试；不访问真实模型，不执行真实 OCR 推理。"""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import fitz
import httpx
import numpy as np
from fastapi import UploadFile
from openai import APIConnectionError, APITimeoutError, AuthenticationError
from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="taskradar-ai-ocr-"))
os.environ.setdefault("DATABASE_PATH", str(_TMP_ROOT / "test.db"))
os.environ.setdefault("MATERIAL_UPLOAD_DIR", str(_TMP_ROOT / "uploads"))

from app.api.routes import analysis  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.ai import analyzer  # noqa: E402
from app.services.ai import client as ai_client  # noqa: E402
from app.services.ai.client import AIError  # noqa: E402
from app.services.documents import image_reader, ocr_engine, pdf_reader  # noqa: E402
from app.services.documents.errors import DocumentError  # noqa: E402
from app.services.documents.image_reader import read_image  # noqa: E402
from app.services.documents.pdf_reader import read_pdf  # noqa: E402
from app.services.documents.reader import read_document  # noqa: E402
from app.services.materials.verifier import verify_material  # noqa: E402

NOTICE_LINES = [
    "2026 年校园创新大赛",
    "参赛对象：全日制本科生",
    "报名时间：2026 年 11 月 1 日至 2026 年 11 月 15 日",
    "提交报名表",
    "办理流程：网上报名",
    "注意事项：逾期不予受理",
]
NOTICE_TEXT = "\n".join(NOTICE_LINES).encode("utf-8")


def tearDownModule() -> None:
    import shutil

    shutil.rmtree(_TMP_ROOT, ignore_errors=True)


def ai_settings(**overrides):
    values = {
        "ai_base_url": "https://unit.test/v1",
        "ai_model": "unit-model",
        "ai_api_key": "",
    }
    values.update(overrides)
    return mock.patch.multiple(settings, **values)


def valid_payload() -> dict:
    def field(key, value, segment_ids):
        return {
            "key": key,
            "value": value,
            "status": "found",
            "segment_ids": segment_ids,
            "note": None,
        }

    return {
        "fields": [
            field("title", "2026 年校园创新大赛", [0]),
            field("matter_type", "竞赛", [0]),
            field("qualification", "全日制本科生", [1]),
            field("registration_start", "2026 年 11 月 1 日", [2]),
            field("deadline", "2026 年 11 月 15 日", [2]),
        ],
        "materials": [{"name": "报名表", "segment_id": 3}],
        "process": [{"text": "网上报名", "segment_id": 4}],
        "notes": [{"text": "逾期不予受理", "segment_id": 5}],
    }


def upload(content: bytes = NOTICE_TEXT, filename: str = "notice.txt") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


class AnalysisModeTest(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_ai_uses_rules_without_calling_model(self) -> None:
        ai_mock = mock.AsyncMock()
        with ai_settings(ai_base_url="", ai_model=""), mock.patch.object(
            analysis, "analyze_with_ai", ai_mock
        ):
            response = await analysis.analyze_document(upload())
        self.assertEqual(response.analysis_mode, "rule_based")
        self.assertFalse(response.ai_configured)
        ai_mock.assert_not_awaited()

    async def test_valid_ai_json_rebuilds_all_evidence_from_local_segments(self) -> None:
        request_mock = mock.AsyncMock(return_value=json.dumps(valid_payload()))
        with ai_settings(), mock.patch.object(
            analyzer, "request_analysis_json", request_mock
        ):
            response = await analysis.analyze_document(upload())

        self.assertEqual(response.analysis_mode, "ai_assisted")
        self.assertEqual(response.fields[0].value, "2026 年校园创新大赛")
        self.assertEqual(response.fields[0].evidence[0].text, NOTICE_LINES[0])
        self.assertEqual(response.fields[0].evidence[0].location, "第 1 行")
        self.assertEqual(response.fields[0].evidence[0].paragraph, 1)
        self.assertEqual(response.fields[1].evidence[0].text, NOTICE_LINES[0])
        self.assertEqual(response.materials[0].evidence.text, NOTICE_LINES[3])
        self.assertEqual(response.process[0].evidence.text, NOTICE_LINES[4])
        self.assertEqual(response.notes[0].evidence.text, NOTICE_LINES[5])
        sent_prompt = request_mock.await_args.args[1]
        self.assertIn(NOTICE_LINES[0], sent_prompt)
        self.assertNotIn("evidence", valid_payload()["fields"][0])

    async def test_invalid_ai_outputs_explicitly_fall_back(self) -> None:
        missing_field = valid_payload()
        missing_field["fields"].pop()
        invalid_key = valid_payload()
        invalid_key["fields"][0]["key"] = "invented"
        out_of_range = valid_payload()
        out_of_range["fields"][0]["segment_ids"] = [999]
        missing_evidence = valid_payload()
        missing_evidence["fields"][0]["segment_ids"] = []
        cases = {
            "non_json": "这不是 JSON",
            "missing_field": json.dumps(missing_field),
            "invalid_key": json.dumps(invalid_key),
            "out_of_range_segment": json.dumps(out_of_range),
            "found_without_evidence": json.dumps(missing_evidence),
        }
        for name, content in cases.items():
            with self.subTest(case=name), ai_settings(), mock.patch.object(
                analyzer,
                "request_analysis_json",
                new=mock.AsyncMock(return_value=content),
            ):
                response = await analysis.analyze_document(upload())
                self.assertEqual(response.analysis_mode, "rule_fallback")
                self.assertIn("回退", response.ai_message)
                self.assertTrue(response.fields)

    async def test_timeout_auth_and_connection_errors_fall_back(self) -> None:
        errors = [
            AIError("大模型服务响应超时，请稍后重试或检查服务状态。"),
            AIError("大模型服务鉴权失败，请检查 backend/.env 中的密钥配置。"),
            AIError("无法连接大模型服务，请检查服务地址、网络或本地模型是否已启动。"),
        ]
        for error in errors:
            with self.subTest(error=str(error)), ai_settings(), mock.patch.object(
                analysis,
                "analyze_with_ai",
                new=mock.AsyncMock(side_effect=error),
            ):
                response = await analysis.analyze_document(upload())
                self.assertEqual(response.analysis_mode, "rule_fallback")
                self.assertIn(str(error), response.ai_message)

    async def test_input_limit_does_not_truncate_or_send_document(self) -> None:
        request_mock = mock.AsyncMock()
        with ai_settings(ai_max_input_chars=3), mock.patch.object(
            analyzer, "request_analysis_json", request_mock
        ):
            response = await analysis.analyze_document(upload())
        self.assertEqual(response.analysis_mode, "rule_fallback")
        self.assertIn("未截断发送", response.ai_message)
        request_mock.assert_not_awaited()

    async def test_unexpected_ai_error_is_sanitized(self) -> None:
        secret = "private-model-secret"
        with ai_settings(), mock.patch.object(
            analysis,
            "analyze_with_ai",
            new=mock.AsyncMock(side_effect=RuntimeError(secret)),
        ), self.assertLogs("app.api.routes.analysis", level="ERROR") as logs:
            response = await analysis.analyze_document(upload())
        self.assertEqual(response.analysis_mode, "rule_fallback")
        self.assertNotIn(secret, response.model_dump_json())
        self.assertNotIn(secret, "\n".join(logs.output))

    def test_capabilities_expose_only_key_boolean(self) -> None:
        secret = "never-return-this-key"
        with ai_settings(ai_api_key=secret), mock.patch.object(
            analysis,
            "get_ocr_status",
            return_value=(True, True, "本地 OCR 可用"),
        ):
            capabilities = analysis.get_capabilities()
        self.assertTrue(capabilities.ai_key_configured)
        self.assertNotIn(secret, capabilities.model_dump_json())
        self.assertNotIn("unit.test", capabilities.model_dump_json())


class _FakeCompletions:
    def __init__(self, action):
        self.action = action

    async def create(self, **_options):
        if isinstance(self.action, Exception):
            raise self.action
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.action))]
        )


class _FakeClient:
    def __init__(self, action):
        self.chat = SimpleNamespace(completions=_FakeCompletions(action))

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


class AIClientTest(unittest.IsolatedAsyncioTestCase):
    async def test_openai_errors_become_safe_messages_and_logs_hide_secrets(self) -> None:
        secret = "offline-test-secret"
        request = httpx.Request("POST", "https://unit.test/chat/completions")
        response = httpx.Response(401, request=request)
        cases = [
            (APITimeoutError(request=request), "超时"),
            (
                AuthenticationError(message=secret, response=response, body=None),
                "鉴权失败",
            ),
            (APIConnectionError(message=secret, request=request), "无法连接"),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__), ai_settings(
                ai_api_key=secret
            ), mock.patch.object(
                ai_client,
                "_CompatibleClient",
                lambda **_kwargs: _FakeClient(error),
            ), self.assertLogs("app.services.ai.client", level="ERROR") as logs:
                with self.assertRaises(AIError) as caught:
                    await ai_client.test_ai_connection()
                self.assertIn(expected, str(caught.exception))
                self.assertNotIn(secret, str(caught.exception))
                self.assertNotIn(secret, "\n".join(logs.output))

    async def test_connection_test_success_and_failure_do_not_leak_key(self) -> None:
        secret = "connection-test-secret"
        with ai_settings(ai_api_key=secret), mock.patch.object(
            ai_client,
            "_CompatibleClient",
            lambda **_kwargs: _FakeClient("OK"),
        ):
            result = await analysis.test_connection()
        self.assertTrue(result.success)
        self.assertNotIn(secret, result.model_dump_json())

        request = httpx.Request("POST", "https://unit.test/chat/completions")
        error = AuthenticationError(
            message=secret,
            response=httpx.Response(401, request=request),
            body=None,
        )
        with ai_settings(ai_api_key=secret), mock.patch.object(
            ai_client,
            "_CompatibleClient",
            lambda **_kwargs: _FakeClient(error),
        ), self.assertLogs("app.services.ai.client", level="ERROR") as logs:
            result = await analysis.test_connection()
        self.assertFalse(result.success)
        self.assertIn("鉴权失败", result.message)
        self.assertNotIn(secret, result.model_dump_json())
        self.assertNotIn(secret, "\n".join(logs.output))

    async def test_keyless_local_client_sends_no_fake_authorization(self) -> None:
        async with ai_client._CompatibleClient(
            api_key=ai_client._NO_KEY_PLACEHOLDER,
            base_url="http://127.0.0.1:11434/v1",
        ) as local_client:
            self.assertEqual(local_client.auth_headers, {})


def image_bytes(image_format: str = "PNG", size=(40, 20)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=image_format)
    return buffer.getvalue()


def pdf_bytes(pages: list[tuple[str, bool]]) -> bytes:
    pdf = fitz.open()
    for text, with_image in pages:
        page = pdf.new_page()
        if text:
            page.insert_text((72, 72), text)
        if with_image:
            page.insert_image(fitz.Rect(72, 100, 172, 140), stream=image_bytes())
    content = pdf.tobytes()
    pdf.close()
    return content


class ImageOCRTest(unittest.TestCase):
    def test_png_jpg_jpeg_share_document_reader(self) -> None:
        cases = [("a.png", "PNG"), ("a.jpg", "JPEG"), ("a.jpeg", "JPEG")]
        for filename, image_format in cases:
            with self.subTest(filename=filename), mock.patch.object(
                image_reader, "recognize", return_value=["报名表", "姓名：张三"]
            ):
                document = read_document(filename, image_bytes(image_format), 100000)
                self.assertTrue(document.ocr_used)
                self.assertEqual(document.ocr_pages, [1])
                self.assertEqual(document.segments[0].location, "第 1 页（OCR）")

    def test_corrupt_image_is_rejected(self) -> None:
        with self.assertRaises(DocumentError) as caught:
            read_image("broken.png", ".png", b"not an image")
        self.assertEqual(caught.exception.code, "invalid_image")

    def test_extension_must_match_real_image_format(self) -> None:
        with self.assertRaises(DocumentError) as caught:
            read_image("fake.png", ".png", image_bytes("JPEG"))
        self.assertEqual(caught.exception.code, "image_extension_mismatch")

    def test_image_pixel_limit_is_enforced_before_ocr(self) -> None:
        recognize_mock = mock.Mock()
        with mock.patch.object(settings, "ocr_max_image_pixels", 10), mock.patch.object(
            image_reader, "recognize", recognize_mock
        ):
            with self.assertRaises(DocumentError) as caught:
                read_image("large.png", ".png", image_bytes())
        self.assertEqual(caught.exception.code, "image_too_large")
        recognize_mock.assert_not_called()

    def test_low_resolution_image_returns_warning_without_rejecting(self) -> None:
        # 短边不足 1200 或总像素不足 1500000，均只提示、不拒绝。
        cases = [(400, 300), (700, 700)]
        for size in cases:
            with self.subTest(size=size), mock.patch.object(
                image_reader, "recognize", return_value=["报名表", "姓名：张三"]
            ):
                document = read_document("small.png", image_bytes(size=size), 100000)
                self.assertTrue(document.ocr_used)
                self.assertEqual(len(document.segments), 2)
                self.assertEqual(
                    document.warnings,
                    [
                        "图片分辨率较低，OCR 结果可能有误，"
                        "建议使用 ≥200DPI 扫描件或清晰拍摄件"
                    ],
                )

    def test_screen_screenshot_triggers_low_resolution_warning(self) -> None:
        # 回归保护：1920×1080 屏幕截图短边不足阈值，必须提示但不拒绝。
        with mock.patch.object(image_reader, "recognize", return_value=["总览", "风险提醒"]):
            document = read_document(
                "screen.png", image_bytes(size=(1920, 1080)), 100000
            )
        self.assertTrue(document.ocr_used)
        self.assertIn("图片分辨率较低", document.warnings[0])
        self.assertEqual(len(document.segments), 2)

    def test_normal_resolution_image_has_no_warning(self) -> None:
        with mock.patch.object(image_reader, "recognize", return_value=["报名表"]):
            document = read_document(
                "clear.png", image_bytes(size=(1600, 1200)), 100000
            )
        self.assertEqual(document.warnings, [])

    def test_empty_ocr_result_is_explicit_no_text(self) -> None:
        with mock.patch.object(image_reader, "recognize", return_value=[]):
            with self.assertRaises(DocumentError) as caught:
                read_image("blank.png", ".png", image_bytes())
        self.assertEqual(caught.exception.code, "no_text")

    def test_ocr_confidence_filter_and_disabled_state(self) -> None:
        engine = mock.Mock(
            return_value=(
                [([], "保留", 0.9), ([], "过滤", 0.1), ([], "", 1.0)],
                1,
            )
        )
        with mock.patch.object(ocr_engine, "_engine", engine), mock.patch.multiple(
            settings, ocr_enabled=True, ocr_min_confidence=0.5
        ):
            lines = ocr_engine.recognize(np.zeros((5, 5, 3), dtype=np.uint8))
        self.assertEqual(lines, ["保留"])

        with mock.patch.object(settings, "ocr_enabled", False):
            with self.assertRaises(DocumentError) as caught:
                ocr_engine.recognize(np.zeros((5, 5, 3), dtype=np.uint8))
        self.assertEqual(caught.exception.code, "ocr_disabled")


class PDFOCRTest(unittest.TestCase):
    def ocr_available(self):
        return mock.patch.object(
            pdf_reader, "get_ocr_status", return_value=(True, True, "本地 OCR 可用")
        )

    def rendered_page(self):
        return mock.patch.object(
            pdf_reader,
            "_render_page",
            return_value=np.zeros((10, 10, 3), dtype=np.uint8),
        )

    def test_native_pdf_does_not_call_ocr(self) -> None:
        content = pdf_bytes([("NATIVE PAGE WITH ENOUGH TEXT", False)])
        with mock.patch.object(pdf_reader, "recognize") as recognize_mock, mock.patch.object(
            pdf_reader, "get_ocr_status"
        ) as status_mock:
            document = read_pdf("native.pdf", content)
        self.assertFalse(document.ocr_used)
        self.assertEqual(document.segments[0].text, "NATIVE PAGE WITH ENOUGH TEXT")
        recognize_mock.assert_not_called()
        status_mock.assert_not_called()

    def test_scanned_pdf_uses_ocr(self) -> None:
        with self.ocr_available(), self.rendered_page(), mock.patch.object(
            pdf_reader, "recognize", return_value=["SCANNED TEXT"]
        ), mock.patch.object(settings, "ocr_enabled", True):
            document = read_pdf("scan.pdf", pdf_bytes([("", False)]))
        self.assertTrue(document.ocr_used)
        self.assertEqual(document.ocr_pages, [1])
        self.assertEqual(document.segments[0].text, "SCANNED TEXT")
        self.assertEqual(document.segments[0].location, "第 1 页（OCR）")

    def test_mixed_pdf_preserves_page_order(self) -> None:
        content = pdf_bytes(
            [("NATIVE PAGE WITH ENOUGH TEXT", False), ("", True)]
        )
        with self.ocr_available(), self.rendered_page(), mock.patch.object(
            pdf_reader, "recognize", return_value=["SCANNED PAGE"]
        ), mock.patch.object(settings, "ocr_enabled", True):
            document = read_pdf("mixed.pdf", content)
        self.assertEqual(document.ocr_pages, [2])
        self.assertEqual(
            [(item.text, item.page) for item in document.segments],
            [("NATIVE PAGE WITH ENOUGH TEXT", 1), ("SCANNED PAGE", 2)],
        )

    def test_partial_ocr_failure_preserves_native_text_and_warns(self) -> None:
        content = pdf_bytes(
            [("NATIVE PAGE WITH ENOUGH TEXT", False), ("", True)]
        )
        error = DocumentError("ocr_failed", "模拟 OCR 失败。", 422)
        with self.ocr_available(), self.rendered_page(), mock.patch.object(
            pdf_reader, "recognize", side_effect=error
        ), mock.patch.object(settings, "ocr_enabled", True):
            document = read_pdf("partial.pdf", content)
        self.assertEqual(document.segments[0].text, "NATIVE PAGE WITH ENOUGH TEXT")
        self.assertFalse(document.ocr_used)
        self.assertTrue(any("第 2 页 OCR 未完成" in item for item in document.warnings))

    def test_scanned_pdf_disabled_and_unavailable_errors(self) -> None:
        content = pdf_bytes([("", False)])
        with mock.patch.object(settings, "ocr_enabled", False):
            with self.assertRaises(DocumentError) as caught:
                read_pdf("disabled.pdf", content)
        self.assertEqual(caught.exception.code, "ocr_disabled")

        with mock.patch.object(settings, "ocr_enabled", True), mock.patch.object(
            pdf_reader,
            "get_ocr_status",
            return_value=(True, False, "本地 OCR 依赖未完整安装。"),
        ):
            with self.assertRaises(DocumentError) as caught:
                read_pdf("unavailable.pdf", content)
        self.assertEqual(caught.exception.code, "ocr_unavailable")

    def test_mixed_pdf_disabled_ocr_keeps_native_text_and_warns(self) -> None:
        content = pdf_bytes(
            [("NATIVE PAGE WITH ENOUGH TEXT", False), ("", True)]
        )
        with mock.patch.object(settings, "ocr_enabled", False):
            document = read_pdf("mixed-disabled.pdf", content)
        self.assertEqual(len(document.segments), 1)
        self.assertTrue(any("OCR 已禁用" in item for item in document.warnings))

    def test_ocr_page_limit(self) -> None:
        with mock.patch.object(settings, "ocr_max_pages", 1):
            with self.assertRaises(DocumentError) as caught:
                read_pdf("pages.pdf", pdf_bytes([("", False), ("", False)]))
        self.assertEqual(caught.exception.code, "ocr_too_many_pages")

    def test_pdf_render_pixel_limit(self) -> None:
        with self.ocr_available(), mock.patch.multiple(
            settings, ocr_enabled=True, ocr_max_image_pixels=1
        ):
            with self.assertRaises(DocumentError) as caught:
                read_pdf("pixels.pdf", pdf_bytes([("", False)]))
        self.assertEqual(caught.exception.code, "image_too_large")


class OCRMaterialVerificationTest(unittest.TestCase):
    def test_ocr_text_enters_existing_rule_verifier(self) -> None:
        with mock.patch.object(
            image_reader,
            "recognize",
            return_value=["报名表", "姓名：张三", "签字：张三"],
        ):
            document = read_image("报名表.png", ".png", image_bytes())
        result = verify_material(
            {"name": "报名表", "description": "需签字"}, document
        )
        self.assertEqual(result.result, "qualified")
        self.assertEqual(result.source, "rule")
        keyword_check = next(
            item for item in result.checks if item.key == "keyword_coverage"
        )
        self.assertEqual(keyword_check.status, "pass")
        self.assertEqual(keyword_check.location, "第 1 页（OCR）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
