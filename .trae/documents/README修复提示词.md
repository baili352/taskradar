# TaskRadar README 与代码对齐修复 · 执行提示词

> 用途：交付给 AI 编程工具（TRAE / Claude Code / Cursor 等）执行。
> 目标文件：`README.md`（项目根目录）。只改这一个文件。

---

## 角色

你是本项目的资深全栈工程师兼技术文档负责人。你写文档的原则是：**每一句都能在代码里被验证，验证不了就不写**。

## 任务

`README.md` 当前停在「第四阶段第四步 · 智能提醒与风险预警系统」，并明确宣称"不接入大模型""本阶段不调用任何大模型"，但代码实际已经完成了大模型接入、本地 OCR、总览统计接口、演示数据系统，数据库 `schema_version` 已到 6。请把 README 全量重写为与当前代码完全一致的状态。

**只允许修改 `README.md`。不得修改任何代码、配置、`.env`、数据库或测试文件。**

---

## 第一步：事实采集（必须真实读代码，禁止凭印象）

按顺序执行，把结果作为重写依据：

1. 读 `backend/app/main.py`，确认全部已注册路由及其 `api_prefix`。
2. 逐个读 `backend/app/api/routes/*.py`，从 `@router.get/post/patch/delete` 装饰器提取**真实的 方法 + 路径 + summary**，形成接口总表（这是文档里接口表的唯一来源）。
3. 读 `backend/app/db/database.py`：确认 `SCHEMA_VERSION` 的实际值，并逐个 migration 分支确认每次新增/变更了哪些表与列（尤其 `is_demo`）。
4. 读 `backend/app/core/config.py` 与 `backend/.env.example`，列出全部 `AI_*` 与 `OCR_*` 配置项及默认值。
5. 执行 `find backend/app -name "*.py" | sort` 与 `find frontend/src -type f | sort`，用真实输出重建目录树。
6. 读 `frontend/src/config/navigation.ts`，确认导航条目**实际数量**与页面 key。
7. 读 `frontend/src/lib/version.ts`，取 `APP_VERSION` 与 `APP_STAGE`。
8. 读 `backend/app/services/ai/`（client/analyzer）、`backend/app/services/documents/ocr_engine.py`、`image_reader.py`、`pdf_reader.py`、`validators.py`、`backend/app/services/demo/seed.py`，确认真实行为边界与限制参数。
9. 读 `backend/tests/` 的文件清单和 `e2e_tests/E2E测试报告.md`、`e2e_tests/第五阶段第三步_UX打磨报告.md`，取可核对的测试口径。

## 第二步：必须修正的过时表述（逐条替换，改完自查无残留）

| 现 README 的错误表述 | 正确做法 |
| --- | --- |
| 头部"当前进度：第四阶段第四步" | 改为代码真实最新阶段（AI + 本地 OCR + 演示数据 + 总览统计） |
| "仍不接入大模型""本阶段不调用任何大模型""已配置但尚未调用" | 全部删除/改写为真实调用逻辑与三态说明 |
| 格式表只有 PDF / DOCX / TXT | 补充 `PNG / JPG / JPEG`（本地 OCR），并补 OCR 定位"第 N 页（OCR）" |
| "`schema_version` 由 4 升级为 5" | 改为真实版本号，并补 5 → 6 的 `is_demo` 迁移说明 |
| "左侧显示六个导航入口" | 改为 `navigation.ts` 的实际条目数（含新增页面） |
| 目录结构缺 `services/ai/`、`services/demo/`、`ocr_engine.py`、`image_reader.py`、`routes/dashboard.py`、`routes/demo.py`、前端 `api/dashboard.ts`、`api/demo.ts` | 按 `find` 真实输出补齐 |
| "已完成 / 尚未开发"清单 | 按代码重写，已实现项移到已完成，未实现项保留但只写真没做的 |
| 测试结果表（42/42、16/16…） | 换成可核对的真实口径，标注测试日期与来源报告 |

## 第三步：新增章节（按现有中文风格续写）

1. **大模型接入**：OpenAI 兼容 `chat/completions`；`AI_BASE_URL` + `AI_MODEL` 即视为已配置（支持无密钥 Ollama）；`analysis_mode` 三态 `rule_based / ai_assisted / rule_fallback`；模型只返回候选值与 `segment_id`，证据由后端从本地 Segment 重建；`segment_id` 越界或结构非法时整份 AI 结果作废并回退；输入超 `AI_MAX_INPUT_CHARS` 不截断直接回退；`POST /api/analysis/ai/test` 只发短提示不发文档；密钥只从 `.env`/环境变量读取，不落库、不进响应、不进前端状态。
2. **本地 OCR**：RapidOCR + ONNX Runtime，仅本机，不上传第三方；图片校验真实格式（不只看扩展名）、EXIF 方向、像素上限；扫描/低文本 PDF 按 `OCR_PDF_TEXT_THRESHOLD` 判定是否 OCR，超 `OCR_MAX_PAGES` 拒绝并提示拆分；OCR 失败但有原生文本时保留结果并写入 `warnings`，全程无有效文本才报错；OCR 只产出 Segment，后续规则/AI/材料核验链路不变。
3. **总览统计与演示数据**：`GET /api/dashboard/summary?demo=false` 真实 SQL 聚合；演示数据通过 `matters.is_demo` 与正式数据隔离，`GET /api/demo/status`、`POST /api/demo/seed`、`DELETE /api/demo/clear`，清理只删 `is_demo = 1`，不动正式数据。
4. **接口总表**：按第一步提取的真实装饰器重建，覆盖 health / dashboard / demo / analysis / matters / tasks / materials / risks 全部路由。

## 硬性约束

- 只写代码能验证的事实。拿不准的写"未实现"或"未验证"，**禁止编造功能、参数、数量、测试数字**。
- 不出现任何真实 API Key、Base URL、绝对本地路径、个人目录名（`D:\新建文件夹\...` 一律不写）。
- 保留原有中文语感、表格风格、`>` 引用块；保留启动步骤、常用地址、备份与恢复、常见问题。
- 不要加英文标题、徽章墙、GIF 演示、路线图等花哨内容。
- 不要留 `TODO`、`待补充`、`（此处略）`。
- 敏感能力必须按实际情况写边界：材料核验仍为本地规则，不调用 AI；核验结论不代表真实性或法律效力认定；OCR 与业务数据在本机，配置外部模型后分析文本会发送到该服务——这两句必须保留且准确。

## 自检（改完逐项执行，全部通过才算完成）

1. `grep -n "不接入大模型\|尚未调用\|本阶段不调用\|六个导航入口" README.md` → 0 命中。
2. 文档接口总表的每一条，都能在 `backend/app/api/routes/` 中找到对应装饰器；反向检查无遗漏路由。
3. 文档目录树与实际 `find` 输出逐项对照，无多写、无漏写。
4. 文档中的 `schema_version` 等于 `database.py` 的 `SCHEMA_VERSION`；`APP_VERSION` 与 `version.ts` 一致。
5. 文档中的页面数量等于 `navigation.ts` 的条目数。
6. 文档中出现的每个 `AI_*` / `OCR_*` 变量都存在于 `config.py`，默认值一致。
7. 可选验证：`python -m unittest discover -s tests` 与 `cd frontend && npm run build`，把真实结果写进测试表；跑不起来就如实写"本次未复跑"，不许沿用旧数字。

## 输出要求

1. 直接整文重写 `README.md`，结构清晰、无占位符。
2. 回复中列出：修正的过时表述清单、新增章节、删除的章节（如有）、以及**无法从代码确认而选择不写**的内容。
