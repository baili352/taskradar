# 第五阶段第三步：用户体验与参赛版本打磨报告

- 产品：办事雷达 TaskRadar AI
- 定位：AI 智能事项拆解与材料核验平台（当前为本地规则版）
- 日期：2026-11-15
- 验收环境：隔离后端 `http://127.0.0.1:8031`（临时数据库与上传目录）、隔离前端 `http://127.0.0.1:5180`
- 正式数据：`backend/data/taskradar.db` 未被修改（修改时间仍为 2026-11-13，迁移仅在副本上验证）
- 自动化测试：后端 108 项单元测试全部通过

## 一、修改文件清单

### 后端

| 文件 | 修改内容 |
| --- | --- |
| `backend/app/db/database.py` | 结构版本 5 → 6；新增 `matters.is_demo` 列；新增事务内迁移与迁移前备份触发条件 |
| `backend/app/db/matters.py` | 事项读取与返回增加 `is_demo` |
| `backend/app/db/tasks.py` | 任务查询改为关联事项，返回 `is_demo`；列表查询列名限定表别名 |
| `backend/app/db/materials.py` | 材料查询增加 `is_demo` |
| `backend/app/db/risks.py` | 风险查询增加 `is_demo` |
| `backend/app/schemas/matter.py` | `MatterRecord.is_demo` |
| `backend/app/schemas/task.py` | `TaskRecord.is_demo` |
| `backend/app/schemas/material.py` | `MaterialRecord.is_demo` |
| `backend/app/schemas/risk.py` | `RiskRecord.is_demo` |
| `backend/app/schemas/dashboard.py` | 新增：总览统计与演示数据状态响应模型 |
| `backend/app/db/dashboard.py` | 新增：按 `is_demo` 隔离的真实统计 SQL 聚合 |
| `backend/app/api/routes/dashboard.py` | 新增：`GET /api/dashboard/summary?demo=false` |
| `backend/app/api/routes/demo.py` | 新增：演示数据状态、初始化、清理接口 |
| `backend/app/services/demo/__init__.py` | 新增：演示数据服务包 |
| `backend/app/services/demo/seed.py` | 新增：三份演示通知及事项/任务/材料/风险写入与清理 |
| `backend/app/main.py` | 注册总览与演示数据路由 |
| `backend/tests/test_p3_fixes.py` | 结构版本断言同步为 6 |

### 前端

| 文件 | 修改内容 |
| --- | --- |
| `frontend/src/types.ts` | 四类记录增加 `is_demo`；新增总览与演示数据类型 |
| `frontend/src/api/dashboard.ts` | 新增：总览统计请求 |
| `frontend/src/api/demo.ts` | 新增：演示数据状态/初始化/清理请求 |
| `frontend/src/pages/DashboardPage.tsx` | 重写为真实 API 总览：范围切换、可点击统计卡、材料进度、近期截止、最近事项、空态与错误态 |
| `frontend/src/pages/SettingsPage.tsx` | 新增「参赛演示数据」管理：状态、一键初始化、清理确认弹窗 |
| `frontend/src/pages/MattersPage.tsx` | 列表与详情增加演示数据标记；更新页脚口径文案 |
| `frontend/src/pages/TasksPage.tsx` | 任务列表增加演示数据标记 |
| `frontend/src/pages/VerificationPage.tsx` | 材料列表增加演示数据标记；补充「不具备法律效力」说明 |
| `frontend/src/pages/RisksPage.tsx` | 风险详情改为「为什么出现 / 影响什么 / 下一步做什么」；演示标记；页头文案校正 |
| `frontend/src/components/analysis/FieldCard.tsx` | 字段按证据区分四态：原文明确 / 规则推断 / 待核实 / 无法判断 |
| `frontend/src/components/analysis/AnalysisResultView.tsx` | 新增四态图例与规则提取声明 |
| `frontend/src/components/layout/Sidebar.tsx` | 导航标签「演示」改为「规则版」；侧边栏说明更新为当前阶段 |
| `frontend/src/components/ui/Button.tsx` | 补充 `danger` 变体类型 |
| `frontend/vite.config.ts` | 支持 `VITE_PROXY_TARGET`，便于隔离端口测试，默认仍为 8000 |
| `frontend/src/styles.css` | 范围切换、演示横幅、可点击统计卡、进度条、四态图例、风险三问、390px 适配 |

### 验收材料

- `e2e_tests/evidence/ux_browser_report.json`：浏览器交互与 390px 检测原始数据
- `e2e_tests/evidence/screenshots/ux_*.png`：本次桌面与 390px 截图
- 本报告

## 二、页面优化说明

### 1. 总览

- 全部数字来自 `GET /api/dashboard/summary`，按 `formal / demo` 两个范围分别统计。
- 六张统计卡片：待办事项、未完成任务、未解决风险、已逾期任务、3 天内截止、待核验材料；每张卡可点击进入事项、任务、风险或材料核验页。
- 材料核验进度：材料准备百分比与核验确认百分比均按真实材料状态计算。
- 近期截止任务：只统计有明确截止来源的未完成任务，含已逾期与 7 天内截止，按天数排序。
- 最近处理的事项：按 `updated_at` 排序，显示状态与截止日期。
- 正式数据为空时显示引导（去智能分析 / 手动新建）；接口失败时显示错误与重试；演示范围未初始化时提供一键初始化。
- 页头明确标识「真实数据 / 演示数据」，演示范围顶部有黄色说明横幅。

### 2. 智能分析

- 保留上传格式、大小限制、上传进度与解析状态。
- 字段卡片根据「是否有值 + 是否有原文证据」区分四态：
  - 原文明确提取：有值且有原文证据句；
  - 规则推断：有值但无直接证据句；
  - 待核实：识别到线索但信息不完整；
  - 无法判断：原文未提供有效信息。
- 结果区新增四态图例，并明确写明「当前为本地规则提取，不是大模型语义理解」。
- 原文证据位置、材料/流程/注意事项分组与「保存为事项」入口保持不变。

### 3. 事项与任务

- 事项列表、搜索、状态/类型筛选、事项详情、截止日期来源、字段证据、生成任务均保留。
- 演示事项在列表与详情中均显示「演示数据」标记。
- 任务按事项分组、优先级筛选、状态流转、截止日期编辑与证据展示保持不变。

### 4. 材料核验

- 材料清单、上传、规则核验、人工确认、缺失提醒、事件历史均保留。
- 补充免责声明：规则核验只提供关键词线索，不代表材料真实性证明，也不具备法律效力。

### 5. 风险中心

- 每条风险详情固定展示三问：
  - **为什么出现**：规则判断原因与补充说明；
  - **影响什么**：按风险类型说明可能造成的后果；
  - **下一步做什么**：处理建议与关联跳转。
- 关联事项、任务、材料、判断依据、数据来源、已读/已解决状态均保留。
- 演示风险单独标记，页头不再使用「真实数据」这一与演示数据冲突的表述。

### 6. 设置

- 新增「参赛演示数据」区块：状态、数量、初始化时间、一键初始化、一键清理。
- 清理前弹出确认框，明确说明只删除演示事项及其级联数据，不影响正式数据。
- 产品定位改为「AI 智能事项拆解与材料核验平台（当前为本地规则版）」，与 AI 未接入说明保持一致。

## 三、演示数据说明

### 内容

| 演示事项 | 截止日期 | 演示重点 |
| --- | --- | --- |
| 【演示】校园开放日志愿服务活动 | 今天 +12 天 | 进行中事项、近期截止任务、材料缺失/待核验/无法判断 |
| 【演示】大学生创新创业竞赛 | 今天 -2 天（已逾期） | 逾期任务、材料冲突、缺失推荐信 |
| 【演示】区属事业单位公开招聘 | 今天 +21 天 | 5 天内投递提醒、材料待核验/不完整 |

- 共 3 个事项、10 个任务、10 项材料、17 条风险（其中 16 条未解决：高 4、中 9、低 3，1 条已解决用于展示状态流转）。
- 风险覆盖：逾期、即将截止、任务积压、材料缺失、待核验、不完整、冲突、无法判断。
- 演示材料文件写在 `uploads/demo/`，清理时整体删除。

### 隔离与安全

- 演示事项统一写入 `matters.is_demo = 1`，正式数据为 `0`；所有新增统计与列表标记均按此字段区分。
- 初始化：`POST /api/demo/seed`，幂等，已存在时不重复写入。
- 清理：`DELETE /api/demo/clear`，只删除 `is_demo = 1` 的事项，任务、材料、风险按外键级联删除，不执行正式数据风险同步。
- 演示数据初始化前后，正式事项/任务/风险统计完全一致（已通过 API 与浏览器两轮验证）。
- 演示数据不包含任何用户数量、节省时间、准确率或企业案例数据。

## 四、390px 手机端测试结果

测试方式：Edge headless + CDP，设备指标 390 × 844，DPR 2，逐页读取 `scrollWidth` 与元素边界。

| 页面 | 页面宽度 | 横向溢出 | 越界元素 | 控制台错误 |
| --- | --- | --- | --- | --- |
| 总览（演示） | 390 | 无（scrollWidth=390） | 0 | 0 |
| 导航抽屉 | 248px 宽，完全位于视口内 | 无 | 0 | 0 |
| 智能分析（上传区） | 390 | 无 | 0 | 0 |
| 我的事项 | 390 | 无 | 0 | 0 |
| 事项详情 | 390 | 无 | 0 | 0 |
| 任务中心 | 390 | 无 | 0 | 0 |
| 材料核验 | 390 | 无 | 0 | 0 |
| 风险中心 | 390 | 无 | 0 | 0 |
| 风险详情弹窗 | 390 | 无 | 0 | 0 |
| 设置 | 390 | 无 | 0 | 0 |
| 清理确认弹窗 | 390 | 无 | 0 | 0 |

其他检查：

- 正式/演示范围切换按钮在 390px 下单行显示，不再换行。
- 操作按钮在窄屏下自动换行或均分宽度，未被遮挡。
- 表格类内容在窄屏下转为卡片布局，无横向滚动。
- 任务卡片、风险详情、演示横幅、空态引导均完整可见。

## 五、前端构建结果

命令：`npm run build`（`tsc --noEmit && vite build`）

- 类型检查通过，无 TypeScript 错误。
- 构建成功，产物：
  - `dist/index.html` 591 B
  - `dist/assets/index-Bj7y0hIv.js` 287,640 B
  - `dist/assets/index-CcAVaw6Y.css` 43,331 B

## 六、浏览器交互结果

使用 Edge headless 真实渲染并执行以下交互：

1. 打开总览：正式数据为空，显示引导与入口。
2. 进入设置：点击「初始化演示数据」，等待出现「演示数据已就绪」。
3. 返回总览：切换到「演示数据」，出现演示横幅；统计卡片显示 3 个事项 / 8 个未完成任务 / 16 条未解决风险 / 2 个逾期 / 1 个 3 天内截止 / 2 项待核验材料。
4. 打开我的事项与事项详情：演示标记、字段证据、任务入口正常。
5. 打开任务中心：分组、优先级、截止来源正常。
6. 打开材料核验与材料详情：清单、核验区、免责声明正常。
7. 打开风险中心与风险详情：「为什么出现 / 影响什么 / 下一步做什么」完整显示。
8. 390px 下打开导航抽屉、风险详情、设置清理确认弹窗，均可正常操作。
9. 通过接口清理演示数据后，总览演示范围回到空态，正式统计与清理前一致。
10. 全程控制台错误：0 条。

原始数据见 `e2e_tests/evidence/ux_browser_report.json`。

## 七、修改前后截图

修改前（第五阶段第二步 E2E 留存的旧界面）：

- `screenshots/e2e_matters_after_refresh.jpg` — 事项页
- `screenshots/e2e_tasks_after_edit.jpg` — 任务页
- `screenshots/e2e_material_detail_before_confirm.jpg` — 材料详情
- `screenshots/e2e_risks_read_filter.jpg` — 风险页

修改后（本次）：

- 桌面：`ux_dashboard_demo_desktop.png`、`ux_dashboard_real_empty_desktop.png`、`ux_analyze_desktop.png`、`ux_matters_demo_desktop.png`、`ux_matter_detail_demo_desktop.png`、`ux_tasks_demo_desktop.png`、`ux_verification_demo_desktop.png`、`ux_material_detail_demo_desktop.png`、`ux_risks_demo_desktop.png`、`ux_risk_detail_demo_desktop.png`、`ux_settings_before_desktop.png`、`ux_settings_demo_desktop.png`
- 390px：`ux_m_dashboard_demo.png`、`ux_m_dashboard_real_empty.png`、`ux_m_drawer.png`、`ux_m_analyze.png`、`ux_m_matters.png`、`ux_m_matter_detail.png`、`ux_m_tasks.png`、`ux_m_verification.png`、`ux_m_risks.png`、`ux_m_risk_detail.png`、`ux_m_settings.png`、`ux_m_settings_modal.png`

说明：总览、设置、智能分析页在本次改造前没有留存同尺寸截图，因此修改前仅以旧版 E2E 截图为参照；其余页面均提供前后对照。

## 八、未完成事项

1. 未接入大模型：智能分析仍为本地规则提取，四态中的「规则推断」不会产生自然语言总结。
2. 未接入 OCR：扫描件图片中的文字无法识别，只能按文件元信息与文本内容核验。
3. 无多用户、登录与权限体系，演示数据与正式数据靠 `is_demo` 字段与本地文件目录隔离。
4. 无云端同步与自动备份，数据仍保存在本机 SQLite 与上传目录。
5. 未提供 PDF/Word 原文高亮定位，证据以原文句子与位置描述展示。
6. 演示数据的风险数量会随分析规则调整而变化，不作为固定指标承诺。

---

当前版本已完成比赛现场演示所需的稳定性与一致性打磨，暂停等待人工验收。
