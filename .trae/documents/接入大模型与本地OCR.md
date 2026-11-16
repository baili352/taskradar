# TaskRadar 接入大模型与本地 OCR 实施计划

## 1. 目标与范围

在保留现有文档解析、规则提取、事项保存和材料规则核验链路的前提下，完成两项真实能力接入：

1. 通过 OpenAI 兼容 `chat/completions` 接口调用大模型，支持云端兼容服务及本地 Ollama；输出事项字段、材料、流程和注意事项，并将证据绑定回本地原文片段。
2. 通过本地 RapidOCR + ONNX Runtime 识别 PNG/JPG/JPEG 图片及扫描版、低文本 PDF，识别结果继续复用现有规则/AI 分析和材料核验链路。

明确约束：

- 密钥仅从 `backend/.env` 或环境变量读取；设置页不提供密钥输入，不在 SQLite、接口响应或前端状态中保存/返回密钥。
- 规则结果始终先生成并作为可靠回退；AI 失败不能伪装成 AI 成功。
- 模型只返回候选值和原文片段编号，证据文本、页码、段落及位置均由后端从本地 `Segment` 生成。
- OCR 不上传第三方服务。配置外部大模型时，文档文本会发送到用户配置的服务，页面必须明确提示。
- 不扩展多文件批量分析、导出、材料真实性/法律效力 AI 判定、用户系统或数据库重构。

## 2. 当前状态与接入点

- `backend/app/api/routes/analysis.py`：当前为 `read_document -> extract_document`，响应固定 `rule_based`，且仍保留“已配置但未调用”的旧提示。
- `backend/app/services/extraction/extractor.py`：`extract_document()` 输出固定 5 个字段及 `materials/process/notes/warnings`，`build_evidence()` 可直接复用。
- `backend/app/services/documents/reader.py`：统一上传入口；智能分析、材料上传和材料核验都调用它，因此在这里接入图片与 OCR 可覆盖两条业务链路。
- `backend/app/services/documents/pdf_reader.py`：使用 PyMuPDF 逐页读文本，无文本时直接报错，是扫描 PDF 的接入点。
- `backend/app/services/documents/types.py`：`ExtractedDocument.segments` 是统一中间表示，现有结构只需补充 OCR 元信息和读取警告。
- `backend/app/services/materials/verifier.py`：继续基于 `ExtractedDocument` 做本地规则核验，无需改成大模型核验。
- `backend/app/schemas/analysis.py` 与 `frontend/src/types.ts`：分析模式目前限制为 `rule_based`，需扩展实际模式、能力状态和 OCR 元信息。
- `frontend/src/pages/AnalyzePage.tsx`、`SettingsPage.tsx`、`VerificationPage.tsx`、`components/ui/FileDropzone.tsx`：仍有不支持图片/OCR、未接入大模型和“绝不发送第三方”的旧文案或格式白名单。
- 当前后端测试为 Python `unittest`，已有 108 项回归基线；前端构建命令为 `npm run build`（`tsc --noEmit && vite build`）。不需要数据库结构迁移。

## 3. 配置与依赖

### 3.1 修改 `backend/app/core/config.py`

保留现有 `AI_PROVIDER / AI_API_KEY / AI_MODEL / AI_BASE_URL`，新增以下环境变量及默认值：

- `AI_TIMEOUT_SECONDS=60`
- `AI_MAX_RETRIES=1`
- `AI_MAX_INPUT_CHARS=60000`
- `OCR_ENABLED=true`
- `OCR_MAX_PAGES=50`（单份 PDF 允许执行 OCR 的页数上限）
- `OCR_PDF_DPI=200`
- `OCR_PDF_TEXT_THRESHOLD=20`（页面有效文本低于该值才考虑 OCR）
- `OCR_MAX_IMAGE_PIXELS=20000000`
- `OCR_MIN_CONFIDENCE=0.5`

`ai_configured` 改为至少具备非空 `AI_BASE_URL` 和 `AI_MODEL`；`AI_API_KEY` 可选，以支持 Ollama。存在密钥时才发送 `Authorization`，不将其拼入 URL 或日志。`AI_PROVIDER` 仅作为服务商标识，默认显示为 OpenAI 兼容服务。

### 3.2 修改 `backend/.env.example`

补充上述配置和示例：

- 云端服务：`AI_BASE_URL=https://.../v1`、模型名及密钥占位。
- Ollama：`AI_BASE_URL=http://127.0.0.1:11434/v1`，密钥留空。
- 删除“只检测、不调用”的说明，增加外部模型会接收文档文本、OCR 仅本地处理的提示。

不修改或提交真实 `.env`，不写入任何真实密钥。

### 3.3 修改 `backend/requirements.txt`

增加并锁定相互兼容的依赖：OpenAI Python SDK、RapidOCR ONNX Runtime 版、ONNX Runtime、Pillow、NumPy（使用兼容 RapidOCR 的 1.26.x）。安装后验证 Python 3.11 下导入和本地推理；不引入云端 OCR SDK。

## 4. 本地 OCR 实施

### 4.1 新增 `backend/app/services/documents/ocr_engine.py`

实现轻量封装：

- 延迟创建 RapidOCR 实例，普通 TXT/DOCX/含文本层 PDF 不加载模型。
- 使用锁保护懒初始化和推理，避免线程池并发重复加载或不受控并行占用内存。
- 输入为 RGB 图像数组，输出按识别顺序排列的文本行；过滤空文本和低于置信度阈值的行。
- 提供不触发完整推理的能力状态，供 `/analysis/capabilities` 显示启用/可用/不可用及中文原因。
- 初始化或推理异常转换为安全的 `DocumentError`，响应不暴露本地模型路径、堆栈或底层异常。

### 4.2 新增 `backend/app/services/documents/image_reader.py`

- 支持 `.png/.jpg/.jpeg`，通过 Pillow 解码并核验真实格式，不能只信任扩展名。
- 校验空文件、损坏图片、尺寸和总像素上限，处理 EXIF 方向后转 RGB。
- 调用本地 OCR，生成带 `page=1`、`location="第 1 页（OCR）"` 的 `Segment`。
- 返回 `ExtractedDocument(page_count=1, ocr_used=True, ocr_pages=[1])`；未识别到有效文本时返回明确 422 错误。

### 4.3 修改文档读取层

- `validators.py`：将 PNG/JPG/JPEG 加入 `SUPPORTED_EXTENSIONS`，更新格式错误提示；继续复用上传大小与提取文本长度限制。
- `reader.py`：增加图片分发，PDF/DOCX/TXT 行为保持不变。
- `types.py`：为 `ExtractedDocument` 增加 `ocr_used=False`、`ocr_pages=[]`、`warnings=[]`，不修改现有数据库。
- `pdf_reader.py`：先逐页保留原生文本；仅对有效文本低于阈值且含图像的页面执行 OCR，整份无文本时将各页作为 OCR 候选。按 `OCR_PDF_DPI` 渲染并校验像素上限，OCR 行使用 `第 N 页（OCR）` 定位，再按原页序合并。
- 需 OCR 页数超过 `OCR_MAX_PAGES` 时明确拒绝并提示拆分，避免长任务耗尽资源。
- OCR 禁用、不可用或单页失败时：若文档还有其他有效文本，保留可用结果并在 `warnings` 标明受影响页；若最终没有任何有效文本，则抛出 `ocr_disabled`、`ocr_unavailable`、`ocr_failed` 或 `no_text` 的明确中文错误。空白页本身不作为失败原因。
- `documents/__init__.py`：更新导出与格式说明。

OCR 只负责把图片内容转成现有 `Segment`，后续规则提取、AI 分析和 `verify_material()` 无需了解图像细节。

## 5. OpenAI 兼容大模型实施

### 5.1 新增 `backend/app/services/ai/client.py`

使用 `AsyncOpenAI` 建立统一客户端：

- 将用户配置的 `AI_BASE_URL` 直接作为 SDK 的 API 根地址，由 SDK 请求 `/chat/completions`。
- 设置超时和最多 1 次有限重试；只有配置密钥时附加密钥。
- 提供结构化分析调用和轻量连接测试调用；连接测试只发送“回复 OK”的短提示，不发送文档。
- 将超时、鉴权、限流、连接和响应错误归类为安全中文信息；日志不记录 API Key、请求头或完整文档。

### 5.2 新增 `backend/app/services/ai/analyzer.py` 与包初始化文件

定义内部 Pydantic 载荷和证据映射：

- 给每个原文 `Segment` 分配稳定的 `segment_id`（从 0 开始的数组下标），连同文本及已有位置元信息发送给模型。
- 要求模型仅返回 JSON 对象：固定字段 `title/matter_type/qualification/registration_start/deadline`，以及 `materials/process/notes`。
- 字段项包含 `key/value/status/segment_ids/note`；材料包含 `name/segment_id`；流程和注意事项包含 `text/segment_id`。模型不得返回证据正文、页码或位置。
- 提示词明确禁止外部知识、虚构截止日期和无依据补全；找不到时字段为 `pending`，列表可为空。
- 请求 JSON 对象输出；兼容服务仍返回 Markdown 代码围栏时只做保守剥离后解析，不进行无限重试或自由文本猜测。
- 校验字段键集合、字段顺序、值/说明长度和列表上限（材料 40、流程 30、注意事项 20）；`found` 字段必须有值和有效片段编号，所有材料/流程/注意事项必须引用有效片段。
- 使用本地 `build_evidence(document.segments[id])` 重建证据；流程序号由后端重新生成，警告由本地最终结果重新计算。
- 任一结构或证据引用不合法时，整份 AI 结果判为无效并回退规则，避免夹带伪造证据或混合来源不清的结果。
- 文档字符数超过 `AI_MAX_INPUT_CHARS` 时不静默截断，直接说明原因并使用规则结果。

## 6. 分析接口与响应

### 6.1 修改 `backend/app/api/routes/analysis.py`

实际流程调整为：

1. 读取文档（必要时本地 OCR）。
2. 在线程池执行现有 `extract_document()`，保留完整规则结果。
3. 未配置 AI：返回 `analysis_mode="rule_based"`。
4. 已配置且输入未超限：调用 AI；校验成功返回 `analysis_mode="ai_assisted"` 和 AI 结果。
5. 网络、鉴权、超时、无效 JSON、无效证据或输入超限：返回 `analysis_mode="rule_fallback"` 和规则结果，`ai_message` 明确本次回退原因，不让 AI 故障导致整个文档分析失败。
6. 合并 `document.warnings` 与提取警告，确保部分 OCR 失败可见。

### 6.2 修改 `backend/app/schemas/analysis.py`

- `analysis_mode` 扩展为 `rule_based | ai_assisted | rule_fallback`。
- `DocumentInfo` 增加 `ocr_used: bool`、`ocr_pages: list[int]`。
- `CapabilitiesResponse` 增加 AI 服务商/模型名（不含 base URL 和密钥）及 `ocr_enabled`、`ocr_available`、`ocr_message`；`analysis_mode` 表示当前优先模式，配置完整时为 `ai_assisted`，否则为 `rule_based`。
- 新增连接测试响应模型：`success/message/model/elapsed_ms`，不包含密钥、请求内容或原始异常。

### 6.3 增加连接测试与能力状态

- `GET /api/analysis/capabilities` 返回真实配置和 OCR 状态，不在该 GET 请求中调用外部模型或加载 OCR 执行推理。
- 新增 `POST /api/analysis/ai/test`：未配置或服务不可达均返回结构化 `success=false` 和中文原因；成功时返回模型名和耗时。
- `materials.py` 仅更新上传接口格式说明；核验算法及持久化结构保持不变。

## 7. 前端状态与文案

### 7.1 类型和 API

- `frontend/src/types.ts`：同步分析模式、OCR 文档元信息、AI/OCR 能力字段和连接测试响应类型。
- `frontend/src/api/analysis.ts`：格式错误提示加入 PNG/JPG/JPEG，新增 `testAIConnection()`；分析请求保留上传进度，并按 OCR + AI 的实际耗时调整前端超时提示。

### 7.2 上传与结果展示

- `components/ui/FileDropzone.tsx`：白名单和 `accept` 增加 `.png/.jpg/.jpeg`，更新默认提示。
- `pages/VerificationPage.tsx`：材料上传白名单、输入框 `accept` 和提示同步支持图片。
- `pages/AnalyzePage.tsx`：格式卡、流程、能力列表和上传提示改为真实能力；AI 状态根据 capabilities 展示“将调用已配置模型”或“未配置，使用规则”，OCR 展示本地可用状态。
- 外部模型已配置时，上传区明确提示“文档文本会发送到所配置模型服务”；未配置时才声明不发送第三方。OCR 始终说明为本地识别。
- `components/analysis/AnalysisResultView.tsx`：按 `ai_assisted/rule_based/rule_fallback` 显示不同徽标、标题和说明；展示 OCR 页码，删除“本阶段未调用”等旧文案。
- `components/analysis/FieldCard.tsx`：根据分析模式将无直接证据的归纳标为“规则推断”或“模型归纳”；保留四态可信度和人工核实声明。

### 7.3 设置与旧状态清理

- `pages/SettingsPage.tsx`：显示服务商、模型名、密钥“已配置/未配置”状态（不显示值）、OCR 状态，并提供“测试连接”按钮及耗时/错误反馈。
- 隐私说明改为分情况描述：业务记录和 OCR 在本机；配置外部 AI 后，智能分析所需文本会发送给该服务，材料规则核验仍不调用 AI。
- 更新 `components/layout/Sidebar.tsx`、`lib/version.ts`、`pages/DashboardPage.tsx` 中“规则版/仅本地规则”等过时展示为不虚夸的“AI + 本地 OCR（支持规则回退）”含义。
- 不新增设置页密钥表单，不改变现有演示数据和业务页面结构。

## 8. 测试与验收

### 8.1 新增离线自动化测试 `backend/tests/test_ai_ocr.py`

使用 `unittest.mock`，默认不访问真实外部模型：

AI 测试：

- 未配置时只走规则；有效 mock JSON 返回 `ai_assisted`，且证据文本/页码/位置等于本地 `Segment`。
- 超时、鉴权/连接错误、非 JSON、缺字段、非法字段键、越界 `segment_id`、缺证据、输入超限均返回 `rule_fallback`，规则内容保持可用。
- 连接测试成功/失败响应不含密钥；日志和接口不包含 secrets。

OCR 测试：

- mock RapidOCR 验证 PNG/JPG/JPEG 可生成带 OCR 定位的片段；损坏图片、伪装扩展名、超像素、空识别结果有明确错误。
- 原生文本 PDF 不调用 OCR；扫描 PDF 调用 OCR；混合 PDF 保留原生文本并合并 OCR 页；页数/像素限制生效。
- OCR 禁用或失败时，纯扫描件明确报错，部分可读文档带警告回退。
- 通过材料上传/核验路径验证 OCR 文本可进入现有关键词规则，不改变 `verification.source="rule"`。

运行完整回归：

```powershell
python -m unittest discover -s tests -v
```

必须保持原有 108 项测试通过，并补齐新增用例；若旧测试因默认环境配置触发 AI/OCR，使用 mock/环境隔离修正测试，不放宽业务校验。

### 8.2 前端构建与静态检查

```powershell
npm run build
```

检查三种模式、AI 测试连接状态、OCR 页码、图片上传提示和隐私说明，无“未接入/不支持 OCR/本阶段未调用”等残留误导文案。

### 8.3 本地真实冒烟

- 使用临时中文 PNG、JPG 和扫描 PDF 各一份执行真实 RapidOCR，确认识别文本进入分析及材料核验；不上传用户现有正式材料，不修改正式数据库。
- 若环境中已有有效 `AI_BASE_URL/AI_MODEL`（及需要时的密钥），执行一次连接测试和一次小文档真实分析，核对模式、证据和回退；没有可用配置时明确记录“未执行真实 AI 冒烟”，不以 mock 冒充真实服务。
- 最终核对 `backend/data/taskradar.db` 和正式 uploads 未因测试改变，且不输出任何 `.env` 密钥内容。
