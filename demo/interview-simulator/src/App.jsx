import { useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  BookOpenText,
  CheckCircle,
  Clock,
  FileDoc,
  Lightbulb,
  LockKey,
  Microphone,
  Notebook,
  Sparkle,
  Target,
} from "@phosphor-icons/react";
import "./styles.css";

const interviewDeck = [
  {
    id: "intro",
    short: "自我介绍",
    category: "基础信息",
    state: "done",
    duration: "4 分钟",
    prompt:
      "请用两分钟介绍一下你自己，重点讲清楚你为什么从通用后端/AI 工程走到企业级 RAG 方向，以及你最近一份工作的核心成果是什么。",
    followups: ["如何概括你的技术定位？", "为什么会选择 RAG 这个细分方向？"],
    answer:
      "我目前的定位更偏 AI 应用工程师，工作重点是把检索、模型、后端服务和业务工作流做成可落地系统。最近一份工作里，我负责的是企业级 RAG 知识库与智能问答平台，核心关注点不是只把模型接起来，而是把文档入库、OCR、切块、检索、重排、引用和权限整成一条稳定链路。",
    sources: [
      {
        id: "intro-resume",
        type: "verified",
        title: "个人简历 - AI 应用工程师",
        note: "简历 · 已验证",
        updatedAt: "更新于 2026-06-01",
        excerpt: "求职方向为 AI 应用工程师，当前主项目为企业级 RAG 知识库与智能问答平台。",
      },
    ],
    outline: ["背景概括", "当前角色", "RAG 方向动机", "最近项目成果"],
  },
  {
    id: "system-design",
    short: "系统设计",
    category: "系统设计",
    state: "active",
    duration: "8 分钟",
    prompt:
      "请设计一个支持每秒百万级请求的短链接服务，需要考虑高可用、低延迟、可扩展性和安全性。请说明整体架构、关键组件的设计思路以及如何应对高并发场景。",
    followups: [
      "如何生成和存储短链键？",
      "如何保证系统的高可用和容灾？",
      "如何统计点击数据并保证准确性？",
    ],
    answer:
      "整体架构采用分层设计，核心目标是高可用、低延迟与可扩展。\n\n1. 架构概览\n- 接入层：通过 DNS + Anycast 将流量就近接入，使用负载均衡（如 Nginx/Envoy）分发请求。\n- 服务层：短链接服务无状态，水平扩展，核心链路为“短链生成 / 查询重定向”。\n- 存储层：短链元数据存储在分布式 KV（如 Redis Cluster / TiKV），点击统计使用流式计数 + 离线聚合。\n- 数据层：冷数据归档到对象存储（如 S3/OSS），报表通过离线计算系统生成。\n- 可观测性：全链路监控、限流降级、灰度发布。\n\n2. 关键组件设计\n- 短链生成：采用 Base62 编码的 Snowflake ID，支持自定义短链；冲突通过重试解决。\n- 缓存策略：热点短链缓存到 Redis，设置合理 TTL；布隆过滤器拦截非法请求。\n- 重定向服务：读路径优先走缓存，缓存 miss 再查持久层，结果异步回填。",
    sources: [
      {
        id: "source-shortlink",
        type: "verified",
        title: "短链服务项目（ShortLinker）",
        note: "代码仓库 · 已验证",
        updatedAt: "更新于 2024-03-12",
        excerpt: "具备短链生成、重定向、缓存回填和数据归档设计经验，可复用到系统设计回答。",
      },
      {
        id: "source-resume-backend",
        type: "verified",
        title: "个人简历 - 高级后端工程师",
        note: "简历 · 已验证",
        updatedAt: "更新于 2024-06-01",
        excerpt: "有分布式系统、接口服务和性能优化相关经历，可支撑高并发题目的答题结构。",
      },
      {
        id: "source-concurrency",
        type: "inference",
        title: "对百万级 QPS 的性能优化经验",
        note: "合理推断",
        updatedAt: "基于项目与经历推断",
        excerpt: "可以谈高并发设计原则，但不要编造成真实线上指标，应明确为架构层面的设计回答。",
      },
      {
        id: "source-architecture",
        type: "verified",
        title: "分布式系统容灾方案实践",
        note: "技术文档 · 已验证",
        updatedAt: "更新于 2024-02-18",
        excerpt: "可作为高可用、监控、限流和灰度发布部分的答题骨架。",
      },
    ],
    outline: ["架构概览", "关键组件设计", "高并发应对策略", "高可用与容灾", "安全性设计", "监控与运维", "总结"],
  },
  {
    id: "algorithms",
    short: "算法与数据结构",
    category: "算法与数据结构",
    state: "queued",
    duration: "6 分钟",
    prompt: "如何设计一个支持 Top K 热门查询的实时统计系统？",
    followups: ["如何做分桶与滑窗？", "海量数据下如何控制内存？"],
    answer: "",
    sources: [],
    outline: ["数据流入口", "窗口聚合", "堆与近似算法", "扩展性"],
  },
  {
    id: "engineering",
    short: "工程实践",
    category: "工程实践",
    state: "queued",
    duration: "5 分钟",
    prompt: "你如何保证一个 AI 功能上线后可观测、可回滚、可评估？",
    followups: ["灰度怎么做？", "回归如何建？"],
    answer: "",
    sources: [],
    outline: ["发布门禁", "观测指标", "回滚预案", "离线评估"],
  },
  {
    id: "business",
    short: "业务理解",
    category: "业务理解",
    state: "queued",
    duration: "5 分钟",
    prompt: "如果业务方只关心回答速度，你会如何解释检索质量的重要性？",
    followups: ["如何平衡速度与正确性？"],
    answer: "",
    sources: [],
    outline: ["用户目标", "质量风险", "速度折中", "实验验证"],
  },
  {
    id: "behavioral",
    short: "行为面试",
    category: "行为面试",
    state: "queued",
    duration: "4 分钟",
    prompt: "讲一个你独立定位复杂问题并推动闭环的案例。",
    followups: ["最难的部分是什么？", "你如何与其他人协同？"],
    answer: "",
    sources: [],
    outline: ["情境", "任务", "行动", "结果"],
  },
];

const sourceTabs = [
  { id: "all", label: "全部", count: 7 },
  { id: "verified", label: "已验证", count: 5 },
  { id: "inference", label: "推断", count: 2 },
];

const categorySummary = [
  { label: "系统设计", value: 2 },
  { label: "算法与数据结构", value: 1 },
  { label: "工程实践", value: 1 },
  { label: "业务理解", value: 0 },
  { label: "行为面试", value: 0 },
];

const hintByCategory = {
  基础信息: "用“当前角色 → 代表性项目 → 为什么匹配岗位”的三段式组织。",
  系统设计: "先给分层架构，再补关键组件、瓶颈点和故障预案，避免一上来深挖单点实现。",
  工程实践: "优先说发布门禁、可观测性和评估回路，形成上线闭环。",
  default: "先给结论，再给证据，最后补限制与边界。",
};

function getSourceStatusLabel(type) {
  if (type === "verified") return "已验证";
  if (type === "inference") return "合理推断";
  return "全部来源";
}

export function App() {
  const [questions, setQuestions] = useState(interviewDeck);
  const [activeQuestionId, setActiveQuestionId] = useState("system-design");
  const [activeSourceTab, setActiveSourceTab] = useState("all");
  const [selectedSourceId, setSelectedSourceId] = useState("source-shortlink");
  const [statusText, setStatusText] = useState("自动保存于 14:30:25");
  const [isRecording, setIsRecording] = useState(false);
  const [isPendingNext, setIsPendingNext] = useState(false);

  const activeQuestion = useMemo(
    () => questions.find((question) => question.id === activeQuestionId) ?? questions[0],
    [activeQuestionId, questions],
  );

  const filteredSources = useMemo(() => {
    if (activeSourceTab === "all") return activeQuestion.sources;
    return activeQuestion.sources.filter((source) => source.type === activeSourceTab);
  }, [activeQuestion.sources, activeSourceTab]);

  const selectedSource =
    filteredSources.find((source) => source.id === selectedSourceId) ?? filteredSources[0] ?? null;

  const answerValue = activeQuestion.answer;
  const answerLength = answerValue.replace(/\s/g, "").length;
  const progressValue = Math.round(((questions.findIndex((item) => item.id === activeQuestion.id) + 1) / questions.length) * 100);
  const completedCount = questions.filter((question) => question.state === "done").length;

  useEffect(() => {
    if (!activeQuestion.sources.length) return;
    const candidate =
      activeQuestion.sources.find((source) => source.id === selectedSourceId) ??
      activeQuestion.sources[0];
    setSelectedSourceId(candidate.id);
  }, [activeQuestion, selectedSourceId]);

  useEffect(() => {
    if (!answerValue) return;
    const timer = window.setTimeout(() => {
      const stamp = new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
      setStatusText(`自动保存于 ${stamp}`);
    }, 600);
    return () => window.clearTimeout(timer);
  }, [answerValue]);

  function updateAnswer(nextAnswer) {
    setQuestions((currentQuestions) =>
      currentQuestions.map((question) =>
        question.id === activeQuestion.id ? { ...question, answer: nextAnswer } : question,
      ),
    );
    setStatusText("正在保存草稿...");
  }

  function handleHintInsert() {
    const hint = hintByCategory[activeQuestion.category] ?? hintByCategory.default;
    const nextAnswer = answerValue
      ? `${answerValue}\n\n提示补充：${hint}`
      : `建议回答结构：${hint}`;
    updateAnswer(nextAnswer);
  }

  function handleQuestionSelect(questionId) {
    setActiveQuestionId(questionId);
    setIsPendingNext(false);
  }

  function handleSubmit() {
    setQuestions((currentQuestions) =>
      currentQuestions.map((question) => {
        if (question.id === activeQuestion.id) {
          return { ...question, state: "done" };
        }
        return question;
      }),
    );
    setStatusText("回答已提交，可进入评估。");
    setIsPendingNext(true);
  }

  function handleNextQuestion() {
    const currentIndex = questions.findIndex((question) => question.id === activeQuestion.id);
    const nextQuestion = questions[currentIndex + 1];
    if (!nextQuestion) return;

    setQuestions((currentQuestions) =>
      currentQuestions.map((question, index) => {
        if (question.id === activeQuestion.id) {
          return { ...question, state: "done" };
        }
        if (index === currentIndex + 1) {
          return { ...question, state: "active" };
        }
        return question;
      }),
    );
    setActiveQuestionId(nextQuestion.id);
    setIsPendingNext(false);
    setStatusText("已切换到下一题，请继续作答。");
  }

  return (
    <main className="app-shell">
      <aside className="session-pane">
        <div className="brand-block">
          <div className="brand-mark">
            <Target size={20} weight="bold" />
          </div>
          <div>
            <h1>AI 面试模拟器</h1>
            <p>企业级 RAG 面试准备</p>
          </div>
        </div>

        <section className="session-card">
          <div className="session-card__header">
            <span>面试会话</span>
            <span className="live-dot">
              <span className="live-dot__point" />
              进行中
            </span>
          </div>
          <h2>高级后端工程师</h2>
          <p>企业：字节跳动</p>
          <p>岗位 ID：Backend-2024-07-058</p>
        </section>

        <section className="progress-card">
          <div className="card-title-row">
            <h3>进度 {questions.findIndex((item) => item.id === activeQuestion.id) + 1} / {questions.length}</h3>
            <span>{progressValue}%</span>
          </div>
          <div className="progress-track" aria-hidden="true">
            <div className="progress-track__bar" style={{ width: `${progressValue}%` }} />
          </div>

          <ol className="round-list">
            {questions.map((question, index) => {
              const isActive = question.id === activeQuestion.id;
              return (
                <li key={question.id}>
                  <button
                    type="button"
                    className={`round-item ${isActive ? "is-active" : ""}`}
                    onClick={() => handleQuestionSelect(question.id)}
                  >
                    <span className={`round-item__index round-item__index--${question.state}`}>
                      {question.state === "done" ? <CheckCircle size={18} weight="fill" /> : index + 1}
                    </span>
                    <span className="round-item__content">
                      <strong>{question.short}</strong>
                      <em>{isActive ? "当前问题" : question.state === "done" ? "已完成" : "待回答"}</em>
                    </span>
                  </button>
                </li>
              );
            })}
          </ol>
        </section>

        <section className="category-card">
          <h3>问题分类</h3>
          <ul>
            {categorySummary.map((item) => (
              <li key={item.label}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </li>
            ))}
          </ul>
        </section>

        <section className="hint-card">
          <div className="hint-card__icon">
            <Lightbulb size={18} weight="fill" />
          </div>
          <div>
            <h3>提示</h3>
            <p>结合你的经验与证据操作答，引用来源可提升回答可信度。</p>
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">{activeQuestion.category}</span>
            <h2>面试官提问</h2>
          </div>
          <div className="meta-pill">
            <Clock size={18} />
            建议时长：{activeQuestion.duration}
          </div>
        </header>

        <article className="question-panel">
          <p className="question-panel__prompt">{activeQuestion.prompt}</p>
          <div className="question-panel__followups">
            <h3>追问方向（可能）</h3>
            <ul>
              {activeQuestion.followups.map((followup) => (
                <li key={followup}>{followup}</li>
              ))}
            </ul>
          </div>
        </article>

        <section className="answer-region">
          <div className="answer-region__header">
            <div>
              <h3>你的回答</h3>
              <p>
                <span className="answer-region__verified-dot" />
                已连接证据库（简历 / 项目 / 技术文档）
              </p>
            </div>
            <div className="answer-region__status">
              <span>{statusText}</span>
              <CheckCircle size={18} weight="fill" />
            </div>
          </div>

          <div className="editor-shell">
            <textarea
              aria-label="回答编辑器"
              className="editor-shell__textarea"
              value={answerValue}
              onChange={(event) => updateAnswer(event.target.value)}
              placeholder="在这里组织你的回答..."
            />
            <div className="editor-toolbar">
              <div className="editor-toolbar__group">
                <button type="button">B</button>
                <button type="button">I</button>
                <button type="button">H</button>
                <button type="button">•</button>
                <button type="button">1.</button>
              </div>
              <div className="editor-toolbar__group">
                <button type="button">
                  <BookOpenText size={16} />
                </button>
                <button type="button">
                  <Notebook size={16} />
                </button>
                <span>已输入 {answerLength} 字</span>
              </div>
            </div>
          </div>
        </section>
      </section>

      <aside className="evidence-pane">
        <section className="evidence-card">
          <div className="card-title-row">
            <h3>证据来源</h3>
            <span className="help-dot">i</span>
          </div>

          <div className="source-tabs" role="tablist" aria-label="证据筛选">
            {sourceTabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`source-tab ${activeSourceTab === tab.id ? "is-active" : ""}`}
                onClick={() => setActiveSourceTab(tab.id)}
              >
                {tab.label} {tab.count}
              </button>
            ))}
          </div>

          <div className="source-list">
            {filteredSources.map((source) => (
              <button
                key={source.id}
                type="button"
                className={`source-item ${selectedSourceId === source.id ? "is-selected" : ""} ${source.type === "inference" ? "is-warning" : ""}`}
                onClick={() => setSelectedSourceId(source.id)}
              >
                <div className="source-item__icon">
                  {source.type === "verified" ? <FileDoc size={18} /> : <Sparkle size={18} />}
                </div>
                <div className="source-item__body">
                  <strong>{source.title}</strong>
                  <span className={`source-badge source-badge--${source.type}`}>{source.note}</span>
                  <em>{source.updatedAt}</em>
                </div>
                {selectedSourceId === source.id ? <CheckCircle size={18} weight="fill" /> : null}
              </button>
            ))}
          </div>

          <button type="button" className="ghost-link">
            查看全部来源（7）
            <ArrowRight size={16} />
          </button>
        </section>

        <section className="outline-card">
          <div className="card-title-row">
            <h3>回答大纲（建议）</h3>
          </div>
          <ol>
            {activeQuestion.outline.map((item, index) => (
              <li key={item} className={index === 1 ? "is-current" : ""}>
                <span className="outline-index">{index + 1}</span>
                <span>{item}</span>
              </li>
            ))}
          </ol>
          {selectedSource ? (
            <div className="source-summary">
              <div className="source-summary__header">
                <LockKey size={16} />
                <span>{getSourceStatusLabel(selectedSource.type)}</span>
              </div>
              <p>{selectedSource.excerpt}</p>
            </div>
          ) : null}
        </section>
      </aside>

      <footer className="action-bar">
        <button
          type="button"
          className={`action-btn action-btn--ghost ${isRecording ? "is-recording" : ""}`}
          onClick={() => setIsRecording((current) => !current)}
        >
          <Microphone size={20} weight={isRecording ? "fill" : "regular"} />
          <span>
            {isRecording ? "录音中..." : "开始录音"}
            <em>语音输入更高效</em>
          </span>
        </button>

        <button type="button" className="action-btn action-btn--ghost" onClick={handleHintInsert}>
          <Lightbulb size={20} />
          <span>
            请求提示
            <em>可获得思路提示</em>
          </span>
        </button>

        <button type="button" className="action-btn action-btn--primary" onClick={handleSubmit}>
          <ArrowRight size={20} />
          <span>
            提交回答
            <em>提交后可查看评估</em>
          </span>
        </button>

        <button
          type="button"
          className="action-btn action-btn--muted"
          onClick={handleNextQuestion}
          disabled={!isPendingNext}
        >
          <CheckCircle size={20} />
          <span>
            下一题
            <em>{isPendingNext ? "提交后解锁" : "提交后解锁"}</em>
          </span>
        </button>

        <div className="countdown-card">
          <span>准备下一题中...</span>
          <strong>{isPendingNext ? "预计 3 秒" : `${completedCount} 题已完成`}</strong>
        </div>
      </footer>
    </main>
  );
}
