# 企业级 RAG 面试参考文档

> 目的：这是一份面向检索优化的参考文档，用于支持一个代表 Enterprise-grade RAG 系统构建者和维护者进行面试回答的机器人。
>
> 写作风格：中立、事实化、受来源约束，并针对分块检索进行优化。如果需要，服务层可以将中立事实转换成第一人称表达，但本源文档应保持非第一人称。

## 1. 文档范围与回答规则

### 1.1 目标读者

* 主要读者：一个由 RAG 驱动的面试机器人，用于代表面试对象回答 HR、技术、系统设计、项目和行为类问题。
* 次要读者：需要基于仓库证据追溯项目事实的人类审核者。

### 1.2 不可妥协的回答规则

1. 优先使用仓库已验证事实，而不是使用润色过但缺乏支撑的表述。
2. 当某个字段在仓库中缺失时，应明确回答：当前知识库中没有该数据。
3. 不要编造个人履历、学校经历、任职日期、薪资、团队规模或业务指标，除非这些内容在来源中明确存在。
4. 当存在不同确定性层级时，应清楚区分：

   * `已验证`：由代码、文档、计划、周报或评估产物直接支撑。
   * `推断`：基于已验证仓库证据得出的合理结论。
   * `未知`：仓库中不存在，不应猜测。
5. 对项目类问题，优先使用具体细节：

   * 目标
   * 架构
   * 技术栈
   * 职责
   * 挑战
   * 解决方案
   * 可衡量结果
6. 对系统能力类问题，要区分当前已经实现的能力和规划路线图中的能力。

### 1.3 仓库已验证来源集

| 来源                                      | 主要用途                               |
| --------------------------------------- | ---------------------------------- |
| `README.md`                             | 产品概要、本地工作流、核心技术栈                   |
| `docs/rag-system-architecture.md`       | 端到端架构与流程                           |
| `docs/知识库功能与能力范围说明.md`                  | 系统定位、能力、指标、限制                      |
| `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md` | 企业级目标状态与路线图框架                      |
| `docs/weekly-report-2026-06-04.md`      | 搜索、质量控制、发布/评估进展                    |
| `docs/weekly-report-2026-06-07.md`      | 检索质量、OCR、UX、可观测性进展                 |
| `Makefile`                              | 运维工作流、验证与发布门禁                      |
| `backend/app/rag/generators/client.py`  | Prompt、事实 grounding、格式化、token 预算行为 |

### 1.4 推荐面试回答策略

| 问题类型     | 推荐回答风格                  |
| -------- | ----------------------- |
| HR / 个人类 | 先陈述已验证背景；如果个人数据缺失，则直接说明 |
| 技术深挖     | 解释架构、取舍、失败模式和验证方式       |
| 项目影响     | 使用可用指标和里程碑证据            |
| 行为类      | 使用仓库支撑的工作方式和决策模式        |
| 路线图      | 区分已实现能力和计划能力            |

### 1.5 来源引用

* `README.md`
* `docs/rag-system-architecture.md`
* `docs/知识库功能与能力范围说明.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`

## 2. 个人背景

### 2.1 已验证职业身份

* 面试对象是一个面向企业的 RAG 平台的主要构建者、架构设计者和维护者，该平台聚焦制造业和文档密集型知识工作流。
* 仓库证据显示，其所有权覆盖后端 API、检索质量、聊天行为、文档摄取、OCR、前端门户/工作区流程、评估治理和发布验证。
* 该工作画像更接近全栈 AI 系统工程师或技术负责人，而不是狭窄的单层专家。

### 2.2 已验证领域方向

| 领域   | 仓库支撑描述                                 |
| ---- | -------------------------------------- |
| 行业重点 | 制造业与企业知识管理                             |
| 问题空间 | 企业文档搜索、基于证据的问答、SOP 生成、权限感知检索和运营知识访问    |
| 产品定位 | 私有化部署、浏览器访问、企业安全、可审计性和面向生产的检索验证        |
| 工程定位 | 可追溯回答、检索评估、运行时可观测性、发布门禁，以及访问控制下符合预期的行为 |

### 2.3 推断出的能力画像

* `推断`：在检索、产品行为和运行防护方面具备较强的系统思维。
* `推断`：能够承担跨模型行为、数据质量和 UX 的模糊产品边界。
* `推断`：强调正确性、可追溯性和部署现实性，而不是只做演示型 AI 输出。

### 2.4 未知个人数据与安全回答策略

| 字段     | 状态    | 安全机器人行为               |
| ------ | ----- | --------------------- |
| 法定全名   | 仓库中未知 | 说明当前知识库不包含已验证姓名数据     |
| 当前雇主职称 | 仓库中未知 | 通过项目所有权描述角色，而不是声称正式头衔 |
| 工作年限   | 仓库中未知 | 除非加入外部简历数据，否则避免数字化声称  |
| 所在地    | 仓库中未知 | 不猜测                   |
| 职业时间线  | 仓库中未知 | 不编造日期或雇主              |

### 2.5 示例面试问题

#### 问题：这个仓库体现的是哪类工程师？

**模型回答要点**

* 该仓库体现的是一位覆盖完整企业级 RAG 技术栈的构建者，而不是只做孤立模型 prompt 的人。
* 最强信号包括架构所有权、检索质量治理、权限感知设计、文档处理、前端/运营工作流和生产验证。
* 该工作基于企业约束，例如可审计性、角色边界、部署流程和发布证据。

#### 问题：对面试对象最可信的画像总结是什么？

**模型回答要点**

* 最适合的画像是实践型 AI 系统工程师或技术负责人。
* 仓库展示了其在后端、检索、聊天、OCR、评估、发布和运维工具方面的动手所有权。
* 最强的可见模式是将企业级 RAG 端到端产品化，而不是孤立的模型实验。

### 2.6 来源引用

* `README.md`
* `docs/知识库功能与能力范围说明.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `docs/weekly-report-2026-06-07.md`

## 3. 教育经历

### 3.1 仓库状态

* 本文档审阅的仓库材料中没有已验证的教育经历。
* 可用来源中没有明确记录大学、学位、毕业年份、正式证书列表或学术专业方向。

### 3.2 安全回答策略

1. 如果被问到教育经历，机器人应说明：当前基于仓库的知识库中没有教育数据。
2. 机器人不应根据写作风格、代码质量、领域选择或架构深度推断教育背景。
3. 如果后续加入外部简历数据，应只用已验证事实替换本节。

### 3.3 未来简历同步的建议补充字段

| 字段     | 当前状态 | 推荐未来来源            |
| ------ | ---- | ----------------- |
| 学位     | 缺失   | 外部简历或 LinkedIn 导出 |
| 学校     | 缺失   | 外部简历或个人资料文档       |
| 毕业年份   | 缺失   | 外部简历              |
| 证书     | 缺失   | 简历或证书列表           |
| 正式研究背景 | 缺失   | 作品集或论文列表          |

### 3.4 示例面试问题

#### 问题：有哪些教育信息可用？

**模型回答要点**

* 当前基于仓库的来源集中不包含已验证教育数据。
* 当前知识库在项目和系统证据方面很强，但不覆盖个人学术经历。

### 3.5 来源引用

* `README.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`

## 4. 技能与技术

### 4.1 技术技能图谱

| 技能领域            | 已验证技术                                                                   | 证据                                                                                              |
| --------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 后端 API          | FastAPI、Python 3.11、Pydantic、服务层设计                                      | `README.md`、仓库地图、endpoint/service 结构                                                            |
| 前端              | React、Vite、门户/工作区界面                                                     | `README.md`、仓库地图、周报                                                                             |
| 检索 / RAG        | Qdrant、BM25、混合检索、rerank hooks、query routing、prompt budget               | `docs/知识库功能与能力范围说明.md`、`docs/rag-system-architecture.md`、`backend/app/rag/generators/client.py` |
| LLM 技术栈         | OpenAI-compatible 接口、Qwen 系列模型、基于证据的答案生成                                | `docs/知识库功能与能力范围说明.md`、`backend/app/rag/generators/client.py`                                   |
| 排序 / Embeddings | BGE-M3、BGE-Reranker-v2-m3                                               | `docs/知识库功能与能力范围说明.md`                                                                          |
| 摄取              | PDF、DOCX、PPTX、XLSX 解析、OCR、chunking、异步处理                                 | `docs/知识库功能与能力范围说明.md`、周报                                                                       |
| OCR             | PaddleOCR、扫描 PDF/图片处理、表格识别                                              | `docs/知识库功能与能力范围说明.md`、周报                                                                       |
| 数据 / 存储         | PostgreSQL、Redis、Celery、文件支撑和 DB 支撑的混合状态                                | `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`、`README.md`                                             |
| 基础设施 / 部署       | Docker Compose、本地/远程运行时工作流、健康检查                                         | `README.md`、`Makefile`                                                                          |
| 质量 / 评估         | verified frozen samples、optimization cases、发布门禁、回归工作流                   | `docs/知识库功能与能力范围说明.md`、`Makefile`、文档中的 `eval/README.md` 引用                                      |
| 可观测性            | request traces、request snapshots、event logs、health checks、Prometheus 方向 | `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`、周报                                                      |

### 4.1.1 具体模块所有权信号

| 能力            | 主要入口文件                                                                                                                     | 面试中能证明什么                          |
| ------------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 检索 API        | `backend/app/api/v1/endpoints/retrieval.py`、`backend/app/schemas/retrieval.py`、`backend/app/services/retrieval_service.py` | 所有权不只是概念层面，而是覆盖公开 API、schema 和编排层 |
| 聊天 API        | `backend/app/api/v1/endpoints/chat.py`、`backend/app/schemas/chat.py`、`backend/app/services/chat_service.py`                | 工作包含基于证据的答案服务，而不仅是离线检索研究          |
| 引用流水线         | `backend/app/services/chat_citation_pipeline.py`                                                                           | 引用质量被视为一等答案契约                     |
| 聊天记忆          | `backend/app/services/chat_memory_service.py`                                                                              | 追问行为是显式工程化的，而不是完全交给模型             |
| Query routing | `backend/app/services/retrieval_query_router.py`、`backend/app/services/query_profile_service.py`                           | Query 意图和模式选择属于系统设计的一部分           |
| 访问策略          | `backend/app/services/retrieval_scope_policy.py`、auth 相关 endpoint/service 层                                                | 检索范围是策略驱动的，而不只是 UI 约定             |
| 摄取            | `backend/app/services/ingestion_service.py`、`backend/app/rag/parsers/document_parser.py`                                   | 真实语料处理属于核心所有权                     |
| Chunking      | `backend/app/rag/chunkers/text_chunker.py`、`backend/app/rag/chunkers/structured_chunker.py`                                | 检索质量工作延伸到 rerank 和 prompting 之前   |
| OCR           | `backend/app/rag/ocr/client.py`                                                                                            | 技术栈支持扫描件和图片密集型来源材料                |
| 向量存储          | `backend/app/rag/vectorstores/qdrant_store.py`                                                                             | 系统不只是 prompt 驱动，还包含检索基础设施工作       |
| Reranking     | `backend/app/rag/rerankers/client.py`、retrieval rerank services                                                            | 排序质量被显式优化并可诊断                     |
| 系统配置          | `backend/app/api/v1/endpoints/system_config.py`、`backend/app/services/system_config_service.py`                            | 运行时控制被暴露为可管理的产品配置                 |
| 运维 / 诊断       | `backend/app/api/v1/endpoints/logs.py`、`traces.py`、`request_snapshots.py`、`ops.py`                                         | 生产调试和运营工作流被设计进产品                  |

### 4.1.2 具体运行时与产品界面

| 界面                   | 已验证文件 / 路由                                                                                 | 面试价值                       |
| -------------------- | ------------------------------------------------------------------------------------------ | -------------------------- |
| Workspace shell      | `frontend/src/App.tsx`、`frontend/src/pages/*`                                              | 证明存在内部运营/管理员工作流，而不仅是终端用户聊天 |
| Portal experience    | `frontend/src/portal/*`                                                                    | 展示外部或员工侧产品 UX 工作           |
| Admin/config surface | `frontend/src/pages/AdminPage.tsx`                                                         | 展示运行时可调性，而不是硬编码实验室设置       |
| Health and ops       | `/api/v1/health`、`/api/v1/ops`、`/api/v1/logs`、`/api/v1/traces`、`/api/v1/request_snapshots` | 支撑关于可观测性和可支持性的强回答          |

### 4.1.3 具体命令级工程信号

| 命令 / 门禁                            | 作用                                                   | 面试中为什么重要                  |
| ---------------------------------- | ---------------------------------------------------- | ------------------------- |
| `make verify-retrieval-focused`    | 对单个 case 或 fix 运行窄范围检索验证                             | 展示调试质量问题的快速内循环            |
| `make verify-retrieval-quick`      | 在不进行完整 live replay 的情况下运行治理导向快速检查                    | 展示快速验证与最终签署之间的分离          |
| `make verify-retrieval-release`    | 运行仓库原生检索发布验证包                                        | 强力证明有纪律化发布门禁              |
| `make verify-v1-release-readiness` | 在检索、优化、门户证据、摄取/OCR、健康和 waiver policy 上运行更广泛的 V1 就绪检查 | 证明跨界面就绪，而不是孤立模型评估         |
| `make snapshot-governance-rolling` | 报告已提交 snapshot/governance/rolling 对齐情况               | 展示语料治理和证据维护               |
| `make portal-chat-browser-smoke`   | 对门户聊天运行聚焦浏览器 smoke                                   | 展示前端可见 AI 行为也被验证，而不仅是单元测试 |
| `make agent-runtime-bridge`        | 启动本地运行时 HTTP bridge                                  | 展示主应用之外的工具化/产品化能力         |

### 4.2 仓库行为体现出的工程优势

* 面向企业 AI 应用的端到端系统设计。
* 强 grounding 和引用意识，而不是通用 LLM-only 答案生成。
* 关注权限感知检索和租户/部门边界。
* 通过样本治理和发布门禁工作流体现质量度量纪律。
* 通过 traces、snapshots、replay 和运维 Make targets 体现生产化调试能力。
* 愿意同时改进产品 UX 和模型质量，而不是把二者割裂。

### 4.3 架构推理模式

| 模式         | 仓库证据                                                               |
| ---------- | ------------------------------------------------------------------ |
| 偏好显式防护栏    | Grounding gates、拒答行为、发布验证包                                         |
| 偏好可观测工作流   | Health endpoints、traces、snapshots、周度运营报告                           |
| 偏好渐进加固而非重写 | 执行计划明确说明不重写整个技术栈                                                   |
| 偏好策略分离     | 区分 auth、retrieval policy、direct-resource access 和 release truth    |
| 偏好可度量质量    | 使用 verified samples、optimization cases 和 focused regression checks |

### 4.4 示例面试问题

#### 问题：这项工作最强的技术能力是什么？

**模型回答要点**

* 企业级 RAG 架构是最清晰的核心能力。
* 该技术栈还展示了较强的后端工程、检索质量工作、AI 产品集成和发布/运维成熟度。
* 这项工作的亮点在于把模型行为、文档处理、安全边界、评估和 UX 结合起来，而不是只优化单一层。

#### 问题：这个画像更偏研究还是产品？

**模型回答要点**

* 可见证据更偏产品和系统，而不是研究论文导向。
* 仓库反复强调运行时行为、发布门禁、可观测性、访问控制和可部署工作流。
* 检索质量被当作带有可衡量门禁的工程纪律，而不是只做抽象 benchmark。

### 4.5 来源引用

* `README.md`
* `docs/rag-system-architecture.md`
* `docs/知识库功能与能力范围说明.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `docs/weekly-report-2026-06-04.md`
* `docs/weekly-report-2026-06-07.md`
* `Makefile`
* `backend/app/rag/generators/client.py`

## 5. 项目：Enterprise-grade RAG 平台

### 5.1 项目总结

Enterprise-grade RAG 是一个基于浏览器、支持私有化部署的知识系统，用于企业文档检索、基于证据的问答和 SOP 生成。仓库将该产品定位为面向制造业和文档密集型运营环境的企业级 AI 知识层，并重点强调引用可追溯性、权限感知检索和可衡量的发布质量。

### 5.2 项目目标

1. 集中管理来自技术手册、维护指南、合同、政策文档和运营材料的企业知识。
2. 提供由文档引用支撑的自然语言答案，而不是自由发挥的无支撑生成。
3. 执行部门和角色边界，使检索符合企业访问约束。
4. 支持多格式摄取和 OCR，使真实企业语料无需大量人工预处理即可使用。
5. 建立一个让检索质量可验证而不是被假定的发布流程。

### 5.3 产品范围

| 范围领域    | 已验证能力                                   |
| ------- | --------------------------------------- |
| 知识检索    | 使用向量 + 词法召回并结合 rerank 的混合检索             |
| 聊天回答    | 带引用支撑且支持多轮记忆的答案                         |
| 文档中心    | 上传、浏览、预览、搜索、重建和删除流程                     |
| SOP 工作流 | SOP 生成、预览、导出和版本管理                       |
| 访问控制    | JWT auth、角色感知行为、部门级隔离                   |
| 运维 / 诊断 | 健康检查、traces、snapshots、replay、logs 和发布检查 |

### 5.3.1 稳定契约与主要 API

| API / 契约                        | 产品中的角色            | 备注               |
| ------------------------------- | ----------------- | ---------------- |
| `POST /api/v1/retrieval/search` | 核心检索契约            | 仓库指导中提到的主要稳定契约之一 |
| `POST /api/v1/chat/ask`         | 主要 grounded QA 契约 | 答案生成的主聊天接口       |
| `POST /api/v1/chat/ask/stream`  | 流式聊天答案路径          | 支持实时 token 流式 UX |
| `GET /api/v1/system-config`     | 读取运行时配置           | 可调产品行为所需         |
| `PUT /api/v1/system-config`     | 更新运行时配置           | 展示管理员侧可配置性       |
| `/api/v1/health`                | 服务健康检查            | 用于运行时检查和可支持性     |

### 5.3.2 主要后端所有权地图

| 产品能力 | 主要文件                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| 检索   | `backend/app/services/retrieval_service.py`、`retrieval_query_router.py`、`query_profile_service.py`、`retrieval_scope_policy.py` |
| 聊天   | `backend/app/services/chat_service.py`、`chat_citation_pipeline.py`、`chat_memory_service.py`                                    |
| 生成   | `backend/app/rag/generators/client.py`                                                                                         |
| 文档管理 | `backend/app/services/document_service.py`                                                                                     |
| 摄取   | `backend/app/services/ingestion_service.py`、`backend/app/rag/parsers/document_parser.py`                                       |
| SOP  | `backend/app/services/sop_service.py`、`sop_generation_service.py`、`sop_version_service.py`                                     |
| 诊断   | `backend/app/services/request_trace_service.py`、`request_snapshot_service.py`、`event_log_service.py`、`ops_service.py`          |

### 5.4 核心技术栈

| 层级         | 技术栈                                       |
| ---------- | ----------------------------------------- |
| 后端         | FastAPI、Python 3.11                       |
| 前端         | React、Vite                                |
| 向量检索       | Qdrant                                    |
| 词法检索       | BM25                                      |
| 元数据 / 系统状态 | PostgreSQL、文件支撑的过渡组件                      |
| 异步处理       | Redis、Celery                              |
| Embeddings | `BAAI/bge-m3`                             |
| Reranking  | `BAAI/bge-reranker-v2-m3`                 |
| 主模型        | 通过 `vLLM` 运行的 `Qwen/Qwen2.5-14B-Instruct` |
| 备用模型       | `Qwen/Qwen3-8B`                           |
| OCR        | PaddleOCR                                 |
| 部署         | Docker Compose、本地和远程运行时工作流                |

### 5.4.1 具体模型与检索栈说明

* Embedding 模型：`BAAI/bge-m3`
* Reranker 模型：`BAAI/bge-reranker-v2-m3`
* 主回答模型：通过 `vLLM` 运行的 `Qwen/Qwen2.5-14B-Instruct`
* 备用回答模型：`Qwen/Qwen3-8B`
* 检索形态：Qdrant 向量召回 + BM25 词法召回 + RRF 风格融合 + rerank
* OCR 技术栈：PaddleOCR，并且周报中有明确的表格识别质量工作
* 前端交付形态：React + Vite，并区分 `portal` 和 `workspace` 界面

### 5.4.2 具体 Prompt 与答案控制信号

生成层不是一个薄薄的原始模型调用。`backend/app/rag/generators/client.py` 展示了若干具体答案控制规则，在面试中很有价值：

1. 模型被要求只根据检索上下文回答。
2. 最近对话可用于追问解析，但明确禁止其优先级高于检索证据。
3. 答案必须使用 Markdown 和结构化标题。
4. Prompt 要求在答案后输出 `used_context_numbers`、`used_documents` 和 `suggested_questions` 元数据。
5. `used_documents` 必须指向真实检索到的文档元数据，而不是编造标签。
6. OpenAI-compatible payload 中的 `max_tokens` 由运行时 prompt budget 控制，而不是由答案路径内部隐藏的硬编码常量控制。

### 5.5 架构概览

#### 请求流程

1. 请求通过 API endpoint 进入，并带有 request context、auth context 和用户身份元数据。
2. 系统判断是否需要使用最近对话记忆来理解追问。
3. Query understanding 和 rewrite 决定意图、实体、过滤条件和路由选择。
4. 请求被路由到多个执行路径之一：

   * 文档 QA
   * 结构化 SQL
   * 工具动作
   * 拒答 / 超出范围
5. 对文档 QA，流水线会执行 ACL-aware 过滤、混合检索、metadata refill、rerank、context compression、citation selection、grounding checks 和最终 LLM 答案生成。
6. 后处理会附加引用、验证输出形态，并记录可追踪的运行时产物，例如 conversation state 和 snapshots。

#### 具体文件级流程

1. FastAPI 入口：`backend/app/main.py`
2. V1 router 聚合：`backend/app/api/v1/router.py`
3. 检索 endpoint：`backend/app/api/v1/endpoints/retrieval.py`
4. 聊天 endpoint：`backend/app/api/v1/endpoints/chat.py`
5. 检索编排：`backend/app/services/retrieval_service.py`
6. Query routing 和 profile selection：`backend/app/services/retrieval_query_router.py` 和 `query_profile_service.py`
7. 词法/向量检索：`backend/app/rag/retrievers/lexical_retriever.py` 和 `backend/app/rag/vectorstores/qdrant_store.py`
8. Rerank 调用路径：`backend/app/rag/rerankers/client.py`
9. 答案生成：`backend/app/rag/generators/client.py`
10. Trace 和 snapshot 持久化：`backend/app/services/request_trace_service.py` 和 `request_snapshot_service.py`

#### 架构特征

* 设计不只是“LLM + 向量搜索”；它包含检索策略、记忆策略、grounding checks 和运营诊断。
* 架构明确区分文档 QA、结构化数据访问和工具动作流程。
* 仓库体现出强烈偏好：保留证据和运行时可解释性。

#### 为什么该架构值得在面试中讲

* 它展示了 endpoint、schema、orchestration、retrieval primitive 和 telemetry layers 的分离。
* 它说明系统被设计为可以解释失败，而不只是产生答案。
* 它显示系统显式支持多种任务类型：文档 QA、结构化 SQL、工具动作和拒答。

### 5.6 仓库体现出的职责

| 职责    | 描述                                                     |
| ----- | ------------------------------------------------------ |
| 系统架构  | 定义企业级目标状态和渐进加固路径                                       |
| 后端所有权 | 构建并维护 API、services、检索逻辑和生成流水线                          |
| 检索设计  | 实现混合检索、query routing、rerank hooks 和 grounding behavior |
| 摄取流水线 | 支持解析、OCR、chunking、异步摄取、重建和预览工作流                        |
| 前端/产品 | 交付与聊天、历史、搜索和文档 UX 相关的 portal 和 workspace 功能            |
| 评估纪律  | 加入已验证样本门禁、optimization-case 回归和发布工作流                   |
| 运维    | 维护健康检查、运行时脚本、验证 Make targets 和远程 bugfix 流程             |

### 5.7 关键功能能力

| 能力            | 细节                                                                         |
| ------------- | -------------------------------------------------------------------------- |
| 多格式摄取         | PDF、DOCX、PPTX、XLSX、扫描图像、OCR 辅助解析                                           |
| Grounded chat | 答案必须基于检索上下文，并可包含引用                                                         |
| 多轮记忆          | 追问可以复用最近对话上下文                                                              |
| SOP 生成        | AI 辅助 SOP 创建，带来源可追溯性和导出路径                                                  |
| 部门感知检索        | 将检索限制在允许范围内，并带有受控 supplemental behavior                                    |
| 拒答行为          | 当证据不足时，有明确的“无法回答”路径                                                        |
| 可观测性          | Health endpoints、event logs、traces、snapshots、replay                        |
| 验证            | Focused verification、release bundles、sample governance 和 regression checks |

### 5.8 可衡量结果与证据

| 指标 / 信号           | 已验证值                                                       |
| ----------------- | ---------------------------------------------------------- |
| 快速模式响应目标          | `< 3 seconds`                                              |
| 检索 top-1 accuracy | 在 `64` 个 verified frozen samples 上约 `90%-95%`              |
| 检索 top-k recall   | 在 `64` 个 verified frozen samples 上约 `98%`                  |
| 文档覆盖率             | 在 `64` 个 verified frozen samples 上约 `97%-98%`              |
| 并发目标              | `>= 30` concurrent users                                   |
| 可用性目标             | `>= 99.5%`                                                 |
| 回归治理              | `64` 个 verified frozen samples + `22` 个 optimization cases |
| 周度交付信号            | 2026-06-01 至 2026-06-06 报告中记录 `170` 次 commits              |

### 5.8.1 周报记录的具体产品进展

| 日期窗口                    | 具体进展                                                                                           |
| ----------------------- | ---------------------------------------------------------------------------------------------- |
| 2026-06-01 至 2026-06-04 | Search 以 Elasticsearch-backed full-text behavior 上线；文档质量门禁和 capability-dashboard 风格的发布决策支持得到推进 |
| 2026-06-01 至 2026-06-06 | 追问稳定性改善，聊天流式输出和历史加载得到改进，OCR 表格处理进入验证，DOCX 解析进入内部验证，Prometheus 可观测性工作推进                         |

### 5.8.2 Makefile 中的具体就绪信号

* `make verify-retrieval-release` 是标准检索发布签署门禁。
* `make verify-v1-release-readiness` 明确将签署范围从检索扩展到：

  * contract checks
  * optimization regression coverage
  * portal evidence
  * ingest / preview / delete / rebuild smoke
  * OCR server-runtime gate
  * health and waiver policy
* `make verify-retrieval-quick` 作为更快的治理检查存在，说明系统区分内循环验证和发布级证明。

### 5.9 主要挑战与解决方案

| 挑战               | 为什么重要                        | 仓库中的解决模式                                                                   |
| ---------------- | ---------------------------- | -------------------------------------------------------------------------- |
| 模糊表达下的检索质量       | 企业用户会提出宽泛、口语化或追问式问题          | 混合检索、query rewrite、query profiling、rerank、focused evaluation               |
| 引用 grounding 可靠性 | 错误引用会破坏信任                    | Grounding checks、答案形态规则、元数据纪律、拒答路径                                         |
| 部门与角色隔离          | 企业 RAG 不能泄露受限文档              | ACL-aware filtering 和 department-scoped retrieval policy                   |
| OCR 和复杂文档        | 真实语料包含扫描件、表格、混合布局和 DOCX 边界情况 | PaddleOCR、structured chunking、OCR diagnostics、fallback parsing             |
| 发布信心             | RAG 变更可能悄悄引入回归               | Verified frozen sample gates、optimization-case regressions、release bundles |
| 运营支持             | 生产调试需要的不只是日志                 | Request traces、snapshots、replay flows、health 和 ops surfaces                |

### 5.9.1 具体挑战故事

#### 挑战：宽泛或口语化问题漂移到错误文档族

* 症状类型：用户提出 overview-style 或松散表述的问题，检索可能过度加权相近但错误的标题或邻近文档族。
* 难点：这不是只靠 embedding 就能解决的，因为企业语料中常常存在高度相似的手册、SOP 和摘要。
* 仓库中的具体响应：

  * 使用混合检索，而不是 vector-only recall
  * query routing 和 query profile selection
  * metadata-anchor logic 和 document-family policies
  * 当残留问题足够重要时，将其捕获为 optimization case 以持续保护

#### 挑战：答案内容正确，但引用或 grounding 形态不可信

* 症状类型：答案看起来合理，但 citation metadata、used-document mapping 或 grounding 一致性不够强。
* 难点：企业用户往往比流畅措辞更关心答案来自哪里。
* 仓库中的具体响应：

  * citation pipeline 作为独立 service concern
  * prompt 规则要求 `used_documents` 映射到真实检索元数据
  * grounding checks 和 refusal/degrade paths
  * request snapshots 和 traces 用于事后调试

#### 挑战：噪声扫描件和复杂表格破坏下游 QA

* 症状类型：系统检索出低价值 OCR 噪声，或遗漏关键表格内容。
* 难点：表格密集型手册和扫描服务文档在制造业中很常见。
* 仓库中的具体响应：

  * OCR pipeline 改进
  * structured chunking，而不是只做固定尺寸文本切片
  * title extraction 和 content-governance checks
  * 周报中明确记录 OCR 表格识别和 DOCX 解析进展

### 5.10 该项目反映出的决策风格

* 当加固现有系统更实际时，避免重写整个技术栈。
* 将策略加固与功能扩展分离。
* 将检索质量和发布证据视为核心产品职责。
* 将可审计性和访问控制等企业约束作为一等设计输入。
* 使用 Make targets 和文档化工作流，将隐性经验转化为可重复工程实践。

### 5.11 示例面试问题

#### 问题：Enterprise-grade RAG 解决什么问题？

**模型回答要点**

* 它将大量企业文档转化为一个可搜索、带引用支撑的知识系统。
* 它为私有化部署、访问控制和答案可追溯性与原始模型流畅度同等重要的场景而设计。
* 它既支持日常知识访问，也支持 SOP 生成等结构化工作流。

#### 问题：它和简单的文档聊天机器人有什么不同？

**模型回答要点**

* 该系统包含混合检索、reranking、grounding checks、角色感知访问控制和可追踪运行时诊断。
* 它将答案质量视为需要通过门禁和回归验证的东西，而不是默认由模型质量保证。
* 它还支持文档操作、SOP 工作流和面向运营者的发布工具。

#### 问题：这个项目中的主要职责是什么？

**模型回答要点**

* 端到端所有权覆盖架构、后端服务、检索行为、文档摄取、前端界面、评估和运营验证。
* 最强的可见职责领域是检索正确性、系统防护栏和生产就绪性。

### 5.12 来源引用

* `README.md`
* `docs/rag-system-architecture.md`
* `docs/知识库功能与能力范围说明.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `docs/weekly-report-2026-06-07.md`
* `Makefile`

## 6. 项目：检索质量与评估治理

### 6.1 项目总结

该仓库最鲜明的特征之一是：检索质量被当作一个受治理的工程界面，而不只是模型输出的副作用。项目包含样本治理、已验证发布真值、focused regression paths 和 optimization-case tracking，以确保改进能够持久。

### 6.2 目标

* 建立一种可重复方式，用于衡量在语料、prompts、policies 和 runtime 演进时，检索和聊天行为是否仍然可靠。

### 6.3 问题陈述

企业 RAG 系统常常静默失败：

* 一个排序调整可能改善一个 query，同时破坏另一个 query
* 一次文档刷新可能使样本真值发生漂移
* 一次 memory 或 routing 变更可能引入答案回归，但没有明显 stack trace

该仓库通过将检索质量转换为有门禁、可审计的工作流来解决这些问题。

### 6.4 职责

| 职责                      | 描述                                                      |
| ----------------------- | ------------------------------------------------------- |
| 定义发布真值                  | Verified frozen samples 是权威发布通过/失败来源                    |
| 管理优化工作                  | 通过 optimization cases 跟踪非平凡残留问题                         |
| 构建 focused verification | 对特定修复使用 targeted replays 和 regression tests             |
| 区分成熟度层级                 | 区分 gate、governance、holdout、candidate 和 rolling evidence |
| 提升可解释性                  | 增加诊断，使失败可行动，而不是模糊不可定位                                   |

### 6.5 评估架构

1. Verified frozen samples 作为发布真值。
2. Optimization cases 表示需要持久保护的活跃或已观察到的质量问题。
3. Focused verification 用于在更广泛发布签署前验证窄范围修复。
4. Release verification bundles 组合检索、memory、ACL、diff 和 threshold checks。
5. Diagnostic artifacts 帮助判断失败是真实回归、证据漂移，还是运行时问题。

### 6.5.1 具体发布门禁组成

根据 Makefile comments 和 targets，检索与 V1 发布工作流不是单个 eval script，而是分层 bundle：

| 门禁 / 命令                            | 具体范围                                                                                                                                           |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `make verify-retrieval-focused`    | 单个 residual、单个 case 或单个窄范围修复                                                                                                                   |
| `make verify-retrieval-quick`      | 不进行完整 live replay 的治理检查                                                                                                                        |
| `make verify-retrieval-release`    | 严格检索发布门禁、verified frozen truth、optimization-case regressions、retrieval eval、chat-memory behavioral gate、ACL visibility、diff 和 threshold checks |
| `make verify-v1-release-readiness` | 检索发布加上 portal evidence、ingest-preview-delete-rebuild smoke、OCR runtime gate、health 和 waiver governance                                         |

### 6.5.2 为什么这是工程成熟度的强证据

* 系统区分探索性 debug checks 和硬发布门禁。
* 检索正确性只被视为发布就绪的一部分。
* Portal/browser evidence 和 ingest/OCR evidence 被纳入同一个运营故事，这在浅层 RAG demo 中并不常见。

### 6.6 可衡量信号

| 信号      | 已验证证据                                              |
| ------- | -------------------------------------------------- |
| 发布真值来源  | 仅使用 verified frozen samples                        |
| 已验证样本范围 | `64` 个样本                                           |
| 优化回归    | `22` 个 optimization cases                          |
| 质量目标    | 显式追踪 top-1、top-k recall 和 document coverage        |
| 验证路径    | `make verify-retrieval-release` 和 focused variants |

### 6.7 为什么这在面试中重要

* 它展示了超越“模型看起来更好了”的工程成熟度。
* 它说明对 AI 系统需要像传统软件一样建立持久回归保护。
* 它为可靠性、发布安全和质量测量相关问题提供了强回答。

### 6.8 示例面试问题

#### 问题：检索质量是如何衡量的？

**模型回答要点**

* 质量绑定到一个作为发布真值的 verified frozen sample set。
* 额外的 optimization cases 捕获活跃或历史重要的残留问题，并将其连接到可执行保护。
* 工作流支持开发期间 focused checks，以及发布签署时的 bundle-level gates。

#### 问题：什么才算“发布真值”？

**模型回答要点**

* 仓库明确说明 verified frozen samples 是检索发布唯一的发布通过/失败真值来源。
* Optimization cases 很重要，在没有保护时会阻塞，但它们不能替代 verified frozen truth。
* 这种分离防止临时判断悄悄重新定义发布标准。

#### 问题：为什么不只依赖手工测试？

**模型回答要点**

* 手工测试对探索有用，但无法扩展到重复性的回归预防。
* 仓库强调持久反回归资产，包括治理样本和可执行检查。
* 这对 RAG 系统尤其重要，因为文档漂移和排序变更可以在不改变公开 API 的情况下破坏行为。

### 6.9 来源引用

* `docs/知识库功能与能力范围说明.md`
* `docs/weekly-report-2026-06-04.md`
* `docs/weekly-report-2026-06-07.md`
* `Makefile`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`

## 7. 项目：文档摄取、OCR 与知识运营

### 7.1 项目总结

仓库展示了企业级 RAG 中困难运营侧的大量工作：文档解析、OCR、chunking 质量、异步摄取、重建和重试行为，以及对嘈杂真实语料而非干净 benchmark 数据集的支持。

### 7.2 目标

* 将异构企业文档转化为可靠的检索资产，并保留足够结构质量以支持基于证据的回答。

### 7.3 文档与内容挑战

| 挑战     | 仓库支撑描述                      |
| ------ | --------------------------- |
| 混合文档格式 | PDF、DOCX、PPTX、XLSX、图片密集型扫描件 |
| 低质量扫描件 | OCR 准确率会因噪声、倾斜或低分辨率下降       |
| 复杂表格   | 合并单元格、多级表头和密集参数表很难保留        |
| 混合布局   | 表格、图片和正文可能破坏朴素 chunking     |
| 内容噪声   | 页脚、页码和伪影会降低检索质量             |

### 7.4 实现特性

| 能力                      | 描述                                                                      |
| ----------------------- | ----------------------------------------------------------------------- |
| 原生文本提取                  | 在可行时先使用直接提取，再使用 OCR fallback                                            |
| OCR 流水线                 | PaddleOCR 用于扫描件/图片密集型页面                                                 |
| 结构化 chunking            | 使用标题层级和 block-aware splitting，而不是只使用原始 token windows                    |
| Contract-aware chunking | 支持 clause、section summary、document summary 和 table-oriented chunk types |
| 异步摄取                    | 基于 Celery 的后台处理，带状态追踪                                                   |
| 重建 / 重试                 | 支持重新处理和重试失败内容                                                           |
| 预览支持                    | 在线文档预览和来源跳转行为                                                           |

### 7.4.1 具体摄取文件地图

| 能力            | 主要文件                                             |
| ------------- | ------------------------------------------------ |
| 解析文档          | `backend/app/rag/parsers/document_parser.py`     |
| 基础 chunking   | `backend/app/rag/chunkers/text_chunker.py`       |
| 结构感知 chunking | `backend/app/rag/chunkers/structured_chunker.py` |
| 嵌入 chunks     | `backend/app/rag/embeddings/client.py`           |
| 存储向量          | `backend/app/rag/vectorstores/qdrant_store.py`   |
| 编排摄取          | `backend/app/services/ingestion_service.py`      |
| 管理文档          | `backend/app/services/document_service.py`       |
| 后台任务          | `backend/app/worker/celery_app.py`               |

### 7.4.2 仓库中提到的具体企业文档类型

* technical manuals
* maintenance manuals
* operation guides
* contracts and agreements
* policies and 制度 documents
* SOP / WI documents
* scanned PDF files
* image-heavy pages
* complex parameter tables

### 7.5 近期进展信号

* OCR 表格识别从诊断进入优化和验证。
* DOCX 解析支持达到内部验证阶段。
* 摄取质量检查和内容治理行为得到强化。
* 摄取期间加入 searchable title extraction，以改善下游发现能力。

### 7.6 仓库体现出的职责

* 提升困难企业文档上的摄取可靠性。
* 为有意义的 QA 和 SOP 生成保留足够文档结构。
* 减少低价值或噪声内容进入检索界面。
* 围绕 OCR 相关工作流加入健康检查、诊断和验证。

### 7.7 示例面试问题

#### 问题：为什么企业级 RAG 中摄取很难？

**模型回答要点**

* 真实企业语料嘈杂、异构，而且经常结构很差。
* OCR 错误、表格丢失、布局碎片化和弱 chunking 都会降低下游检索与答案质量。
* 因此，强 RAG 系统不仅需要更好的 prompt，还需要摄取、解析和内容治理工作。

#### 问题：采取了哪些实际步骤来改善文档质量？

**模型回答要点**

* 尽可能优先使用原生解析，对扫描件和图片密集页面使用 OCR fallback。
* 流水线加入结构感知 chunking、title extraction、noise cleaning 和 reprocess/retry paths。
* OCR 表格处理和 DOCX 解析被当作有验证的具体工程路线，而不是非正式未来想法。

### 7.8 来源引用

* `docs/知识库功能与能力范围说明.md`
* `docs/weekly-report-2026-06-04.md`
* `docs/weekly-report-2026-06-07.md`
* `docs/rag-system-architecture.md`

## 8. 从仓库提取的工作经验画像

### 8.1 重要说明

* 仓库没有提供包含公司名称、职称或日期的正式工作经历。
* 因此，本节描述的是由仓库证据强支撑的角色形态经验。
* 这些角色画像适合用于项目型面试回答，但不应被误认为完整简历时间线。

### 8.2 角色画像：AI 系统架构师 / 技术负责人

| 类别    | 基于证据的总结                           |
| ----- | --------------------------------- |
| 角色范围  | 端到端负责企业级 RAG 平台架构                 |
| 主要关注点 | 安全、检索正确性、发布质量、可观测性和企业可运营性         |
| 最强证据  | 执行计划、架构文档、基于 Make 的发布工作流、受治理的质量门禁 |
| 成就模式  | 将一个可运行的 RAG 技术栈逐步加固为企业平台          |

### 8.3 角色画像：全栈产品工程师

| 类别   | 基于证据的总结                                                                  |
| ---- | ------------------------------------------------------------------------ |
| 后端工作 | API endpoints、service logic、retrieval/generation paths、ingest operations |
| 前端工作 | Portal/workspace improvements、chat history、search UX、preview behavior    |
| 产品耦合 | 跨用户流程工作，而不是将模型工作与产品体验割裂                                                  |
| 成就模式 | 同时改善聊天质量、搜索可用性和运营界面                                                      |

### 8.4 角色画像：检索与评估工程师

| 类别   | 基于证据的总结                                                                      |
| ---- | ---------------------------------------------------------------------------- |
| 质量模型 | Verified frozen truth、optimization cases、focused regressions、release bundles |
| 评估思维 | 质量由治理证据衡量，而不是由轶事式 demo 成功衡量                                                  |
| 成就模式 | 构建机制来检测漂移、分类残留问题并让修复持久                                                       |

### 8.5 角色画像：平台 / 发布 / 运维工程师

| 类别    | 基于证据的总结                                                 |
| ----- | ------------------------------------------------------- |
| 运行时支持 | 本地和远程运行时工作流、健康检查、bugfix redeploy paths                  |
| 诊断工具  | Traces、snapshots、replay、event logs、verification targets |
| 运维成熟度 | 发布工作流将检索、memory、ACL、ingest 和 runtime health 连接起来        |
| 成就模式  | 缩小功能工作与可部署运营行为之间的差距                                     |

### 8.6 仓库支撑的成就亮点

1. 构建了一个面向企业的 RAG 技术栈，覆盖文档 QA、SOP 生成和文档中心工作流。
2. 使用已验证样本和 optimization-case regressions 建立可衡量检索质量门禁。
3. 改善聊天行为、追问处理和引用可靠性，而不是把 LLM 输出默认当作可信。
4. 推进 OCR、DOCX 解析和结构化文档摄取，以支持真实企业语料。
5. 通过 health、trace、replay 和基于 Make 的验证路径强化运行时可观测性与发布纪律。

### 8.6.1 具体“亲自负责了什么”回答库

当面试官问亲自负责了什么时，使用以下更具体的回答片段：

| 主题      | 具体回答片段                                                                                                          |
| ------- | --------------------------------------------------------------------------------------------------------------- |
| API 设计  | 负责检索 search、chat ask 和 system config behavior 等主要企业契约                                                           |
| 检索      | 参与 retrieval service orchestration、query routing、query profiles、rerank integration 和 scope policy               |
| 聊天质量    | 参与 citation-backed answering、follow-up handling、prompt constraints、grounding behavior 和 answer formatting rules |
| 摄取      | 参与 parsing、OCR 相关质量改进、chunking、rebuild/retry flows 和 document preview support                                   |
| 评估      | 构建或维护 verified frozen sample gates、optimization-case regression protection 和 release verification entrypoints   |
| 产品 / UX | 改善 portal search、chat behavior、history performance 和 document-center workflows                                  |
| 运维      | 增加或使用 traces、request snapshots、replay、health checks 和 remote bugfix runtime workflows                           |

### 8.7 示例面试问题

#### 问题：这里最清楚体现了哪类工作经验？

**模型回答要点**

* 最强证据指向一种混合型画像：横跨 AI 系统架构、后端工程、全栈产品交付和发布/运维加固。
* 该仓库尤其能证明其对企业级 RAG 产品化系统的所有权，而不是原型项目。

#### 问题：这项工作更偏功能交付还是基础设施加固？

**模型回答要点**

* 两者都有，但最有特色的是二者结合。
* Search、memory、SOP generation 和 document preview 等功能是在 evaluation gates、observability 和 release discipline 的同时交付的。

### 8.8 来源引用

* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `docs/rag-system-architecture.md`
* `docs/weekly-report-2026-06-04.md`
* `docs/weekly-report-2026-06-07.md`
* `Makefile`

## 9. 常见面试问答

### 9.1 HR / 通用叙事问题

#### 问题：面试中最值得讲的项目是什么？

**模型回答要点**

* 最强项目是 Enterprise-grade RAG 平台，因为它在一个系统中展示了架构、产品、AI 和运维深度。
* 它包含文档摄取、检索、基于证据的回答、SOP 生成、访问控制、可观测性和发布治理。
* 它还有可衡量质量信号，因此比纯 demo 项目更可信。

#### 问题：这项工作和标准 LLM 集成项目有什么区别？

**模型回答要点**

* 该工作超越 prompt orchestration，包含摄取质量、ACL-aware retrieval、evaluation truth、release safety 和 operator diagnostics。
* 设计由企业约束塑造，而不只是面向消费者聊天便利性。

#### 问题：这个项目暗示了什么样的影响？

**模型回答要点**

* 它暗示在知识访问速度、检索可信度、文档工作流自动化和减少发布运营不确定性方面产生影响。
* 仓库提供了检索和响应目标方面的具体技术指标，尽管没有明确记录业务 ROI 指标。

### 9.2 技术架构问题

#### 问题：系统如何回答用户 query？

**模型回答要点**

1. 请求带着 request context 和 auth context 进入。
2. 系统判断最近对话记忆是否相关。
3. Query understanding 和 rewrite 决定 route、filters 和 profile。
4. 文档 QA 请求经过 ACL filtering、hybrid retrieval、rerank、compression、citation selection、grounding checks 和 final generation。
5. 最终响应经过后处理，并与 traces 或 snapshots 一起存储以供诊断。

#### 问题：如果现场向面试官讲系统，会使用哪些文件？

**模型回答要点**

* 从 `backend/app/main.py` 和 `backend/app/api/v1/router.py` 开始，展示应用外壳和路由聚合。
* 然后进入 `backend/app/services/retrieval_service.py` 和 `chat_service.py` 讲编排。
* 使用 `retrieval_query_router.py`、`query_profile_service.py`、`lexical_retriever.py`、`qdrant_store.py` 和 `rerankers/client.py` 解释检索。
* 使用 `backend/app/rag/generators/client.py` 解释答案控制、grounding rules 和 metadata outputs。
* 最后用 `request_trace_service.py` 和 `request_snapshot_service.py` 展示调试和 replay 如何工作。

#### 问题：为什么使用混合检索，而不是只用向量搜索？

**模型回答要点**

* 企业文档包含精确标识符、标题、条款标记和领域术语，词法搜索能很好捕获这些内容。
* 当用户措辞与文档措辞不一致时，语义检索有帮助。
* 结合 vector recall、BM25、fusion 和 rerank 可以提升精确问题和模糊问题下的鲁棒性。

#### 问题：答案结构是如何控制的，而不是完全交给模型？

**模型回答要点**

* 生成客户端包含显式回答规则：Markdown 输出、标题规则、仅基于证据回答，以及答案后的 response metadata。
* Prompt 要求模型返回结构化元数据，例如 `used_context_numbers`、`used_documents` 和 `suggested_questions`。
* 系统还限制最近对话的使用方式，从而减少追问漂移。

#### 问题：如何降低幻觉风险？

**模型回答要点**

* 生成客户端要求模型只根据检索上下文回答。
* 系统使用引用行为、grounding checks，并在证据不足时明确拒答。
* Prompt 规则还强调结构化回答、证据使用和对不支持字段的清晰处理。

#### 问题：如何安全处理多轮记忆？

**模型回答要点**

* 最近对话用于追问解析，但不允许覆盖检索证据。
* Prompt guidance 明确说明，最近轮次用于理解追问，而不是替代 grounded context。
* 这降低了对话惯性变成虚假证据的概率。

#### 问题：权限如何执行？

**模型回答要点**

* 系统使用基于 JWT 的 auth 和角色感知行为。
* 检索在答案生成前应用访问过滤，而不是在检索后简单裁剪。
* 部门隔离被视为设计约束，而不是可选 UI 行为。

### 9.3 项目执行与质量问题

#### 问题：如何建立发布信心？

**模型回答要点**

* 仓库使用基于 Make 的验证包，将检索、memory、ACL 和其他检查组合起来。
* Verified frozen samples 作为发布真值。
* Optimization cases 提供一种方式，将重要残留问题纳入持久回归保护。

#### 问题：哪些具体命令能证明项目被生产化？

**模型回答要点**

* `make verify-retrieval-release` 用于检索发布签署。
* `make verify-v1-release-readiness` 用于更广泛的产品就绪。
* `make snapshot-governance-rolling` 用于语料/治理一致性检查。
* `make portal-chat-browser-smoke` 用于用户可见 portal 行为。
* `make remote-bugfix-portal-readiness` 及相关远程运行时命令用于部署相邻验证。

#### 问题：如何调试回归？

**模型回答要点**

* 系统保留 request traces、snapshots、replay paths 和 focused verification commands。
* 这使得检索和答案行为可以基于证据调试，而不是只依靠通用日志。

#### 问题：这个项目中最难的工程问题是什么？

**模型回答要点**

* 仓库暗示，最难的问题不是单个模型性能，而是噪声文档、检索排序、访问控制、记忆行为和 grounding 可靠性之间的相互作用。
* 这也是为什么大量工作投入到 evaluation gates、diagnostics 和 structured ingestion。

### 9.4 产品与路线图问题

#### 问题：哪些已经实现，哪些仍在计划？

**模型回答要点**

* 已实现能力包括文档上传、OCR-enabled ingestion、hybrid retrieval、citation-backed chat、SOP generation、preview、access control 和核心 diagnostics。
* 计划中或部分设计的领域包括更深层监控、缓存层、更丰富的企业集成，以及围绕 durable storage 和 platform governance 的部分运营加固。

#### 问题：下一步高价值改进是什么？

**模型回答要点**

* 强化 durable system-of-record ownership in storage。
* 扩展可观测性和 dashboards。
* 持续改进困难边界 case 的检索质量，例如多文档歧义和复杂表格密集型文档。
* 在保留策略边界的同时深化企业集成。

### 9.5 来源引用

* `docs/rag-system-architecture.md`
* `docs/知识库功能与能力范围说明.md`
* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `Makefile`
* `backend/app/rag/generators/client.py`

## 10. 行为类与场景回答

### 10.1 行为回答风格

* 推荐风格：简洁的 STAR-like 结构。
* 语气：冷静、事实化、强调所有权，并基于证据。
* 重点：决策方式、取舍、调试方法和可衡量结果。

### 10.2 场景：存在多个可能失败源的模糊问题

| 维度 | 模型回答要点                                                                   |
| -- | ------------------------------------------------------------------------ |
| 情境 | 一个 RAG 答案可能因为文档质量、检索排序、prompt 行为、memory scope 或 permission filtering 而失败 |
| 任务 | 避免浅层修复，并定位真实失败源                                                          |
| 行动 | 在改代码前使用 traces、snapshots、focused verification 和 route-by-route analysis  |
| 结果 | 产生更小的修复、更低的回归风险和更好的长期信心                                                  |

### 10.2.1 具体 STAR 版本

* 情境：portal 或 chat 答案错误，但根因可能在 OCR、chunking、retrieval routing、rerank、prompt behavior 或 permission scope。
* 任务：确定精确失败层，而不是交付表面化的 prompt-only 修复。
* 行动：检查 request traces 和 snapshots，通过 focused verification replay 该 case，并在修改代码前确认正确的 document、chunk 和 citation 是否存在。
* 结果：修复更窄、更有依据，也更容易用回归覆盖保护。

### 10.3 场景：在不牺牲可靠性的情况下交付功能

| 维度 | 模型回答要点                                                |
| -- | ----------------------------------------------------- |
| 情境 | 新 AI 功能容易 demo，但也可能静默破坏已有企业行为                         |
| 任务 | 保持交付推进，同时保留发布信心                                       |
| 行动 | 增加 focused verification，用治理样本保护重要残留问题，并将实现过程与最终发布签署分离 |
| 结果 | 本地迭代更快，发布时信心更强                                        |

### 10.3.1 具体 STAR 版本

* 情境：chat、search 或 document workflows 中的功能工作可能意外降低检索质量或答案 grounding。
* 任务：保持 startup-style 团队的功能速度，但不接受“某次 demo 看起来可以”作为证明。
* 行动：实现期间使用 focused checks，然后将最终信心绑定到 release-gate commands 和治理证据。
* 结果：仓库同时支持快速迭代和更严格的发布姿态。

### 10.4 场景：处理低质量或嘈杂数据

| 维度 | 模型回答要点                                                                                                   |
| -- | -------------------------------------------------------------------------------------------------------- |
| 情境 | 企业文档包含扫描件、低质量 OCR、复杂表格和不一致布局                                                                             |
| 任务 | 即使源材料不完美，也要让系统可用                                                                                         |
| 行动 | 加入 structure-aware chunking、OCR validation、fallback parsing、title extraction 和 content-governance checks |
| 结果 | 更好的检索 grounding 和更少的下游答案噪声                                                                               |

### 10.4.1 具体 STAR 版本

* 情境：企业手册和扫描 PDF 经常包含表格密集页面、重复页眉/页脚和低价值 OCR artifacts。
* 任务：阻止这些噪声污染检索和答案生成。
* 行动：改善 parsing paths，强化 chunk structure，验证 OCR-heavy scenarios，并加入 content-governance 和 rebuild/retry workflows。
* 结果：证据选择更稳定，答案被噪声或弱 chunk 锚定的概率降低。

### 10.5 场景：平衡产品 UX 与模型正确性

| 维度 | 模型回答要点                                                                                               |
| -- | ---------------------------------------------------------------------------------------------------- |
| 情境 | 用户会同时通过正确性和界面流畅度来判断 AI 质量                                                                            |
| 任务 | 提升信任，而不是把 UX 和模型质量当成两条分离路线                                                                           |
| 行动 | 同时改进 answer flow、history performance、search usability、preview behavior 和 citation-backed correctness |
| 结果 | 得到一个更可信、更可用的产品，而不仅是更好的离线模型分数                                                                         |

### 10.6 场景：决定不进行过度工程化

| 维度 | 模型回答要点                                |
| -- | ------------------------------------- |
| 情境 | 大型 AI 系统容易诱发过早重写和投机式抽象                |
| 任务 | 在不丢失现有产品价值的情况下提升企业就绪度                 |
| 行动 | 渐进加固现有技术栈，保持每个阶段可运行，并将核心策略修复与未来功能扩展分离 |
| 结果 | 进展更可靠，迁移风险更低                          |

### 10.7 示例行为类问题

#### 问题：如何处理困难 bug？

**模型回答要点**

* 先判断问题来自数据质量、检索、routing、memory 还是 generation。
* 在编辑代码前，使用 traces、snapshots 和 focused checks 确认假设。
* 优先使用外科手术式修复加持久回归覆盖，而不是大范围重写。

#### 问题：这个项目如何管理取舍？

**模型回答要点**

* 仓库显示出多次在速度和严谨之间做取舍，并且通常通过本地快速 focused iteration + 发布时更严格 bundled checks 来解决。
* 另一个反复出现的取舍是模型流畅度和证据忠实度；系统明确偏向 grounded、auditable answers。

#### 问题：有哪些领导力或所有权信号？

**模型回答要点**

* 仓库体现出对架构方向、质量门禁和运营工作流的所有权，而不只是孤立 ticket 完成。
* 周报和执行计划展示了持续优先级排序、系统加固和跨产品界面的协调。

### 10.8 来源引用

* `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`
* `docs/weekly-report-2026-06-04.md`
* `docs/weekly-report-2026-06-07.md`
* `Makefile`

## 11. 可追溯性索引

### 11.1 来源到主题映射

| 主题                          | 最佳来源                                                                  |
| --------------------------- | --------------------------------------------------------------------- |
| 产品概要                        | `README.md`                                                           |
| 端到端流程                       | `docs/rag-system-architecture.md`                                     |
| 能力范围和指标                     | `docs/知识库功能与能力范围说明.md`                                                |
| 企业目标状态和路线图                  | `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`                               |
| 近期交付工作和运营进展                 | `docs/weekly-report-2026-06-04.md`、`docs/weekly-report-2026-06-07.md` |
| 运行时和发布工作流                   | `Makefile`                                                            |
| Prompt 和 grounded answer 约束 | `backend/app/rag/generators/client.py`                                |

### 11.2 值得频繁复用的高置信事实

1. 该系统是面向制造业和文档密集型知识工作流的企业级 RAG 平台。
2. 技术栈包括 FastAPI、React、Qdrant、BM25、Redis、Celery、PostgreSQL、PaddleOCR 和 Qwen 系列模型。
3. 核心差异点包括混合检索、带引用支撑的回答、部门感知访问控制、SOP 生成和可衡量发布门禁。
4. 最强工程信号是跨架构、产品、检索质量和运营加固的端到端所有权。
5. 已验证指标包括：

   * 快速模式目标低于 3 秒
   * top-1 accuracy 约 90%-95%
   * top-k recall 约 98%
   * document coverage 约 97%-98%
   * 质量系统中有 64 个 verified frozen samples 和 22 个 optimization cases

### 11.3 低置信或缺失领域

| 主题     | 状态 |
| ------ | -- |
| 法定姓名   | 缺失 |
| 教育经历   | 缺失 |
| 正式职位头衔 | 缺失 |
| 雇主时间线  | 缺失 |
| 工作年限   | 缺失 |
| 薪资期望   | 缺失 |

### 11.4 维护说明

1. 如果获得外部简历数据，优先更新第 2、3 和 8 节。
2. 如果检索指标发生明显变化，应同步更新第 5、6 和 11 节。
3. 如果路线图项目进入生产，应更新第 9 节中“已实现 vs 计划中”的回答。
4. 即使服务机器人后续将其改写为对话风格，也应保持本文档中立和事实化。
