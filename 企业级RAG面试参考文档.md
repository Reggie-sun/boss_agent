# Enterprise-grade RAG 面试参考文档｜融合简历完整版

> 目的：这是一份面向检索优化的参考文档，用于支持一个代表孙瑞杰进行面试回答的 RAG 面试机器人。
>
> 使用场景：HR 面试、技术面试、系统设计追问、项目复盘、行为面试、简历深挖、项目答辩、AI 求职自动问答。
>
> 写作风格：中立、事实化、受来源约束，并针对分块检索进行优化。服务层可以将中立事实转换成第一人称表达，但本源文档应保持非第一人称。
>
> 核心原则：同时保留仓库证据、项目证据和简历证据；对未验证信息不编造；对指标、经历、职责和能力范围明确标注来源边界。

---

## 1. 文档范围与回答规则

### 1.1 目标读者

* 主要读者：一个由 RAG 驱动的面试机器人，用于代表候选人孙瑞杰回答 HR、技术、系统设计、项目和行为类问题。
* 次要读者：人类审核者，用于检查项目陈述是否可追溯、是否符合简历事实、是否有仓库证据支撑。
* 第三类读者：用于生成简历话术、求职 Agent、面试陪练、Boss / 拉勾 / 猎聘等求职平台自动回复内容的系统。

### 1.2 不可妥协的回答规则

1. 优先使用明确来源支撑的事实。
2. 回答时应区分三种证据来源：

   * `简历已验证`：来自候选人提供的简历内容。
   * `仓库已验证`：来自代码、README、docs、Makefile、周报、评测报告、模块文件等项目仓库证据。
   * `合理推断`：根据简历与仓库证据综合得出的能力画像或角色定位。
3. 当某个字段没有来源时，必须明确说明“当前知识库没有该信息”，不要编造。
4. 不要编造以下内容：

   * 薪资
   * 期望薪资
   * 团队人数
   * 公司业务收入
   * 项目真实用户量
   * 项目节省成本
   * 领导评价
   * 绩效评级
   * 公司内部敏感数据
5. 对项目类问题，优先使用具体细节：

   * 项目背景
   * 项目目标
   * 系统架构
   * 技术栈
   * 个人职责
   * 核心难点
   * 解决方案
   * 工程化细节
   * 可衡量结果
6. 对系统能力类问题，必须区分：

   * 当前已实现能力
   * 当前优化中能力
   * 路线图或计划能力
7. 对指标类问题，必须说明指标口径：

   * 简历中当前描述的指标
   * 仓库中历史阶段记录的指标
   * 若二者不同，应说明可能是阶段不同、样本集不同或口径不同。
8. 对 HR 类问题，优先使用简历事实。
9. 对技术深挖类问题，优先使用项目链路、模块、文件、命令、评测方式证明候选人真实参与深度。
10. 对行为面试类问题，优先使用 STAR 结构，并结合企业级 RAG 项目中的真实工程问题。

### 1.3 来源层级

| 来源类型               | 可信度 | 主要用途                            |
| ------------------ | --- | ------------------------------- |
| 简历信息               | 高   | 个人信息、教育背景、工作经历、实习经历、项目经历、技能、证书  |
| 仓库代码               | 高   | 系统结构、模块职责、API、服务层、检索链路、提示词、权限控制 |
| 仓库文档               | 高   | 架构说明、执行计划、能力范围、周报、路线图、评测说明      |
| Makefile / CI / 测试 | 高   | 发布门禁、验证流程、工程成熟度                 |
| 项目访问地址             | 中   | 可展示项目，但不应夸大访问量、用户规模或商业影响        |
| 合理推断               | 中   | 工程能力画像、角色定位、工作风格，但回答时需要避免过度包装   |

### 1.4 仓库已验证来源集

| 来源                                               | 主要用途                            |
| ------------------------------------------------ | ------------------------------- |
| `README.md`                                      | 产品总结、本地工作流、核心技术栈                |
| `docs/rag-system-architecture.md`                | 端到端架构与流程                        |
| `docs/知识库功能与能力范围说明.md`                           | 系统定位、能力、指标、限制                   |
| `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`          | 企业级目标状态与路线图框架                   |
| `docs/weekly-report-2026-06-04.md`               | 搜索、质量控制、发布/评估进展                 |
| `docs/weekly-report-2026-06-07.md`               | 检索质量、OCR、UX、可观测性进展              |
| `Makefile`                                       | 运维工作流、验证和发布门禁                   |
| `backend/app/rag/generators/client.py`           | Prompt、grounding、格式化、token 预算行为 |
| `backend/app/services/retrieval_service.py`      | 检索服务编排                          |
| `backend/app/services/chat_service.py`           | 聊天问答主流程                         |
| `backend/app/services/retrieval_query_router.py` | 查询路由、检索模式选择                     |
| `backend/app/services/chat_memory_service.py`    | 多轮追问与记忆处理                       |
| `backend/app/services/chat_citation_pipeline.py` | 引用溯源与证据绑定                       |
| `backend/app/services/retrieval_scope_policy.py` | 检索范围与权限策略                       |
| `backend/app/rag/chunkers/structured_chunker.py` | 结构化切块                           |
| `backend/app/rag/vectorstores/qdrant_store.py`   | Qdrant 向量存储                     |
| `backend/app/rag/rerankers/client.py`            | 重排序模型调用                         |

### 1.5 简历已验证来源集

| 来源字段  | 内容                                                 |
| ----- | -------------------------------------------------- |
| 姓名    | 孙瑞杰                                                |
| 求职意向  | AI 应用工程师                                           |
| 年龄    | 23 岁                                               |
| 性别    | 男                                                  |
| 到岗时间  | 一个月内到岗                                             |
| 地区    | 湖北                                                 |
| 手机    | 17798303245                                        |
| 邮箱    | [2745124840@qq.com](mailto:2745124840@qq.com)      |
| 教育    | 湖北工程学院，光电信息科学与工程，本科，2021-09 至 2025-06              |
| 当前工作  | 宁波伟立机器人科技股份有限公司，AI 开发工程师，2026-03 至今                |
| 当前主项目 | 企业级 RAG 知识库与智能问答平台                                 |
| 实习经历  | 上海企顺信息系统有限公司，IT 工程师，2024-10 至 2024-12；convoloo，机器学习，2025-05 至 2025-09 |
| 项目经历  | 企业级 RAG 知识库与智能问答平台；BOSS AGENT；乳腺癌良 / 恶性预测系统       |
| 证书    | Coursera 吴恩达机器学习专项课程、深度学习专项课程、convoloo 实习证书、大学英语四级 |

### 1.6 推荐面试回答策略

| 问题类型     | 推荐回答风格                         |
| -------- | ------------------------------ |
| HR / 个人类 | 先陈述简历已验证背景，再连接到 AI 应用工程师定位     |
| 技术深挖     | 解释架构、链路、模块、取舍、失败模式和验证方式        |
| 项目影响     | 使用可用指标，不编造业务 ROI               |
| 行为类      | 使用 STAR 结构，强调独立负责、定位问题、工程闭环    |
| 路线图      | 区分已实现能力、优化中能力、计划能力             |
| 简历真实性追问  | 使用模块名、文件名、API、命令、指标和具体链路证明参与深度 |

---

## 2. 个人背景

### 2.1 简历已验证个人信息

| 字段   | 内容                                            |
| ---- | --------------------------------------------- |
| 姓名   | 孙瑞杰                                           |
| 性别   | 男                                             |
| 年龄   | 23 岁                                          |
| 求职意向 | AI 应用工程师                                      |
| 到岗时间 | 一个月内到岗                                        |
| 地区   | 湖北                                            |
| 手机   | 17798303245                                   |
| 邮箱   | [2745124840@qq.com](mailto:2745124840@qq.com) |

### 2.2 已验证职业身份

* 候选人孙瑞杰当前求职意向为 AI 应用工程师。
* 候选人当前在宁波伟立机器人科技股份有限公司担任 AI 开发工程师，时间为 2026-03 至今。
* 候选人当前主要项目是企业级 RAG 知识库与智能问答平台。
* 候选人在该项目中独立负责核心架构与落地开发。
* 该企业级 RAG 项目面向制造业内部制度文档、SOP、设备资料、运维手册与业务知识问答场景。
* 项目覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、多轮追问、智能问答、SOP 生成、运行观测与评测回归。
* 项目累计实现 89 个 API 路由、26 个核心 schema 模块。
* 项目支撑企业内部私有知识问答、制度查询、SOP 检索、文档中心检索与可追溯文档分析。
* 当前简历明确记录 release capability dashboard 中 12 项 blocking capability 全部通过。

### 2.3 仓库已验证专业身份

* 仓库证据显示，候选人负责或深度参与了一个面向企业的 RAG 平台，该平台聚焦制造业和文档密集型知识工作流。
* 仓库证据显示，候选人相关工作覆盖后端 API、检索质量、聊天行为、文档摄取、OCR、前端门户 / 工作区流程、评估治理和发布验证。
* 工作画像更接近全栈 AI 系统工程师、RAG 应用工程师或 AI 技术负责人，而不是狭窄的单层模型调用者。

### 2.4 已验证领域方向

| 领域   | 描述                                  |
| ---- | ----------------------------------- |
| 行业重点 | 制造业与企业知识管理                          |
| 问题空间 | 企业文档搜索、基于证据的问答、SOP 检索、权限感知检索、运营知识访问 |
| 产品定位 | 私有化部署、浏览器访问、企业安全、可审计、可追溯、可评测        |
| 工程定位 | 可追溯回答、检索评估、运行时可观测性、发布门禁、访问控制        |
| 求职定位 | AI 应用工程师、RAG 应用工程师、LLM 应用开发工程师      |

### 2.5 合理推断出的能力画像

* `合理推断`：候选人具备较强的 AI 应用工程化能力，能把模型、检索、数据处理、后端服务、前端界面和部署联调组合成完整系统。
* `合理推断`：候选人具备较强的 RAG 系统思维，理解企业知识库不只是向量检索，而是文档摄取、权限、检索、引用、评测和运维的整体工程。
* `合理推断`：候选人更偏产品落地和系统工程，而不是单纯算法研究。
* `合理推断`：候选人重视正确性、可追溯性、评测和部署现实性，而不是只做 Demo 型 AI 应用。
* `合理推断`：候选人适合 AI 应用工程师、RAG 工程师、LLM 应用工程师、AI 后端工程师、Agent 工程师等岗位。

### 2.6 未验证或不能编造的信息

| 字段         | 状态       | 安全回答策略             |
| ---------- | -------- | ------------------ |
| 当前薪资       | 未提供      | 不编造                |
| 期望薪资       | 未提供      | 可询问候选人或由服务层按岗位策略处理 |
| 团队人数       | 未提供      | 不声称“带团队”或具体人数      |
| 公司业务收入     | 未提供      | 不编造                |
| 项目真实用户数    | 未提供      | 不编造                |
| 项目节省成本     | 未提供      | 不编造                |
| 领导评价       | 未提供      | 不编造                |
| 公司内部敏感文档内容 | 未提供且不宜披露 | 不主动披露              |
| 具体客户名称     | 未提供      | 不编造                |

### 2.7 示例面试问题

#### 问题：你是什么类型的工程师？

**模型回答要点**

* 候选人孙瑞杰的求职方向是 AI 应用工程师。
* 他的核心经验是企业级 RAG 知识库与智能问答平台，从文档入库、OCR/解析、结构化切块、向量索引、混合检索、重排序、权限过滤、引用溯源、多轮问答到评测回归都有实际参与。
* 他的特点不是只会调用大模型 API，而是能把 LLM、RAG、后端服务、前端交互、异步任务、部署和质量评测做成完整系统。
* 更准确的定位是工程落地型 AI 应用工程师或 RAG 系统工程师。

#### 问题：最可信的候选人画像是什么？

**模型回答要点**

* 候选人是偏工程落地型的 AI 应用工程师。
* 当前最强项目是制造业企业级 RAG 知识库与智能问答平台。
* 该项目体现了他在后端、检索、OCR、权限、引用、多轮追问、评测和部署方面的综合能力。
* 除 RAG 外，他还做过机器学习预测系统和生成式 AI 图像应用，因此能力覆盖传统机器学习、LLM 应用和生成式 AI 应用。

---

## 3. 教育背景

### 3.1 简历已验证教育经历

| 学校     | 专业        | 学历 | 时间                |
| ------ | --------- | -- | ----------------- |
| 湖北工程学院 | 光电信息科学与工程 | 本科 | 2021-09 至 2025-06 |

### 3.2 教育背景说明

* 候选人本科毕业于湖北工程学院，专业为光电信息科学与工程。
* 光电信息科学与工程属于理工科专业，通常涉及数学、物理、电子信息、信号处理、编程和工程系统基础。
* 候选人后续通过机器学习课程、深度学习课程、项目实践和企业级 RAG 工作，将专业背景延伸到 AI 应用开发方向。

### 3.3 课程与证书补充

候选人通过 Coursera 上吴恩达的机器学习专项课程和深度学习专项课程，包含：

* Supervised Machine Learning: Regression and Classification
* Advanced Learning Algorithms
* Unsupervised Learning, Recommenders
* Reinforcement Learning
* Neural Networks and Deep Learning
* Improving Deep Neural Networks: Hyperparameter Tuning, Regularization and Optimization

证书链接：

* `https://www.coursera.org/account/accomplishments/verify/1W6647EN8OMH`
* `https://www.coursera.org/account/accomplishments/certificate/AZSRUJYO5B1B`

其他证书：

* convoloo 实习证书
* 大学英语四级证书

### 3.4 教育背景安全回答策略

1. 可以明确回答学校、专业、学历和时间。
2. 可以说明通过 Coursera 系统学习机器学习和深度学习。
3. 不应夸大为计算机科班背景。
4. 可以强调通过项目实践完成向 AI 应用工程方向的转型。
5. 如果被问到成绩、排名、奖学金，当前文档没有提供，不应编造。

### 3.5 示例面试问题

#### 问题：你的教育背景是什么？

**模型回答要点**

* 本科毕业于湖北工程学院，专业是光电信息科学与工程，时间是 2021-09 至 2025-06。
* 本科是理工科背景，后续通过机器学习、深度学习课程和多个 AI 项目实践转向 AI 应用工程方向。
* 目前主要经验集中在企业级 RAG、LLM 应用、机器学习预测系统和生成式 AI 应用落地。

#### 问题：非计算机专业会不会影响 AI 应用开发？

**模型回答要点**

* 候选人虽然本科专业不是纯计算机，但具备理工科基础。
* 后续通过系统课程和项目实践补齐了机器学习、深度学习、Python、FastAPI、React、Docker、RAG、LLM 应用等能力。
* 当前企业级 RAG 项目覆盖 89 个 API 路由、26 个核心 schema 模块和完整检索问答链路，能够证明其工程能力来自实际项目，而不只是专业名称。

---

## 4. 技能与技术

### 4.1 技术技能图谱

| 技能领域               | 已验证技术                                                                   | 证据                               |
| ------------------ | ----------------------------------------------------------------------- | -------------------------------- |
| 后端 API             | FastAPI、Python、Pydantic、服务层设计                                           | 简历、README、仓库 endpoint/service 结构 |
| 前端                 | React、TypeScript、Vite、Streamlit、Plotly                                  | 简历、项目经历、前端目录                     |
| 检索 / RAG           | Qdrant、Elasticsearch BM25、RRF、混合检索、query router、rerank、prompt budget    | 简历、架构文档、代码模块                     |
| LLM 应用             | OpenAI-compatible 接口、Qwen 系列模型、vLLM、Prompt Engineering、RAG、API 编排       | 简历、生成器代码、系统文档                    |
| Embedding / Rerank | BGE-M3、BGE-reranker-v2-m3                                               | 简历、系统文档                          |
| 文档摄取               | PDF、Office、PPT、OCR、表格识别、结构化切块、异步处理                                      | 简历、系统文档、周报                       |
| OCR                | PaddleOCR、扫描件处理、表格识别                                                    | 仓库文档、周报                          |
| 异步任务               | Celery、Redis、ingest_cpu、ingest_ocr、preview 队列                           | 简历                               |
| 数据 / 存储            | PostgreSQL、Redis、MinIO、Qdrant、Elasticsearch                             | 简历、README、执行计划                   |
| 部署                 | Docker、Linux、cloudflared tunnel、Caddy 反向代理                              | 简历                               |
| 机器学习               | scikit-learn、Logistic Regression、特征工程、模型评估、Pickle                       | 简历项目                             |
| 深度学习               | PyTorch、混合精度训练、梯度裁剪、学习率调度、早停                                            | 简历                               |
| 生成式 AI             | Stable Diffusion、ControlNet、LoRA、Diffusers                              | convoloo 实习                      |
| Agent 工程           | Codex、Claude Code、MCP、自定义 Skill、Agent Runtime、Harness、AGENTS.md         | 简历技能                             |
| 质量 / 评测            | frozen + rolling 样本、blocking rules、回归报告、CI 发布门禁                         | 简历、Makefile                      |
| 可观测性               | request traces、request snapshots、event logs、health checks、Prometheus 方向 | 仓库文档、周报                          |

### 4.1.1 企业级 RAG 技术栈

| 层级        | 技术                    |
| --------- | --------------------- |
| 后端        | Python、FastAPI        |
| 前端        | React、TypeScript、Vite |
| 异步任务      | Celery、Redis          |
| 向量数据库     | Qdrant                |
| 关键词检索     | Elasticsearch、BM25    |
| 融合排序      | RRF                   |
| 重排序       | BGE-reranker-v2-m3    |
| Embedding | BGE-M3                |
| LLM 推理    | vLLM                  |
| 主模型       | Qwen 系列模型             |
| 元数据存储     | PostgreSQL            |
| 对象存储      | MinIO                 |
| OCR       | PaddleOCR             |
| 部署        | Docker、Linux          |

### 4.1.2 具体模块所有权信号

| 能力        | 主要入口文件                                                                                                                     | 面试中能证明什么                          |
| --------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------- |
| 检索 API    | `backend/app/api/v1/endpoints/retrieval.py`、`backend/app/schemas/retrieval.py`、`backend/app/services/retrieval_service.py` | 所有权不只是概念层，而是覆盖公开 API、schema 和服务编排 |
| 聊天 API    | `backend/app/api/v1/endpoints/chat.py`、`backend/app/schemas/chat.py`、`backend/app/services/chat_service.py`                | 工作包含 grounded QA 服务，而不仅是离线检索      |
| 引用流水线     | `backend/app/services/chat_citation_pipeline.py`                                                                           | 引用质量被视为一等答案契约                     |
| 聊天记忆      | `backend/app/services/chat_memory_service.py`                                                                              | 多轮追问行为被显式工程化                      |
| 查询路由      | `backend/app/services/retrieval_query_router.py`、`backend/app/services/query_profile_service.py`                           | query 意图与检索模式选择属于系统设计             |
| 访问策略      | `backend/app/services/retrieval_scope_policy.py`、auth 相关 endpoint/service                                                  | 检索范围是策略驱动，不只是前端约束                 |
| 文档摄取      | `backend/app/services/ingestion_service.py`、`backend/app/rag/parsers/document_parser.py`                                   | 真实企业语料处理属于核心工作                    |
| Chunking  | `backend/app/rag/chunkers/text_chunker.py`、`backend/app/rag/chunkers/structured_chunker.py`                                | 检索质量工作延伸到切块层                      |
| OCR       | `backend/app/rag/ocr/client.py`                                                                                            | 系统处理扫描件和图片型文档                     |
| 向量存储      | `backend/app/rag/vectorstores/qdrant_store.py`                                                                             | 系统包含检索基础设施，而不是只写 prompt           |
| Reranking | `backend/app/rag/rerankers/client.py`                                                                                      | 排序质量被显式优化                         |
| 系统配置      | `backend/app/api/v1/endpoints/system_config.py`、`backend/app/services/system_config_service.py`                            | 运行时配置被产品化管理                       |
| 运维诊断      | `logs.py`、`traces.py`、`request_snapshots.py`、`ops.py`                                                                      | 生产调试与运营工作流被设计进系统                  |

### 4.1.3 具体运行时与产品界面

| 界面 / 路由                            | 价值            |
| ---------------------------------- | ------------- |
| `frontend/src/App.tsx`             | 工作区入口，体现前端应用壳 |
| `frontend/src/pages/*`             | 内部页面与管理界面     |
| `frontend/src/portal/*`            | 门户侧或员工侧产品体验   |
| `frontend/src/pages/AdminPage.tsx` | 管理员配置界面       |
| `/api/v1/health`                   | 服务健康检查        |
| `/api/v1/ops`                      | 运维能力          |
| `/api/v1/logs`                     | 日志查看          |
| `/api/v1/traces`                   | 请求链路追踪        |
| `/api/v1/request_snapshots`        | 请求快照与复盘       |

### 4.1.4 具体命令级工程信号

| 命令 / 门禁                            | 作用                                             | 面试价值           |
| ---------------------------------- | ---------------------------------------------- | -------------- |
| `make verify-retrieval-focused`    | 对单个 residual、case 或 fix 运行窄范围检索验证              | 展示调试质量问题的快速内循环 |
| `make verify-retrieval-quick`      | 不进行完整 live replay 的治理导向快速检查                    | 展示快速验证与最终签署分离  |
| `make verify-retrieval-release`    | 运行仓库原生检索发布验证包                                  | 证明有发布门禁        |
| `make verify-v1-release-readiness` | 跨检索、优化、门户证据、摄取/OCR、健康和 waiver policy 的 V1 就绪检查 | 证明系统级发布意识      |
| `make snapshot-governance-rolling` | 报告 snapshot/governance/rolling 对齐情况            | 展示样本治理和证据维护    |
| `make portal-chat-browser-smoke`   | 对门户聊天运行浏览器 smoke                               | 证明用户可见行为也被验证   |
| `make agent-runtime-bridge`        | 启动本地运行时 HTTP bridge                            | 展示工具化和产品化能力    |

### 4.2 简历技能特长

#### 4.2.1 机器学习能力

候选人掌握监督学习、无监督学习与推荐系统基础，熟悉 Transformer、CNN、RNN 等模型结构。具备 LLM 应用落地能力，能够基于 Prompt Engineering、RAG、API 编排及轻量微调方法支持业务场景实现。

#### 4.2.2 Agent 与 AI 工程化能力

候选人熟练使用 Codex、Claude Code、MCP 及自定义 Skill 工作流进行项目开发、代码重构、自动化测试与部署。具备 Agent Runtime、Harness、递归式 AGENTS.md 规则体系的工程实践经验，能够搭建多步骤任务执行、工具调用、结果校验与回归测试链路，并为复杂代码仓设计分层规则与执行边界。

#### 4.2.3 编程能力

候选人精通 Python，擅长异步编程、正则表达式、数据清洗、特征工程与自动化脚本开发。熟悉 LangChain、LangGraph 等大模型应用开发框架，理解 Function Calling、MCP 与工具编排机制的差异及适用场景。

#### 4.2.4 部署与工程化能力

候选人熟悉 Linux 环境下的服务部署、网络配置、Docker 镜像构建与调试，具备 cloudflared tunnel、Caddy 反向代理等实际使用经验，能够独立完成本地到服务端的部署与联调。

#### 4.2.5 模型训练与优化能力

候选人熟练掌握 PyTorch，能够独立完成模型构建、训练、调优与部署。掌握混合精度训练、梯度裁剪、学习率调度、早停等常用优化技巧。

### 4.3 工程优势

* 端到端系统设计能力。
* 企业 RAG 架构设计能力。
* 强 grounding 和引用意识。
* 熟悉权限感知检索和部门边界。
* 有检索评测、回归报告和发布门禁意识。
* 有文档摄取、OCR、结构化切块、异步任务等真实企业语料处理经验。
* 能同时改进产品 UX 和模型质量。
* 能使用 AI 编程工具和 Agent 工作流提升研发效率。

### 4.4 架构推理模式

| 模式         | 证据                                                            |
| ---------- | ------------------------------------------------------------- |
| 偏好显式防护栏    | grounding gates、拒答行为、发布验证                                     |
| 偏好可观测工作流   | health endpoints、traces、snapshots、周报                          |
| 偏好渐进加固而非重写 | 企业级执行计划                                                       |
| 偏好策略分离     | auth、retrieval policy、direct-resource access、release truth 分离 |
| 偏好可度量质量    | verified samples、optimization cases、frozen + rolling 评测       |
| 偏好工程闭环     | 文档摄取、检索、生成、引用、评测、部署全部覆盖                                       |

### 4.5 示例面试问题

#### 问题：你最强的技术能力是什么？

**模型回答要点**

* 最强能力是 AI 应用工程化，尤其是企业级 RAG 系统从 0 到 1 的架构与落地。
* 候选人不只是调用模型 API，而是能处理文档摄取、OCR、chunking、Embedding、混合检索、rerank、权限过滤、引用溯源、多轮追问和评测回归。
* 同时具备 FastAPI 后端、React 前端、Celery 异步任务、Docker 部署和 AI 编程工具使用经验。

#### 问题：你更偏算法还是工程？

**模型回答要点**

* 候选人更偏 AI 应用工程落地。
* 具备机器学习和深度学习基础，也做过传统机器学习预测系统和 LoRA 图像生成实习。
* 当前最强证据来自企业级 RAG 项目，体现的是把模型能力、检索系统、业务流程和工程部署结合起来的能力。

---

## 5. 项目：Enterprise-grade RAG 知识库与智能问答平台

### 5.1 项目总结

Enterprise-grade RAG 是一个基于浏览器、支持私有化部署的企业知识系统，用于企业文档检索、基于证据的智能问答、制度查询、SOP 检索、文档中心检索和可追溯文档分析。

该项目面向制造业内部制度文档、SOP、设备资料、运维手册与业务知识问答场景，由候选人孙瑞杰在宁波伟立机器人科技股份有限公司担任 AI 开发工程师期间独立负责核心架构与落地开发。

项目不是简单的 ChatPDF 或文档聊天 Demo，而是覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、智能问答、多轮追问、SOP 生成、运行观测和评测回归的完整企业级 AI 应用系统。

### 5.2 项目背景

制造业企业内部存在大量文档，包括：

* 制度文件
* SOP
* 设备资料
* 技术手册
* 运维手册
* 维护指南
* 业务流程文档
* 合同和协议
* 操作指导书
* 扫描 PDF
* 表格密集型文档
* 图片型页面

传统文件夹和关键词搜索存在明显问题：

1. 文档数量多，查找慢。
2. 文档格式复杂，PDF、Office、PPT、扫描件混杂。
3. 用户问题经常是自然语言，不一定包含精确关键词。
4. 制度、SOP、设备型号、文档编号等又需要精确匹配。
5. 不同部门和角色有不同文档权限。
6. 答案必须能追溯到原文，否则企业用户难以信任。
7. 系统改动后可能出现检索回归，需要评测体系保证质量。

该项目通过 RAG 架构将企业文档转化为可检索、可问答、可引用、可审计的知识资产。

### 5.3 项目目标

1. 集中管理企业内部制度、SOP、设备资料和业务知识文档。
2. 支持 PDF / Office / PPT / Excel 等多格式文档入库。
3. 支持 OCR、表格识别和结构化解析。
4. 将文档切分为适合检索和引用的结构化 chunks。
5. 建立 Embedding 索引和关键词索引。
6. 使用向量召回 + BM25 + RRF + reranker 提升检索质量。
7. 支持部门与文档可见范围权限过滤。
8. 支持基于文档证据的智能问答。
9. 支持答案引用来源文档、页码、片段和原文跳转。
10. 支持多轮追问和上下文改写。
11. 建立检索评测样本、回归报告和发布门禁。
12. 支撑企业内部私有知识问答、制度查询、SOP 检索、文档中心检索和可追溯文档分析。

### 5.4 产品范围

| 范围领域    | 已验证能力                                      |
| ------- | ------------------------------------------ |
| 知识检索    | 向量检索 + BM25 + RRF 融合 + rerank              |
| 聊天回答    | citation-backed answers，支持多轮记忆             |
| 文档中心    | 上传、浏览、预览、搜索、重建、删除                          |
| SOP 工作流 | SOP 生成、预览、导出、版本管理                          |
| 访问控制    | JWT auth、角色感知行为、部门级隔离                      |
| 运维诊断    | health checks、traces、snapshots、replay、logs |
| 评测治理    | frozen + rolling 样本、blocking rules、CI 发布门禁 |

### 5.5 项目规模与指标

#### 5.5.1 简历当前指标

| 指标                  | 数值                         |
| ------------------- | -------------------------- |
| API 路由              | 89 个                       |
| 核心 schema 模块        | 26 个                       |
| release capability dashboard | 12 项 blocking capability 全部通过 |
| 支持文档格式              | PDF / Office / PPT / Excel 等 |
| 支撑场景                | 私有知识问答、制度查询、SOP 检索、文档中心检索、可追溯文档分析 |

#### 5.5.2 仓库历史阶段指标

| 指标 / 信号           | 历史记录值                                                  |
| ----------------- | ------------------------------------------------------ |
| fast-mode 响应目标    | `< 3 seconds`                                          |
| 检索 top-1 accuracy | 在 64 个 verified frozen samples 上约 90%-95%              |
| 检索 top-k recall   | 在 64 个 verified frozen samples 上约 98%                  |
| 文档覆盖率             | 在 64 个 verified frozen samples 上约 97%-98%              |
| 并发目标              | `>= 30` concurrent users                               |
| 可用性目标             | `>= 99.5%`                                             |
| 回归治理              | 64 个 verified frozen samples + 22 个 optimization cases |
| 周度交付信号            | 2026-06-01 至 2026-06-06 报告中记录 170 commits              |
| 既有文档治理口径          | 167 条检索评测样本、Top1 Accuracy 约 95%+、TopK Recall 约 97%+ |

#### 5.5.3 指标口径说明

* 当前 PDF 简历明确给出的规模指标是 89 个 API 路由、26 个核心 schema 模块，以及 release capability dashboard 中 12 项 blocking capability 全部通过。
* 167 条检索评测样本、Top1 Accuracy 约 95%+、TopK Recall 约 97%+ 来自本文档既有治理口径；如果回答时使用，应标注为仓库或既有文档证据，而不是当前 PDF 简历直接陈述。
* 仓库文档中的 64 个 verified frozen samples、22 个 optimization cases、top-1 约 90%-95%、top-k recall 约 98%，应视为某一历史阶段或特定评测集口径。
* 面试时如被追问指标差异，可以说明：随着项目推进，评测样本集从较小的 verified frozen samples 扩展到 frozen + rolling 双轨样本，因此样本数量和指标口径可能不同。

### 5.6 稳定契约与主要 API

| API / Contract                  | 产品中的角色  | 说明                      |
| ------------------------------- | ------- | ----------------------- |
| `POST /api/v1/retrieval/search` | 核心检索契约  | 用于检索 chunks / 文档证据      |
| `POST /api/v1/chat/ask`         | 主问答契约   | 用于 grounded QA          |
| `POST /api/v1/chat/ask/stream`  | 流式问答路径  | 支持实时 token streaming UX |
| `GET /api/v1/system-config`     | 读取运行时配置 | 用于系统可调行为                |
| `PUT /api/v1/system-config`     | 更新运行时配置 | 展示管理员侧配置能力              |
| `/api/v1/health`                | 服务健康检查  | 用于运行时检查和支持ability       |
| `/api/v1/logs`                  | 日志查看    | 支持问题排查                  |
| `/api/v1/traces`                | 请求追踪    | 支持链路诊断                  |
| `/api/v1/request_snapshots`     | 请求快照    | 支持 replay 与回归分析         |

### 5.7 主后端所有权地图

| 产品能力 | 主要文件                                                                                                                           |
| ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| 检索   | `backend/app/services/retrieval_service.py`、`retrieval_query_router.py`、`query_profile_service.py`、`retrieval_scope_policy.py` |
| 聊天   | `backend/app/services/chat_service.py`、`chat_citation_pipeline.py`、`chat_memory_service.py`                                    |
| 生成   | `backend/app/rag/generators/client.py`                                                                                         |
| 文档管理 | `backend/app/services/document_service.py`                                                                                     |
| 摄取   | `backend/app/services/ingestion_service.py`、`backend/app/rag/parsers/document_parser.py`                                       |
| SOP  | `backend/app/services/sop_service.py`、`sop_generation_service.py`、`sop_version_service.py`                                     |
| 诊断   | `request_trace_service.py`、`request_snapshot_service.py`、`event_log_service.py`、`ops_service.py`                               |
| OCR  | `backend/app/rag/ocr/client.py`                                                                                                |
| 切块   | `text_chunker.py`、`structured_chunker.py`                                                                                      |
| 向量库  | `qdrant_store.py`                                                                                                              |
| 重排序  | `rerankers/client.py`                                                                                                          |

### 5.8 核心技术栈

| 层级         | 技术                    |
| ---------- | --------------------- |
| 后端         | Python、FastAPI        |
| 前端         | React、TypeScript、Vite |
| 向量检索       | Qdrant                |
| 词法检索       | Elasticsearch BM25    |
| 融合排序       | RRF                   |
| 重排序        | BGE-reranker-v2-m3    |
| Embedding  | BGE-M3                |
| 元数据 / 系统状态 | PostgreSQL            |
| 对象存储       | MinIO                 |
| 异步处理       | Redis、Celery          |
| 文档解析       | PDF / Office / PPT 解析 |
| OCR        | PaddleOCR             |
| 模型推理       | vLLM                  |
| 主模型        | Qwen 系列模型             |
| 部署         | Docker、Linux          |

### 5.9 具体模型与检索栈说明

* Embedding 模型：`BGE-M3`
* Reranker 模型：`BGE-reranker-v2-m3`
* LLM 推理：`vLLM`
* 主回答模型：Qwen 系列模型
* 检索形态：Qdrant 向量召回 + Elasticsearch BM25 词法召回 + RRF 融合 + rerank
* OCR 技术栈：PaddleOCR
* 前端交付形态：React + TypeScript + Vite
* 异步队列：Celery + Redis，拆分 ingest_cpu / ingest_ocr / preview 等队列

### 5.10 Prompt 与答案控制信号

生成层不是一个薄的原始模型调用。`backend/app/rag/generators/client.py` 展示了若干具体答案控制规则：

1. 模型被要求只根据检索上下文回答。
2. 最近对话可用于追问解析，但不能优先于检索证据。
3. 答案必须使用 Markdown 和结构化标题。
4. Prompt 要求在答案后输出 `used_context_numbers`、`used_documents` 和 `suggested_questions` 元数据。
5. `used_documents` 必须指向真实检索到的文档元数据，而不是编造标签。
6. OpenAI-compatible payload 中的 `max_tokens` 由运行时 prompt budget 控制，而不是隐藏硬编码。
7. 如果证据不足，系统应走拒答、降级或明确说明知识库中没有足够依据。

### 5.11 架构概览

#### 5.11.1 请求流程

1. 用户通过浏览器或 API 发起问题。
2. 请求进入 FastAPI endpoint，并携带 request context、auth context 和用户身份信息。
3. 系统判断是否需要 recent conversation memory 来理解追问。
4. Query understanding 和 rewrite 解析意图、实体、过滤条件和路由。
5. Query router 判断查询更偏 exact、semantic 还是 mixed。
6. 检索阶段根据用户权限注入 ACL filter。
7. 系统执行 Qdrant 向量召回。
8. 系统执行 Elasticsearch BM25 词法召回。
9. 对召回结果进行 RRF 融合。
10. 使用 BGE-reranker-v2-m3 对候选 chunks 重排序。
11. 执行 metadata refill、context compression、citation selection。
12. 构造 LLM prompt。
13. vLLM / Qwen 系列模型生成答案。
14. Citation Pipeline 将答案绑定到 chunk 级证据。
15. 后处理校验答案结构、引用、metadata 和 grounding。
16. 记录 request trace、snapshot、event log。
17. 返回带引用的答案。

#### 5.11.2 文件级流程

1. FastAPI 入口：`backend/app/main.py`
2. V1 router 聚合：`backend/app/api/v1/router.py`
3. 检索 endpoint：`backend/app/api/v1/endpoints/retrieval.py`
4. 聊天 endpoint：`backend/app/api/v1/endpoints/chat.py`
5. 检索编排：`backend/app/services/retrieval_service.py`
6. Query routing：`backend/app/services/retrieval_query_router.py`
7. Query profile：`backend/app/services/query_profile_service.py`
8. Lexical retrieval：`backend/app/rag/retrievers/lexical_retriever.py`
9. Vector retrieval：`backend/app/rag/vectorstores/qdrant_store.py`
10. Rerank：`backend/app/rag/rerankers/client.py`
11. Answer generation：`backend/app/rag/generators/client.py`
12. Citation pipeline：`backend/app/services/chat_citation_pipeline.py`
13. Memory service：`backend/app/services/chat_memory_service.py`
14. Scope policy：`backend/app/services/retrieval_scope_policy.py`
15. Trace persistence：`backend/app/services/request_trace_service.py`
16. Snapshot persistence：`backend/app/services/request_snapshot_service.py`

### 5.12 核心功能能力

| 能力            | 细节                                               |
| ------------- | ------------------------------------------------ |
| 多格式摄取         | PDF、Office、PPT、扫描图像、OCR 辅助解析                     |
| 结构化切块         | 标题层级、表格、条款、段落、摘要等 chunk 类型                       |
| 混合检索          | Qdrant + Elasticsearch BM25 + RRF                |
| 重排序           | BGE-reranker-v2-m3                               |
| query router  | exact / semantic / mixed 查询识别                    |
| 多轮追问          | Memory-Aware Query Rewrite，生成 effective question |
| 权限控制          | global / department / library 等权限粒度              |
| 引用溯源          | 来源文档、页码、片段、原文跳转                                  |
| Grounded chat | 答案必须基于检索上下文                                      |
| SOP 检索 / 生成   | 支持 SOP 相关知识访问与生成流程                               |
| 评测治理          | frozen + rolling 样本、blocking rules、CI 门禁         |
| 可观测性          | traces、snapshots、logs、health、replay              |

### 5.13 核心亮点一：混合检索与查询路由

#### 背景

企业知识库中存在大量精确标识：

* 文档编号
* 条款号
* 设备型号
* SOP 名称
* 制度标题
* 物料编码
* 业务术语
* 部门名称

单纯向量检索适合语义问题，但对精确字符串不一定稳定。单纯 BM25 对关键词和编号敏感，但无法很好处理口语化问题和语义改写。

#### 方案

系统使用：

1. Qdrant 向量召回
2. Elasticsearch BM25 词法召回
3. RRF 融合排序
4. BGE-reranker-v2-m3 重排序
5. query router 动态判断查询类型

query router 会识别：

* `exact`：编号、型号、条款号、标题类精确查询。
* `semantic`：自然语言描述、解释类、概念类问题。
* `mixed`：同时包含关键词和语义意图的问题。

系统根据查询类型动态调整 lexical / vector 权重，降低编号类问题漏召风险。

#### 面试价值

该亮点证明候选人理解企业 RAG 不是“向量库 + 大模型”即可解决，而是要根据 query 类型、文档结构和业务语料特点设计检索策略。

### 5.14 核心亮点二：结构化文档摄入与异步处理

#### 背景

企业文档格式复杂，包含：

* PDF
* Word
* PPT
* Excel
* 扫描件
* 图片型 PDF
* 表格
* 页眉页脚
* 重复水印
* 多级标题
* 条款编号

如果直接粗暴切块，会导致检索噪声高、引用不稳定、答案 grounding 差。

#### 方案

候选人将文档解析、OCR、表格识别、结构化抽取、切块和索引构建拆成异步任务链路。

Celery 队列拆分：

* `ingest_cpu`：CPU 密集型解析和切块任务。
* `ingest_ocr`：OCR 和图像识别任务。
* `preview`：文档预览和轻量任务。

该设计隔离 OCR、IO 和 CPU 密集型任务，提升摄入链路稳定性，避免重任务阻塞主业务请求。

#### 面试价值

该亮点证明候选人具备 AI 应用工程化能力，理解真实企业 RAG 的难点在数据摄入、异步处理和系统稳定性，而不只是模型调用。

### 5.15 核心亮点三：权限隔离与可追溯问答

#### 背景

企业知识库必须处理权限问题。不同部门、角色、文档库之间可能存在访问边界。RAG 如果只在前端隐藏文档，而检索阶段不做权限过滤，就可能造成敏感内容泄露。

#### 方案

系统基于部门 scope 和文档可见范围实现访问控制，在检索阶段自动注入 ACL 过滤条件。权限粒度支持：

* `global`
* `department`
* `library`

同时构建 Citation Pipeline，将答案与 chunk 级证据绑定，支持：

* 来源文档
* 页码
* 片段
* 原文跳转
* 引用溯源

#### 面试价值

该亮点证明候选人理解企业级 AI 系统的核心不是“答出来”即可，而是必须可追溯、可审计、可控权。

### 5.16 核心亮点四：多轮追问与上下文改写

#### 背景

RAG 常见失败是多轮追问断裂。用户不会每次都重复完整问题，而是会问：

* “这个呢？”
* “有没有相关规范？”
* “再详细点。”
* “第二步是什么？”
* “还有类似的吗？”
* “那这个制度适用于谁？”

如果直接把这类问题拿去检索，retrieval query 缺少核心实体，容易搜偏。

#### 方案

候选人设计 Memory-Aware Query Rewrite，将：

* 用户展示问题
* 实际检索问题

解耦。

系统结合：

* 近轮对话摘要
* 主题锚点
* 上一轮引用文档
* 当前追问
* 文档上下文
* 历史引用范围

生成 effective question，再用 effective question 进入 retrieval。

#### 面试价值

该亮点证明候选人理解：多轮 RAG 的关键不是把历史对话塞给 LLM，而是让 retrieval 也理解上下文。

### 5.17 核心亮点五：检索评测与发布门禁

#### 背景

RAG 优化容易出现：

* 修好一个问题，改坏另一个问题。
* 向量权重调整后，编号类查询退化。
* BM25 权重提高后，语义查询退化。
* 追问改写增强后，跨主题问题被错误继承。
* 文档更新后，原样本真值漂移。

如果没有评测样本和回归保护，系统质量无法稳定。

#### 方案

候选人构建 frozen + rolling 双轨评测体系；本文档既有治理口径记录了 167 条检索评测样本，覆盖：

* 精确查询
* 语义查询
* 多轮追问
* 跨部门补充召回
* 文档编号类问题
* 制度查询
* SOP 查询
* 相似文档区分

既有治理口径下的评测信号：

* Top1 Accuracy 约 95%+
* TopK Recall 约 97%+

同时通过：

* blocking rules
* 回归报告
* CI 发布门禁
* focused verification
* release verification

约束检索改动，保障优化可评估、可复现、可回滚。

#### 面试价值

该亮点证明候选人具备 AI 系统质量治理意识，能够用工程化方式约束 RAG 的不确定性。

### 5.18 主要挑战与解决方案

| 挑战        | 为什么重要            | 解决方案                                               |
| --------- | ---------------- | -------------------------------------------------- |
| 模糊表达下检索不准 | 企业用户经常口语化提问      | query rewrite、query router、hybrid retrieval、rerank |
| 编号 / 条款漏召 | 向量检索对精确字符串不稳定    | BM25、exact query 识别、lexical 权重提升                   |
| 相似文档混淆    | 制造业文档标题和内容高度相似   | metadata anchor、document family policy、rerank      |
| 引用不可信     | 企业用户关心答案来源       | Citation Pipeline、used_documents、grounding checks  |
| 权限泄露风险    | 企业 RAG 不能召回不可见文档 | 检索阶段 ACL filtering                                 |
| OCR 噪声    | 扫描件和表格会污染检索      | PaddleOCR、结构化切块、OCR 队列隔离                           |
| 多轮追问断裂    | 用户追问常省略实体        | Memory-Aware Query Rewrite                         |
| 发布回归      | 检索策略调整可能影响旧 case | frozen + rolling 样本、blocking rules、CI 门禁           |

### 5.19 决策风格

* 避免重写整个技术栈，优先渐进式加固。
* 将策略加固与功能扩展分离。
* 将检索质量和发布证据视为核心产品职责。
* 将权限、可审计性和引用追溯作为企业 RAG 的一等设计输入。
* 使用 Make targets、CI、评测样本和回归报告把经验转成可重复工程流程。
* 对模型能力保持克制，不把流畅回答等同于可信回答。

### 5.20 示例面试问题

#### 问题：Enterprise-grade RAG 解决什么问题？

**模型回答要点**

* 它将制造业企业内部大量制度文档、SOP、设备资料和业务知识转化为可检索、可问答、可追溯的知识系统。
* 它支持多格式文档入库、OCR/解析、结构化切块、混合检索、权限过滤、引用溯源和多轮问答。
* 它适合私有部署、权限边界严格、答案必须可审计的企业场景。

#### 问题：它和简单 ChatPDF 有什么不同？

**模型回答要点**

* 简单 ChatPDF 通常是上传文档后直接向量检索 + LLM 回答。
* 该系统额外处理企业级场景中的文档摄取、OCR、结构化切块、query router、混合检索、rerank、ACL 权限过滤、Citation Pipeline、多轮追问改写、评测样本和发布门禁。
* 它不是只追求回答流畅，而是追求可追溯、可评测、可控权和可维护。

#### 问题：你在项目中的主要职责是什么？

**模型回答要点**

* 候选人独立负责核心架构与落地开发。
* 具体包括文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、智能问答、多轮追问和评测回归。
* 项目累计实现 89 个 API 路由、26 个核心 schema 模块；当前 PDF 简历还记录 release capability dashboard 中 12 项 blocking capability 全部通过。

---

## 6. 项目：检索质量与评测治理

### 6.1 项目总结

该仓库和简历共同体现出一个重要特点：检索质量被当作一个受治理的工程界面，而不是模型输出的副作用。

该项目包含：

* frozen 样本
* rolling 样本
* verified release truth
* optimization cases
* focused verification
* blocking rules
* 回归报告
* CI 发布门禁
* Makefile release gates
* request traces
* request snapshots
* replay 机制

这些机制用于让 RAG 优化可评估、可复现、可回滚。

### 6.2 目标

* 建立可重复的方法，衡量检索和问答行为在语料、prompt、策略、权限、memory 和 runtime 变化后是否仍然可靠。
* 防止“局部优化、整体回归”。
* 防止发布时只靠人工试几个问题判断质量。
* 将 AI 系统质量控制转化为工程流程。

### 6.3 问题陈述

企业 RAG 系统经常静默失败：

1. 排序权重调整可能改善一个 query，同时破坏另一个 query。
2. 文档刷新可能使样本真值漂移。
3. memory 或 query rewrite 变更可能导致跨主题误继承。
4. prompt 改动可能让引用和 used_documents metadata 不一致。
5. 权限策略改动可能导致可见范围异常。
6. OCR 处理变化可能影响 chunk 质量。
7. 检索 top-k 看似命中，但最终 answer grounding 失败。

因此需要把检索质量纳入可执行、可审计、可回归的治理流程。

### 6.4 职责

| 职责                      | 描述                                          |
| ----------------------- | ------------------------------------------- |
| 定义发布真值                  | verified frozen samples / frozen 样本作为核心稳定基准 |
| 管理滚动样本                  | rolling 样本持续吸收线上或测试中新发现的问题                  |
| 管理优化 case               | optimization cases 保护历史重要残留问题               |
| 构建 focused verification | 对单点修复做快速验证                                  |
| 构建 release gate         | 发布前运行完整验证                                   |
| 生成回归报告                  | 对比改动前后结果                                    |
| 设置 blocking rules       | 核心样本退化则阻塞发布                                 |
| 提供诊断证据                  | traces、snapshots、replay 用于定位失败层             |

### 6.5 评测架构

1. frozen 样本用于稳定发布基准。
2. rolling 样本用于持续吸收新 case。
3. optimization cases 用于记录重要残留问题。
4. focused verification 用于快速验证单点修复。
5. release verification 用于发布前完整检查。
6. blocking rules 用于阻断核心能力退化。
7. 回归报告用于比较改动前后差异。
8. traces 和 snapshots 用于定位失败原因。
9. replay 用于复现问题。
10. CI 发布门禁用于防止不合格改动进入发布流程。

### 6.6 具体发布门禁组成

| 门禁 / 命令                            | 具体范围                                                                                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `make verify-retrieval-focused`    | 单个 residual、单个 case 或单个窄范围修复                                                                                                               |
| `make verify-retrieval-quick`      | 不进行完整 live replay 的治理检查                                                                                                                    |
| `make verify-retrieval-release`    | 严格检索发布门禁，覆盖 verified truth、optimization-case regressions、retrieval eval、chat-memory behavioral gate、ACL visibility、diff 和 threshold checks |
| `make verify-v1-release-readiness` | 检索发布 + portal evidence + ingest/preview/delete/rebuild smoke + OCR runtime gate + health + waiver governance                               |

### 6.7 可衡量信号

| 信号                           | 值         |
| ---------------------------- | --------- |
| PDF 简历当前 API 路由              | 89 个      |
| PDF 简历当前核心 schema 模块        | 26 个      |
| PDF 简历 release capability dashboard | 12 项 blocking capability 全部通过 |
| 既有文档治理口径检索评测样本             | 167 条     |
| 既有文档治理口径 Top1 Accuracy       | 约 95%+    |
| 既有文档治理口径 TopK Recall         | 约 97%+    |
| 仓库历史 verified frozen samples | 64 条      |
| 仓库历史 optimization cases      | 22 条      |
| 仓库历史 top-1 accuracy          | 约 90%-95% |
| 仓库历史 top-k recall            | 约 98%     |
| 仓库历史 document coverage       | 约 97%-98% |

### 6.8 为什么这体现工程成熟度

* 系统区分探索性 debug checks 和硬发布门禁。
* 检索正确性只是发布就绪的一部分，还要考虑 memory、ACL、OCR、portal、health。
* 样本治理让 RAG 系统从“凭感觉优化”变成“按证据优化”。
* 回归报告和 blocking rules 能防止修复一个 case 时破坏其他 case。
* 对企业级 AI 系统来说，可复现和可回滚比单次 demo 表现更重要。

### 6.9 示例面试问题

#### 问题：你如何衡量 RAG 检索质量？

**模型回答要点**

* 候选人使用 frozen + rolling 双轨评测体系。
* frozen 样本用于稳定发布基准，rolling 样本用于持续吸收新发现的问题。
* 当前 PDF 简历明确记录 release capability dashboard 中 12 项 blocking capability 全部通过。
* 既有文档治理口径记录了 167 条检索评测样本，覆盖精确查询、语义查询、多轮追问、跨部门补充召回等场景。
* 如使用 Top1 Accuracy 约 95%+、TopK Recall 约 97%+，应说明这是既有文档治理口径，不是当前 PDF 简历直接给出的指标。
* 发布前通过 blocking rules、回归报告和 CI 门禁约束改动。

#### 问题：为什么不只靠人工测试？

**模型回答要点**

* 手工测试适合发现问题，但不适合长期防回归。
* RAG 改动影响面大，排序、权重、改写、权限、OCR、prompt 都可能影响结果。
* 通过评测样本和发布门禁，可以把质量判断从主观感受转成可重复验证。

#### 问题：如果优化一个 case 后另一个 case 坏了怎么办？

**模型回答要点**

* 这正是建立 frozen + rolling 评测体系的原因。
* 每次改动都看整体回归报告，而不是只看当前 case。
* 如果核心样本退化，blocking rules 会阻止发布。
* 对重要 residual 会沉淀为 optimization case，后续持续保护。

---

## 7. 项目：文档摄取、OCR 与知识运营

### 7.1 项目总结

企业级 RAG 的难点不只在检索和生成，还在文档进入系统之前的处理。

该项目处理的文档包括：

* PDF
* Word
* PPT
* Excel
* 扫描件
* 图片型 PDF
* 表格密集文档
* 制度文件
* SOP
* 设备手册
* 维护资料
* 业务流程文档

候选人的工作覆盖文档解析、OCR、表格识别、结构化抽取、切块、索引构建、异步处理、重建 / 重试和预览支持。

### 7.2 目标

* 将异构企业文档转化为可靠的检索资产。
* 保留足够的结构信息，支持基于证据的问答和引用。
* 降低 OCR 噪声、页眉页脚、重复内容、表格丢失对检索质量的影响。
* 通过异步任务队列提升文档摄取稳定性。

### 7.3 文档与内容挑战

| 挑战     | 描述                       |
| ------ | ------------------------ |
| 混合文档格式 | PDF、DOCX、PPTX、XLSX、扫描件混杂 |
| 低质量扫描件 | OCR 准确率受噪声、倾斜、低分辨率影响     |
| 复杂表格   | 合并单元格、多级表头、参数表难以保留       |
| 混合布局   | 表格、图片、正文、标题混排            |
| 内容噪声   | 页眉、页脚、页码、水印、重复片段         |
| 文档结构弱  | 标题层级、条款编号、章节关系可能丢失       |
| 大文档处理慢 | OCR 和解析容易阻塞主流程           |

### 7.4 实现特性

| 能力                      | 描述                                                              |
| ----------------------- | --------------------------------------------------------------- |
| 原生文本提取                  | 能直接提取文本时优先使用原生解析                                                |
| OCR fallback            | 对扫描件和图片型文档使用 OCR                                                |
| 表格识别                    | 对表格密集文档进行识别和结构化处理                                               |
| 结构化 chunking            | 基于标题、条款、段落、表格进行 chunk                                           |
| Contract-aware chunking | 支持 clause、section summary、document summary、table-oriented chunk |
| 异步摄取                    | Celery 后台任务处理                                                   |
| 队列隔离                    | ingest_cpu / ingest_ocr / preview 队列隔离                          |
| 重建 / 重试                 | 支持失败内容重新处理                                                      |
| 预览支持                    | 支持在线预览和原文跳转                                                     |
| 内容治理                    | 降低低价值内容进入检索面                                                    |

### 7.5 具体摄取文件地图

| 能力           | 主要文件                                             |
| ------------ | ------------------------------------------------ |
| 解析文档         | `backend/app/rag/parsers/document_parser.py`     |
| 基础切块         | `backend/app/rag/chunkers/text_chunker.py`       |
| 结构化切块        | `backend/app/rag/chunkers/structured_chunker.py` |
| 生成 embedding | `backend/app/rag/embeddings/client.py`           |
| 存储向量         | `backend/app/rag/vectorstores/qdrant_store.py`   |
| 编排摄取         | `backend/app/services/ingestion_service.py`      |
| 管理文档         | `backend/app/services/document_service.py`       |
| 后台任务         | `backend/app/worker/celery_app.py`               |
| OCR          | `backend/app/rag/ocr/client.py`                  |

### 7.6 企业文档类型

* technical manuals
* maintenance manuals
* operation guides
* contracts and agreements
* policies and 制度 documents
* SOP / WI documents
* scanned PDF files
* image-heavy pages
* complex parameter tables
* internal business knowledge documents
* device documentation
* workflow documents

### 7.7 近期进展信号

* OCR 表格识别从诊断进入优化和验证。
* DOCX 解析支持进入内部验证阶段。
* 摄取质量检查和内容治理行为得到强化。
* 摄取期间加入 searchable title extraction，以改善下游发现能力。
* 异步任务拆分提升了摄取链路稳定性。
* 文档预览和原文跳转能力支撑 Citation Pipeline 的用户体验。

### 7.8 示例面试问题

#### 问题：为什么企业级 RAG 里文档摄取很难？

**模型回答要点**

* 企业真实文档不是干净文本，而是 PDF、Office、PPT、扫描件、表格和图片混合。
* OCR 错误、表格丢失、布局碎片化、标题层级丢失都会影响下游检索和答案质量。
* 所以企业级 RAG 不能只做向量检索，还必须做好解析、OCR、结构化切块和内容治理。

#### 问题：你怎么提升文档入库稳定性？

**模型回答要点**

* 将文档解析、OCR、表格识别、切块和索引构建拆成异步任务链路。
* 基于 Celery 拆分 ingest_cpu、ingest_ocr、preview 等队列，隔离 OCR、IO 和 CPU 密集型任务。
* 支持失败任务重试、文档重建和预览能力，避免单个重任务阻塞主业务流程。

---

## 8. 工作经验画像

### 8.1 当前正式工作经历

| 字段   | 内容                           |
| ---- | ---------------------------- |
| 公司   | 宁波伟立机器人科技股份有限公司              |
| 岗位   | AI 开发工程师                     |
| 时间   | 2026-03 至今                   |
| 项目   | 企业级 RAG 知识库与智能问答平台           |
| 角色   | 独立负责核心架构与落地开发                |
| 行业场景 | 制造业内部知识管理、制度查询、SOP 检索、设备资料问答 |

### 8.2 当前工作内容总结

候选人在宁波伟立机器人科技股份有限公司担任 AI 开发工程师，主要负责面向制造业内部制度文档、SOP、设备资料和业务知识问答场景的企业级 RAG 知识库与智能问答平台。

该工作覆盖：

* 核心架构设计
* 后端 API 开发
* 文档摄取链路
* OCR / 表格识别
* 结构化切块
* Embedding 索引
* 混合检索
* rerank
* 权限过滤
* Citation Pipeline
* 多轮追问改写
* 检索评测
* 发布门禁
* 前端联调
* 部署运维

### 8.3 角色画像：AI 系统架构师 / 技术负责人型

| 类别    | 基于证据的总结                         |
| ----- | ------------------------------- |
| 角色范围  | 端到端负责企业级 RAG 平台核心架构             |
| 主要关注点 | 安全、检索正确性、发布质量、可观测性、企业可运营性       |
| 最强证据  | 架构文档、代码模块、Make 发布门禁、评测样本、简历项目规模 |
| 成就模式  | 将可运行 RAG 栈逐步加固为企业知识问答平台         |

### 8.4 角色画像：全栈 AI 产品工程师

| 类别   | 基于证据的总结                                                                     |
| ---- | --------------------------------------------------------------------------- |
| 后端工作 | FastAPI endpoint、service logic、retrieval/generation paths、ingest operations |
| 前端工作 | React / Vite 门户、工作区、搜索、聊天、文档预览                                              |
| 产品耦合 | 同时处理用户问答体验、文档管理、引用展示和运维界面                                                   |
| 成就模式 | 将模型能力包装成企业可用产品，而不是停留在脚本或 Demo                                               |

### 8.5 角色画像：检索与评估工程师

| 类别   | 基于证据的总结                                                              |
| ---- | -------------------------------------------------------------------- |
| 质量模型 | frozen + rolling、verified samples、optimization cases、release bundles |
| 评估思维 | 质量由治理证据衡量，不靠主观 demo                                                  |
| 成就模式 | 构建机制检测 drift、分类 residual、保护重要修复                                      |

### 8.6 角色画像：平台 / 发布 / 运维工程师

| 类别              | 基于证据的总结                                               |
| --------------- | ----------------------------------------------------- |
| Runtime support | local / remote runtime workflows、Docker、health checks |
| 诊断工具            | traces、snapshots、replay、event logs                    |
| 运维成熟度           | 发布工作流连接 retrieval、memory、ACL、ingest、health            |
| 成就模式            | 缩小功能开发和可部署运行之间的距离                                     |

### 8.7 具体“亲自负责了什么”回答库

| 主题      | 具体回答片段                                                                                                  |
| ------- | ------------------------------------------------------------------------------------------------------- |
| API 设计  | 负责 retrieval search、chat ask、system config 等主要企业契约                                                      |
| 检索      | 参与 retrieval service orchestration、query routing、query profiles、rerank integration、scope policy         |
| 聊天质量    | 参与 citation-backed answering、follow-up handling、prompt constraints、grounding behavior、answer formatting |
| 摄取      | 参与 parsing、OCR、chunking、rebuild/retry、document preview                                                  |
| 权限      | 在检索阶段注入 ACL 条件，支持 global / department / library 权限粒度                                                    |
| 评测      | 构建或维护 frozen + rolling 样本、blocking rules、回归报告、release gates                                             |
| 产品 / UX | 改善 portal search、chat behavior、history performance、document center workflows                            |
| 运维      | 增加或使用 traces、request snapshots、replay、health checks、remote bugfix workflows                             |

### 8.8 示例面试问题

#### 问题：你这段工作最核心的价值是什么？

**模型回答要点**

* 核心价值是把企业内部大量制度、SOP、设备资料和业务文档转成可检索、可问答、可追溯的知识系统。
* 候选人不只是完成某个单点模块，而是覆盖 RAG 平台从文档摄取到检索、问答、权限、引用和评测的完整链路。
* 项目累计 89 个 API 路由、26 个核心 schema 模块，且 release capability dashboard 中 12 项 blocking capability 全部通过；既有文档治理口径还记录了 167 条检索评测样本，体现了工程规模和质量治理意识。

#### 问题：这段经历更偏功能开发还是基础设施建设？

**模型回答要点**

* 两者都有。
* 功能层包括文档中心、智能问答、SOP 检索、多轮追问、引用溯源。
* 基础设施层包括文档摄取、OCR 队列、混合检索、权限过滤、评测样本、发布门禁、traces 和 snapshots。
* 最有价值的是功能交付和工程加固同时推进。

---

## 9. 实习经历

### 9.1 上海企顺信息系统有限公司 IT 工程师

| 字段   | 内容 |
| ---- | ---- |
| 公司   | 上海企顺信息系统有限公司 |
| 岗位   | IT 工程师 |
| 时间   | 2024-10 至 2024-12 |
| 项目   | 联想手机自动化测试外包项目 |

候选人在上海企顺信息系统有限公司实习期间，负责联想手机自动化测试外包项目，跟踪管理 4 个在运行项目，并基于 Linux 环境使用 ADB / Fastboot 与 Python 脚本执行压力测试和稳定性测试，保障设备性能达标。

这段经历体现了候选人在 Linux、自动化脚本、设备调试、测试执行和多项目跟踪方面的工程基础，也为后续 AI 应用工程中的部署、诊断和自动化验证能力提供了早期实践。

### 9.2 convoloo 实习基本信息

| 字段     | 内容                            |
| ------ | ----------------------------- |
| 公司     | convoloo                      |
| 公司描述   | 硅谷高科技公司                       |
| 岗位方向   | 机器学习                          |
| 时间     | 2025-05 至 2025-09             |
| 项目访问地址 | `https://storygen.srj666.com` |

### 9.3 实习内容总结

候选人在 convoloo 实习期间，参与构建基于 Stable Diffusion / ControlNet / LoRA 的故事文本与插画生成系统。系统支持多页故事文本生成、逐页插画一键生成、角色照片上传、LoRA 训练、角色一致性生成、SSE 训练进度推送和前端单页应用集成。

### 9.4 技术栈

| 类型         | 技术                                                 |
| ---------- | -------------------------------------------------- |
| 后端         | Python、FastAPI                                     |
| AI / 生成模型  | Diffusers、Stable Diffusion、ControlNet、LoRA、PyTorch |
| LLM / 应用框架 | LangChain、Ollama、DeepSeek Chat                     |
| 前端         | React、TypeScript、Vite、Node.js                      |
| 通信         | SSE 实时进度推送                                         |

### 9.5 具体工作

1. 基于 FastAPI 封装 Stable Diffusion / ControlNet / LoRA 推理。
2. 实现多页故事文本生成与逐页插画一键生成。
3. 对 prompt / negative prompt 进行日志记录。
4. 对 CLIP token 做安全裁剪，避免输入超限。
5. 设计“上传角色照片 → 训练 LoRA → 生成故事插画”的角色创建闭环。
6. 支持后台异步训练。
7. 支持 SSE 实时进度推送。
8. 支持 LoRA 列表和状态查询。
9. 使用 React + Vite 开发前端单页应用。
10. 将角色设定、故事生成、LoRA 选择、成图参数和图片画廊整合到一个界面。

### 9.6 技术亮点

| 亮点                               | 说明                                     |
| -------------------------------- | -------------------------------------- |
| LoRA 角色一致性                       | 通过角色照片训练 LoRA，在不同场景中保持同一角色外观一致         |
| ControlNet / Stable Diffusion 集成 | 支持更可控的图像生成流程                           |
| Prompt 可复现                       | 记录 prompt、negative prompt、采样步数、随机种子等参数 |
| SSE 实时进度                         | 训练耗时较长，通过 SSE 提供用户可见进度                 |
| 前后端一体化                           | 后端推理与前端交互整合为完整 Web 应用                  |

### 9.7 示例面试问题

#### 问题：convoloo 实习主要做了什么？

**模型回答要点**

* 主要做生成式 AI 应用开发，围绕故事生成和插画生成构建完整系统。
* 后端用 FastAPI 封装 Stable Diffusion、ControlNet 和 LoRA 推理。
* 设计上传角色照片、训练 LoRA、生成角色一致插画的闭环。
* 前端用 React + Vite 整合角色设定、故事生成、LoRA 选择、成图参数和图片画廊。
* 这个实习体现了图像生成、模型推理封装、异步任务、实时进度和前后端集成能力。

#### 问题：这个项目和企业级 RAG 项目有什么共同点？

**模型回答要点**

* 两者都是 AI 应用工程项目，不是单纯模型训练。
* 都需要把模型能力封装成可用产品。
* 都涉及后端服务、前端交互、参数管理、异步任务和部署。
* 不同点是 convoloo 偏图像生成和角色一致性，企业级 RAG 偏文档检索、知识问答、权限和引用溯源。

---

## 10. 项目经历：BOSS AGENT

### 10.1 项目概述

BOSS AGENT 是一个面向 AI Agent 的招聘平台工具层，基于 Python + Click + MCP + SQLite 构建，支持职位搜索、本地候选池、简历 / 面试 AI 辅助、Boss RAG 草稿回复、多平台抽象和结构化工具导出。

该项目的核心定位不是自动批量触达，而是在低风险合规模式下，为 Agent 提供可控的招聘平台工具能力。系统默认阻断批量触达、投递、联系方式交换等敏感动作，并通过 pytest、mypy --strict、ruff 建立工程质量门禁。

### 10.2 项目信息

| 字段   | 内容 |
| ---- | ---- |
| 项目名称 | BOSS AGENT |
| 项目类型 | AI Agent 招聘平台工具层 |
| 技术栈 | Python、Click、httpx、MCP、SQLite、pytest、mypy、Docker、LangChain、LangGraph |
| 主要能力 | 职位搜索、本地候选池、简历 / 面试 AI 辅助、Boss RAG 草稿回复、多平台适配、结构化工具导出 |
| 安全边界 | 默认阻断批量触达、投递、联系方式交换等高风险动作 |

### 10.3 项目职责

1. 独立构建 AI Agent 可调用的招聘平台工具系统。
2. 提供 CLI、MCP Server、Python SDK、OpenAI / Anthropic tool schema 多种接入方式。
3. 设计结构化 JSON envelope 输出协议和错误恢复字段，使 Agent 能稳定解析成功 / 失败状态并进行自动化编排。
4. 抽象多平台适配层，将平台协议、认证、响应包络、风控边界封装在 adapter 内，命令层保持平台无关。
5. 在合规约束下实现 RAG 草稿回复与人工审批链路，避免 Agent 直接执行高风险发送动作。
6. 使用 pytest、mypy --strict、ruff 建立质量门禁。

### 10.4 技术亮点

| 亮点 | 说明 |
| ---- | ---- |
| Agent 工具化接口 | 同时支持 CLI、MCP Server、SDK 和 tool schema，便于不同 Agent Runtime 调用 |
| JSON envelope 协议 | 输出成功状态、错误类型、恢复字段和结构化 payload，降低 Agent 解析不稳定性 |
| 多平台 adapter | 将平台差异封装在 adapter 层，减少命令层与平台协议耦合 |
| 合规安全边界 | 默认不允许 Agent 直接批量触达、投递或交换联系方式 |
| RAG 草稿回复 | 将候选人资料和岗位信息用于生成可审核的草稿，而不是直接发送 |
| 工程质量门禁 | 使用 pytest / mypy --strict / ruff 保护工具层稳定性 |

### 10.5 面试价值

* 该项目证明候选人不仅做 RAG 问答系统，也能把 Agent 工具调用、MCP、结构化输出协议和安全边界结合成实际工具层。
* 项目体现了对高风险自动化的克制：Agent 可以辅助搜索、整理和生成草稿，但敏感动作需要人工审批或明确阻断。
* 项目与企业级 RAG 的共同点是都强调 grounded context、结构化接口、工程质量门禁和可控自动化。

### 10.6 示例面试问题

#### 问题：BOSS AGENT 项目主要解决什么问题？

**模型回答要点**

* 它是一个面向 AI Agent 的招聘平台工具层，让 Agent 可以通过 CLI、MCP Server、SDK 或 tool schema 调用职位搜索、候选池、简历辅助和草稿回复能力。
* 项目重点不是让 Agent 无限制自动投递，而是在合规边界内辅助招聘或求职流程。
* 系统通过 JSON envelope、adapter 抽象和质量门禁提升 Agent 编排稳定性。

#### 问题：这个项目如何体现 Agent 工程化能力？

**模型回答要点**

* 候选人设计了 Agent 可稳定解析的结构化输出协议。
* 使用 MCP Server 和 tool schema 将能力暴露给不同 Agent Runtime。
* 将平台协议、认证、风控边界封装在 adapter 层，降低命令层复杂度。
* 对批量触达、投递、联系方式交换等敏感动作默认阻断，体现对 Agent 安全边界的理解。

---

## 11. 项目经历：乳腺癌良 / 恶性预测系统

### 11.1 项目概述

乳腺癌良 / 恶性预测系统是一个基于公开医学数据构建的端到端机器学习预测系统，覆盖数据清洗、特征工程、模型训练、模型评估、模型序列化、交互式前端和可视化展示。

### 11.2 项目信息

| 字段           | 内容                                                                     |
| ------------ | ---------------------------------------------------------------------- |
| 项目名称         | 乳腺癌良 / 恶性预测系统                                                          |
| 类型           | 机器学习 + 可视化应用                                                           |
| 技术栈          | Python、Pandas、scikit-learn、Streamlit、Plotly、NumPy、Pickle               |
| 模型           | Logistic Regression + 特征标准化 Pipeline                                   |
| 测试集 Accuracy | 97%+                                                                   |
| 访问地址         | `https://breast-cancer-predicto-or37cpd4fwnv4cuemradqx.streamlit.app/` |

### 11.3 项目职责

1. 基于公开医学数据完成数据清洗。
2. 进行特征工程和特征标准化。
3. 使用 Logistic Regression 构建分类模型。
4. 使用 Pipeline 串联标准化器和模型。
5. 在测试集上进行模型评估，accuracy 达到 97%+。
6. 将模型和标准化器序列化存储。
7. 使用 Streamlit 开发交互式前端。
8. 使用 Plotly 实现雷达图可视化。
9. 支持用户通过多特征输入滑块实时获取预测结果和概率。

### 11.4 技术亮点

| 亮点        | 说明                           |
| --------- | ---------------------------- |
| 端到端机器学习流程 | 覆盖数据清洗、训练、评估、序列化和部署          |
| 可复用推理管线   | 模型和标准化器一起保存，避免训练 / 推理特征处理不一致 |
| 可解释可视化    | 使用雷达图展示多特征输入，帮助用户理解预测依据      |
| 轻量部署      | 使用 Streamlit 快速构建可访问 Web 应用  |
| 应用扩展性     | 可扩展至其他医学辅助诊断或结构化数据预测场景       |

### 11.5 示例面试问题

#### 问题：这个机器学习项目体现了什么能力？

**模型回答要点**

* 该项目体现了完整机器学习应用流程能力，而不是只训练一个模型。
* 项目从数据清洗、特征工程、模型训练、评估、序列化到前端部署都有覆盖。
* 使用 Logistic Regression 和标准化 Pipeline 保证训练和推理一致性。
* 使用 Streamlit 和 Plotly 做交互式可视化，让模型结果更容易理解。

#### 问题：为什么用 Logistic Regression？

**模型回答要点**

* 乳腺癌结构化特征数据适合先用可解释性较强的传统机器学习模型做 baseline。
* Logistic Regression 训练稳定、推理快、可解释性好，适合结构化医学分类任务的轻量应用。
* 项目重点不是堆复杂模型，而是打通端到端机器学习应用流程。

---

## 12. 常见面试问答

### 12.1 HR / 通用叙事问题

#### 问题：请做一个自我介绍。

**推荐回答**

我叫孙瑞杰，23 岁，本科毕业于湖北工程学院光电信息科学与工程专业，求职方向是 AI 应用工程师。

我目前在宁波伟立机器人科技股份有限公司担任 AI 开发工程师，主要独立负责一个面向制造业内部制度文档、SOP、设备资料、运维手册和业务知识问答的企业级 RAG 知识库与智能问答平台。这个项目覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、多轮问答、SOP 生成、运行观测和检索评测回归。项目累计实现 89 个 API 路由、26 个核心 schema 模块，release capability dashboard 中 12 项 blocking capability 全部通过。

除此之外，我还做过 BOSS AGENT 招聘平台工具层、乳腺癌良恶性预测系统；也在 convoloo 实习期间做过基于 Stable Diffusion、ControlNet 和 LoRA 的故事插画生成系统，并在上海企顺实习中参与过联想手机自动化测试外包项目。

我的优势是 AI 应用工程化落地能力，不只是调用模型 API，而是能把模型、检索、后端、前端、异步任务、部署和质量评测整合成可运行、可维护的系统。

#### 问题：你最有代表性的项目是什么？

**模型回答要点**

* 最有代表性的项目是企业级 RAG 知识库与智能问答平台。
* 该项目体现了架构、产品、AI、检索、文档处理、权限、引用、评测和部署的综合深度。
* 项目不是简单 Demo，而是包含 89 个 API 路由、26 个核心 schema 模块，并在 release capability dashboard 中 12 项 blocking capability 全部通过的完整工程系统。

#### 问题：你为什么选择 AI 应用工程师方向？

**模型回答要点**

* 候选人更偏工程落地型，喜欢把模型能力做成真实可用系统。
* AI 模型本身重要，但企业真正需要的是能解决业务问题的 AI 应用。
* 企业级 RAG 项目让候选人积累了文档、检索、权限、引用、评测、部署和用户体验方面的经验。
* 因此 AI 应用工程师方向与候选人的项目经历和能力结构高度匹配。

#### 问题：你的核心优势是什么？

**模型回答要点**

1. 有企业级 RAG 项目独立负责经验。
2. 熟悉从文档摄取到问答生成的完整链路。
3. 能处理混合检索、权限过滤、引用溯源和多轮追问等真实企业问题。
4. 有评测回归和发布门禁意识。
5. 前后端、部署、异步任务和模型服务都有实际经验。
6. 熟练使用 Codex、Claude Code、MCP 和 Agent 工作流提升开发效率。

#### 问题：你的不足是什么？

**模型回答要点**

* 当前更强的是 AI 应用落地和工程系统建设，底层模型预训练和大规模分布式训练经验相对少。
* 但是候选人熟悉 PyTorch 和常见训练优化方法，也有机器学习预测系统和 LoRA 相关实践。
* 后续希望继续增强模型训练、模型评估、复杂 Agent 系统和企业级 LLM 平台方面的深度。

#### 问题：为什么考虑新的机会？

**安全回答模板**

希望寻找更聚焦 AI 应用落地、RAG、Agent 或 LLM 工程化方向的机会。当前项目让我积累了企业级 RAG 从架构到落地的完整经验，下一步希望进入更成熟的 AI 团队或更有 AI 产品化空间的环境，把检索增强生成、智能体和企业知识系统做得更深入。

不要主动表达对原公司负面评价。

### 12.2 技术架构问题

#### 问题：系统如何回答一个用户 query？

**模型回答要点**

1. 请求带着用户身份和权限上下文进入 API。
2. 系统判断是否需要多轮记忆。
3. Query rewrite 生成 effective question。
4. Query router 判断 exact / semantic / mixed。
5. 检索阶段注入 ACL 过滤条件。
6. 系统执行 Qdrant 向量召回和 Elasticsearch BM25 召回。
7. 使用 RRF 融合多路召回结果。
8. 使用 reranker 对候选 chunks 排序。
9. 构建 LLM 上下文并进行 citation selection。
10. 模型基于检索证据生成答案。
11. Citation Pipeline 绑定来源文档、页码、片段和原文跳转。
12. 系统记录 traces 和 snapshots 以便诊断。

#### 问题：为什么使用混合检索？

**模型回答要点**

* 企业文档包含文档编号、设备型号、条款号和制度标题，这些内容需要关键词检索。
* 用户自然语言提问又需要语义检索。
* 单纯向量检索对精确字符串不稳定，单纯 BM25 对语义改写不友好。
* 所以系统采用 Qdrant 向量召回 + Elasticsearch BM25 + RRF 融合 + reranker，兼顾精确查询和语义查询。

#### 问题：query router 怎么发挥作用？

**模型回答要点**

* query router 会识别用户问题更偏 exact、semantic 还是 mixed。
* 如果包含编号、型号、条款号，会提高 lexical 权重。
* 如果是解释性、概念性问题，会提高 vector 权重。
* 如果两类信号都有，就走 mixed 权重。
* 这样可以降低编号类问题漏召，也保留语义问答能力。

#### 问题：你怎么解决 RAG 多轮追问问题？

**模型回答要点**

* 候选人没有只把历史对话塞给 LLM，而是让 memory 进入 retrieval。
* 系统将用户展示问题和实际检索问题解耦。
* 对“这个呢”“有没有相关规范”等问题，系统结合近轮摘要、主题锚点、上一轮引用文档和当前追问，生成 effective question。
* 再用 effective question 检索，从而降低多轮追问断裂问题。

#### 问题：如何降低幻觉风险？

**模型回答要点**

* 模型被要求只根据检索上下文回答。
* 检索阶段通过混合检索和 rerank 提供可靠证据。
* 权限阶段通过 ACL 过滤保证只使用用户可见文档。
* 生成阶段通过 Citation Pipeline 将答案与 chunk 证据绑定。
* 如果证据不足，系统应明确拒答或说明知识库没有足够依据。

#### 问题：权限如何实现？

**模型回答要点**

* 权限不能只在前端做，也不能只在答案生成后裁剪。
* 系统在检索阶段注入 ACL 过滤条件。
* 根据用户部门、角色、文档可见范围确定 retrieval scope。
* 支持 global、department、library 等权限粒度。
* 这样可以降低敏感文档被模型看到或被引用的风险。

#### 问题：如何保证 RAG 优化不会越改越乱？

**模型回答要点**

* 使用 frozen + rolling 双轨评测体系。
* 既有文档治理口径记录了 167 条检索评测样本。
* 覆盖精确查询、语义查询、多轮追问、跨部门补充召回等场景。
* 每次修改 query router、rerank、rewrite 或检索权重后，通过回归报告和 blocking rules 检查。
* 如果核心样本退化，就不能发布。

### 12.3 项目执行与质量问题

#### 问题：如何建立发布信心？

**模型回答要点**

* 通过评测样本、回归报告、blocking rules 和 CI 门禁建立发布信心。
* 仓库中还存在 Make-based verification bundles，例如 `make verify-retrieval-release` 和 `make verify-v1-release-readiness`。
* 这些命令将 retrieval、memory、ACL、OCR、portal、health 等能力纳入发布检查。
* 这说明项目不是靠主观试用判断质量，而是有工程化验证流程。

#### 问题：哪些命令能证明项目被生产化？

**模型回答要点**

* `make verify-retrieval-release`
* `make verify-v1-release-readiness`
* `make verify-retrieval-focused`
* `make verify-retrieval-quick`
* `make snapshot-governance-rolling`
* `make portal-chat-browser-smoke`
* `make agent-runtime-bridge`

这些命令说明项目有检索发布签署、V1 就绪验证、样本治理、门户 smoke 和本地 runtime bridge。

#### 问题：如何调试回归？

**模型回答要点**

* 使用 request traces、snapshots、replay 和 focused verification。
* 先判断问题来自文档质量、chunking、query router、retrieval、rerank、memory、prompt 还是 ACL。
* 确认失败层后再做小范围修复。
* 修复后将 case 纳入 rolling 或 optimization case，防止下次回归。

#### 问题：项目最难的工程问题是什么？

**模型回答要点**

* 最难的不是单个模型性能，而是多个因素的耦合：噪声文档、结构化切块、混合检索、权限过滤、多轮记忆、引用溯源和评测回归。
* 企业 RAG 要求答案可信、可追溯、可控权，而不是只要求模型生成流畅。
* 所以候选人投入大量工作在 query router、Memory-Aware Query Rewrite、Citation Pipeline 和评测门禁上。

### 12.4 产品与路线图问题

#### 问题：哪些已经实现，哪些还可以继续优化？

**模型回答要点**

已实现能力包括：

* 文档上传
* OCR / 解析
* 结构化切块
* Embedding 索引
* 混合检索
* reranker 重排序
* 权限过滤
* 引用溯源
* 多轮问答
* 检索评测
* 回归报告
* CI 发布门禁

可继续优化方向包括：

* 更复杂表格的结构化解析
* 更细粒度权限模型
* 更强的多文档对比问答
* 更完善的可观测性 dashboard
* 更深入的 Agent 化文档操作
* 更完整的企业系统集成

#### 问题：下一步高价值改进是什么？

**模型回答要点**

* 强化复杂表格和扫描件处理。
* 深化多轮追问和跨文档对比能力。
* 扩展 observability dashboard。
* 将评测体系进一步自动化。
* 增强与企业系统的集成能力。
* 在保持权限边界的前提下扩展 Agent 工具调用。

---

## 13. 行为类与场景回答

### 13.1 行为回答风格

* 推荐使用简洁 STAR 结构。
* 语气要冷静、事实化、强调所有权。
* 重点放在决策方式、取舍、调试方法和可衡量结果。
* 避免只说“我优化了效果”，要说明如何定位、如何修复、如何防回归。

### 13.2 场景：解决检索不准问题

| STAR      | 内容                                                                                                               |
| --------- | ---------------------------------------------------------------------------------------------------------------- |
| Situation | 企业用户会用文档编号、条款号、设备型号或口语化表达提问，单一向量检索容易漏召或召回相似但错误的文档                                                                |
| Task      | 提升不同类型 query 下的检索稳定性                                                                                             |
| Action    | 构建 Qdrant + Elasticsearch BM25 + RRF + reranker 的混合检索链路，并设计 query router 识别 exact / semantic / mixed 类型，动态调整检索权重 |
| Result    | 既有文档治理口径下 Top1 Accuracy 约 95%+、TopK Recall 约 97%+，编号类和语义类问题稳定性提升                                                     |

### 13.3 场景：解决多轮追问断裂问题

| STAR      | 内容                                                                                  |
| --------- | ----------------------------------------------------------------------------------- |
| Situation | 用户在连续对话中经常问“这个呢”“有没有相关规范”，但这些问题本身缺少完整检索信息                                           |
| Task      | 让系统在多轮对话中仍然能检索到正确文档                                                                 |
| Action    | 设计 Memory-Aware Query Rewrite，将展示问题和实际检索问题解耦，结合近轮摘要、主题锚点和文档上下文生成 effective question |
| Result    | memory 不再只进入 LLM，而是进入 retrieval，降低追问场景下的检索断裂问题                                      |

### 13.4 场景：解决文档摄取不稳定问题

| STAR      | 内容                                                                   |
| --------- | -------------------------------------------------------------------- |
| Situation | 企业文档格式复杂，OCR、表格、Office 解析和预览任务容易互相阻塞                                 |
| Task      | 提升文档入库链路稳定性                                                          |
| Action    | 基于 Celery 拆分 ingest_cpu、ingest_ocr、preview 等队列，隔离 OCR、IO 和 CPU 密集型任务 |
| Result    | 文档摄取链路更加稳定，重任务不容易阻塞主业务流程                                             |

### 13.5 场景：建立 AI 系统质量门禁

| STAR      | 内容                                                                             |
| --------- | ------------------------------------------------------------------------------ |
| Situation | RAG 系统优化容易出现局部改善、整体回归的问题                                                       |
| Task      | 建立可复现、可评估、可回滚的质量控制流程                                                           |
| Action    | 维护 167 条检索评测样本，构建 frozen + rolling 双轨评测体系，并通过 blocking rules、回归报告和 CI 发布门禁约束改动 |
| Result    | 检索优化不再依赖主观感觉，而是有明确指标和回归保护                                                      |

### 13.6 场景：平衡产品 UX 与模型正确性

| STAR      | 内容                                                                                                   |
| --------- | ---------------------------------------------------------------------------------------------------- |
| Situation | 用户判断 AI 产品质量时，不只看答案是否正确，也看引用、原文跳转、速度和交互体验                                                            |
| Task      | 在提升模型和检索质量的同时，让产品可用                                                                                  |
| Action    | 同时改进 answer flow、history performance、search usability、preview behavior 和 citation-backed correctness |
| Result    | 产品不只是离线分数更好，也更容易被用户理解和信任                                                                             |

### 13.7 场景：决定不进行过度工程化

| STAR      | 内容                                    |
| --------- | ------------------------------------- |
| Situation | 大型 AI 系统容易诱发过早重写和投机式抽象                |
| Task      | 在不丢失现有产品价值的情况下提升企业就绪度                 |
| Action    | 渐进加固现有技术栈，保持每个阶段可运行，并将核心策略修复与未来功能扩展分离 |
| Result    | 进展更可靠，迁移风险更低                          |

### 13.8 示例行为问题

#### 问题：你如何处理困难 bug？

**模型回答要点**

* 先判断问题来自数据质量、检索、routing、memory、ACL 还是 generation。
* 使用 traces、snapshots 和 focused checks 确认假设。
* 优先做外科手术式修复，而不是大范围重写。
* 修复后补充评测样本或回归保护。

#### 问题：你如何管理速度和质量的取舍？

**模型回答要点**

* 开发阶段使用 focused verification 保持快速迭代。
* 发布阶段使用 release gate 保证质量。
* 对重要 residual 纳入 optimization cases 或 rolling 样本。
* 这样既能推进交付，也能降低回归风险。

#### 问题：你有哪些领导力或所有权信号？

**模型回答要点**

* 候选人独立负责企业级 RAG 平台核心架构与落地开发。
* 工作覆盖架构、后端、检索、文档摄取、OCR、前端联调、评测和发布门禁。
* 这体现出跨模块推进和端到端负责能力，而不是只完成单点任务。

---

## 14. 简历项目之间的叙事关系

### 14.1 技术成长主线

候选人的技术成长路径可以概括为：

1. 本科理工科背景，具备数学、工程和系统基础。
2. 通过 Coursera 系统学习机器学习和深度学习。
3. 通过乳腺癌良 / 恶性预测系统实践传统机器学习端到端流程。
4. 在上海企顺实习中接触 Linux、ADB / Fastboot、Python 脚本和自动化稳定性测试。
5. 在 convoloo 实习中接触生成式 AI、Stable Diffusion、ControlNet、LoRA、FastAPI 和 React 全栈集成。
6. 通过 BOSS AGENT 项目实践 Agent 工具层、MCP、多平台 adapter、结构化工具输出和合规安全边界。
7. 在宁波伟立机器人科技股份有限公司独立负责企业级 RAG 项目，将 LLM、检索、文档处理、权限、评测和部署整合为完整企业 AI 应用。

### 14.2 推荐面试叙事

候选人不是单点掌握某个模型或框架，而是从机器学习基础、生成式 AI 应用、LLM 工程化，逐步走到企业级 RAG 系统落地。当前最强能力是把 AI 模型能力封装成真实业务系统，尤其擅长处理文档、检索、权限、引用、评测和部署这些企业 AI 应用中的工程问题。

### 14.3 主要项目的能力关系

| 项目                | 体现能力                                                  |
| ----------------- | ----------------------------------------------------- |
| 乳腺癌良 / 恶性预测系统     | 传统机器学习、数据清洗、特征工程、模型评估、轻量部署                            |
| convoloo 故事插画生成系统 | 生成式 AI、Stable Diffusion、ControlNet、LoRA、FastAPI、React |
| BOSS AGENT        | Agent 工具层、MCP、多平台 adapter、结构化输出协议、合规安全边界                 |
| 企业级 RAG 平台        | LLM 应用、RAG 架构、企业知识库、权限、引用、评测、工程化部署                    |

### 14.4 一句话总叙事

候选人的经历从传统机器学习、生成式 AI 应用逐步发展到企业级 RAG 系统落地，核心优势是能够把模型能力、后端服务、前端交互、数据处理、检索系统、权限控制和质量评测整合成可运行、可维护的 AI 应用。

---

## 15. 高置信事实索引

### 15.1 个人信息

1. 姓名：孙瑞杰。
2. 性别：男。
3. 年龄：23 岁。
4. 求职意向：AI 应用工程师。
5. 到岗时间：一个月内到岗。
6. 地区：湖北。
7. 手机：17798303245。
8. 邮箱：[2745124840@qq.com](mailto:2745124840@qq.com)。

### 15.2 教育

1. 湖北工程学院。
2. 光电信息科学与工程。
3. 本科。
4. 2021-09 至 2025-06。

### 15.3 工作经历

1. 宁波伟立机器人科技股份有限公司。
2. AI 开发工程师。
3. 2026-03 至今。
4. 独立负责企业级 RAG 知识库与智能问答平台核心架构与落地开发。
5. 上海企顺信息系统有限公司，IT 工程师，2024-10 至 2024-12。
6. 上海企顺实习内容包括联想手机自动化测试外包项目、4 个在运行项目跟踪、Linux 环境下 ADB / Fastboot 与 Python 脚本压力测试和稳定性测试。

### 15.4 企业级 RAG 项目

1. 面向制造业内部制度文档、SOP、设备资料、运维手册和业务知识问答场景。
2. 支持 PDF / Office / PPT / Excel 等多格式文档入库。
3. 覆盖 OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、多轮追问、智能问答、SOP 生成、运行观测与评测回归。
4. 实现 89 个 API 路由。
5. 实现 26 个核心 schema 模块。
6. release capability dashboard 中 12 项 blocking capability 全部通过。
7. 技术栈包括 Python、FastAPI、React、TypeScript、Celery、Redis、Qdrant、PostgreSQL、Elasticsearch / BM25、MinIO、Docker、vLLM、Qwen、BGE-M3、BGE-reranker-v2-m3、PaddleOCR。

### 15.5 BOSS AGENT 项目

1. 项目名称：BOSS AGENT。
2. 类型：面向 AI Agent 的招聘平台工具层。
3. 技术栈包括 Python、Click、httpx、MCP、SQLite、pytest、mypy、Docker、LangChain、LangGraph。
4. 支持职位搜索、本地候选池、简历 / 面试 AI 辅助、Boss RAG 草稿回复、多平台抽象和结构化工具导出。
5. 默认阻断批量触达、投递、联系方式交换等敏感动作。

### 15.6 convoloo 实习

1. 公司：convoloo。
2. 岗位方向：机器学习。
3. 时间：2025-05 至 2025-09。
4. 技术栈包括 Python、LangChain、FastAPI、Diffusers、Stable Diffusion、ControlNet、LoRA、PyTorch、React、TypeScript、Vite、Node.js、Ollama / DeepSeek Chat。
5. 项目访问地址：`https://storygen.srj666.com`。

### 15.7 乳腺癌预测项目

1. 项目名称：乳腺癌良 / 恶性预测系统。
2. 使用 Logistic Regression + 特征标准化 Pipeline。
3. 测试集 accuracy 达到 97%+。
4. 使用 Streamlit + Plotly 构建交互式前端。
5. 技术栈包括 Python、Pandas、scikit-learn、Streamlit、Plotly、NumPy、Pickle。
6. 项目访问地址：`https://breast-cancer-predicto-or37cpd4fwnv4cuemradqx.streamlit.app/`。

### 15.8 证书

1. Coursera 吴恩达机器学习专项课程。
2. Coursera 吴恩达深度学习专项课程。
3. convoloo 实习证书。
4. 大学英语四级证书。

---

## 16. 低置信或不能编造的内容

| 内容        | 处理方式            |
| --------- | --------------- |
| 当前薪资      | 文档中未提供，不编造      |
| 期望薪资      | 文档中未提供，不编造      |
| 团队人数      | 文档中未提供，不编造      |
| 公司业务收入    | 文档中未提供，不编造      |
| 项目真实用户量   | 文档中未提供，不编造      |
| 项目节省成本    | 文档中未提供，不编造      |
| 领导评价      | 文档中未提供，不编造      |
| 绩效评级      | 文档中未提供，不编造      |
| 公司内部敏感资料  | 不主动披露           |
| 具体未公开业务数据 | 不主动披露           |
| 项目商业 ROI  | 没有明确数据时不编造      |
| 是否带团队     | 没有明确团队信息时不声称带团队 |

---

## 17. 可追溯性索引

### 17.1 来源到主题映射

| 主题                          | 最佳来源                                                                          |
| --------------------------- | ----------------------------------------------------------------------------- |
| 个人信息                        | 简历                                                                            |
| 教育背景                        | 简历                                                                            |
| 当前工作经历                      | 简历                                                                            |
| 企业级 RAG 项目概要                | 简历、README、架构文档                                                                |
| 端到端系统流程                     | `docs/rag-system-architecture.md`                                             |
| 能力范围和指标                     | 简历、`docs/知识库功能与能力范围说明.md`                                                     |
| 企业目标状态和路线图                  | `docs/ENTERPRISE_RAG_EXECUTION_PLAN.md`                                       |
| 近期交付工作和运营进展                 | `docs/weekly-report-2026-06-04.md`、`docs/weekly-report-2026-06-07.md`         |
| 运行时和发布工作流                   | `Makefile`                                                                    |
| Prompt 和 grounded answer 约束 | `backend/app/rag/generators/client.py`                                        |
| 检索链路                        | `retrieval_service.py`、`retrieval_query_router.py`、`query_profile_service.py` |
| 多轮记忆                        | `chat_memory_service.py`                                                      |
| 引用溯源                        | `chat_citation_pipeline.py`                                                   |
| 权限过滤                        | `retrieval_scope_policy.py`                                                   |
| OCR / 摄取                    | `ingestion_service.py`、`document_parser.py`、`ocr/client.py`                   |
| BOSS AGENT                  | 简历项目经历、当前仓库代码                                                               |
| 乳腺癌预测系统                     | 简历项目经历                                                                        |
| 上海企顺 IT 实习                  | 简历实习经历                                                                        |
| convoloo 实习                 | 简历实习经历                                                                        |

### 17.2 高频复用事实

1. 候选人孙瑞杰，23 岁，求职意向为 AI 应用工程师。
2. 本科毕业于湖北工程学院光电信息科学与工程专业。
3. 当前在宁波伟立机器人科技股份有限公司担任 AI 开发工程师。
4. 当前独立负责企业级 RAG 知识库与智能问答平台核心架构与落地开发。
5. 企业级 RAG 项目面向制造业内部制度文档、SOP、设备资料、运维手册和业务知识问答场景。
6. 项目覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、多轮追问、智能问答、SOP 生成、运行观测与评测回归。
7. 项目累计实现 89 个 API 路由、26 个核心 schema 模块。
8. release capability dashboard 中 12 项 blocking capability 全部通过。
9. 技术栈包括 FastAPI、React、Qdrant、Elasticsearch、Redis、Celery、PostgreSQL、MinIO、Docker、vLLM、Qwen、BGE-M3、BGE-reranker-v2-m3、PaddleOCR。
10. 候选人还做过 BOSS AGENT、乳腺癌良 / 恶性预测系统和 convoloo 生成式 AI 实习项目。
11. 候选人有上海企顺 IT 工程师实习经历，涉及 Linux、ADB / Fastboot、Python 脚本和自动化稳定性测试。
12. 候选人熟悉 Codex、Claude Code、MCP、自定义 Skill、Agent Runtime、Harness 和 AGENTS.md 规则体系。

### 17.3 维护说明

1. 如果后续补充正式简历 PDF，应同步更新第 2、3、8、9、10、11、14、15 节。
2. 如果企业级 RAG 项目指标变化，应同步更新第 5、6、14 节。
3. 如果新增项目访问地址，应更新第 9、10、11、14、15 节。
4. 如果新增工作经历，应更新第 8、9、13、14、15 节。
5. 如果候选人确定期望薪资，应更新第 16 节，避免面试 Bot 继续回答“未提供”。
6. 如果项目路线图能力进入生产，应更新第 12.4 节的“已实现 vs 可优化方向”。

---

## 18. 简短版候选人总结

孙瑞杰，23 岁，本科毕业于湖北工程学院光电信息科学与工程专业，求职意向为 AI 应用工程师。目前在宁波伟立机器人科技股份有限公司担任 AI 开发工程师，独立负责企业级 RAG 知识库与智能问答平台核心架构与落地开发。

该项目面向制造业内部制度文档、SOP、设备资料、运维手册和业务知识问答场景，覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、混合检索、重排序、权限过滤、引用溯源、多轮问答、SOP 生成、运行观测和评测回归，累计实现 89 个 API 路由、26 个核心 schema 模块，release capability dashboard 中 12 项 blocking capability 全部通过。

候选人还具备 BOSS AGENT 工具层、机器学习预测系统、生成式 AI 图像应用、LoRA 角色一致性生成、FastAPI 后端、React 前端、Docker 部署和 Agent 工程化经验。整体画像是偏工程落地型的 AI 应用工程师，优势在于能把 LLM、RAG、模型推理、文档处理、权限控制、评测体系和前后端工程整合成可运行、可维护的业务系统。

---

## 19. 一分钟面试口述版

我叫孙瑞杰，23 岁，本科毕业于湖北工程学院光电信息科学与工程专业，求职方向是 AI 应用工程师。

我目前在宁波伟立机器人科技股份有限公司做 AI 开发工程师，主要独立负责一个面向制造业内部制度文档、SOP、设备资料、运维手册和业务知识问答的企业级 RAG 平台。这个系统不是简单的 ChatPDF，而是覆盖文档入库、OCR/解析、结构化切块、Embedding 索引、Qdrant 向量检索、Elasticsearch BM25、RRF 融合、reranker 重排序、权限过滤、引用溯源、多轮追问、SOP 生成、运行观测和检索评测回归的完整系统。

项目目前实现了 89 个 API 路由、26 个核心 schema 模块，release capability dashboard 中 12 项 blocking capability 全部通过。我在项目里比较核心的工作包括混合检索与 query router、Memory-Aware 查询改写、ACL 权限过滤、Citation Pipeline 和 frozen + rolling 双轨评测体系。

除此之外，我还做过 BOSS AGENT 招聘平台工具层和乳腺癌良恶性预测系统；也在 convoloo 实习期间做过基于 Stable Diffusion、ControlNet 和 LoRA 的故事插画生成系统。我的优势是 AI 应用工程化落地能力，能够把模型、检索、后端、前端、异步任务、部署、工具调用和质量评测整合成真正可用的系统。

---

## 20. 面试回答风格建议

### 20.1 总体风格

* 直接。
* 技术细节充分。
* 不夸大。
* 用系统链路证明能力。
* 用指标证明结果。
* 用模块和设计取舍证明参与深度。
* 遇到不知道的问题明确说明边界。

### 20.2 推荐表达方式

推荐多使用：

* “我主要负责的是……”
* “这个问题的难点在于……”
* “我的处理方式是……”
* “系统中我把它拆成了几层……”
* “这个设计的好处是……”
* “为了防止回归，我做了……”
* “这个指标来自既有文档治理口径……”
* “这个能力目前已经实现，后续还可以继续优化……”

避免使用：

* “精通所有大模型”
* “完全解决幻觉”
* “达到生产级零错误”
* “大幅提升业务效率”但没有指标支撑
* “独立完成所有公司 AI 系统”但缺少边界说明
* “项目用户很多”但没有用户量数据
* “节省大量成本”但没有 ROI 数据

### 20.3 最适合的岗位表达

候选人最适合的岗位方向：

* AI 应用工程师
* RAG 应用工程师
* LLM 应用开发工程师
* AI 后端工程师
* AI 产品工程师
* 企业知识库工程师
* Agent 工程师

理由：

* 有企业级 RAG 独立负责经验。
* 有完整 AI 应用工程链路经验。
* 熟悉模型、检索、后端、前端、部署、评测。
* 有生成式 AI、传统机器学习和 Agent 工程化补充经历。
