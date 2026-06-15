import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  Lightning,
  MagnifyingGlass,
  PaperPlaneTilt,
  PlayCircle,
  Quotes,
  Sparkle,
  User,
  WarningCircle,
} from "@phosphor-icons/react";
import "./styles.css";

const starterPrompts = [
  "请介绍一下企业级 RAG 项目的核心架构，以及你在里面负责的部分。",
  "如果面试官追问多轮问答和记忆管理，你会怎么解释具体实现？",
  "请说明这个项目里引用溯源为什么重要，具体是怎么落地的？",
  "如果被问到评测指标为什么有不同口径，你会怎么回答？",
  "请用 STAR 结构讲一个你在企业级 RAG 项目里解决复杂问题的例子。",
];

const emptyAnswer = {
  ok: false,
  answer: "",
  citations: [],
  reasoningSummary: null,
  delivery: null,
  draftId: "",
  draftIntent: "",
  auditStatus: "idle",
  errorMessage: "",
  latencyMs: null,
  askedAt: null,
};

const sessionStorageKey = "boss-rag-demo-thread-id";

function loadOrCreateSessionId() {
  const existing = globalThis.localStorage?.getItem(sessionStorageKey);
  if (existing) return existing;
  const created =
    globalThis.crypto?.randomUUID?.() ?? `interview-${Date.now()}`;
  globalThis.localStorage?.setItem(sessionStorageKey, created);
  return created;
}

function titleFromCitation(citation, index) {
  return (
    citation.title ||
    citation.document_name ||
    citation.document_title ||
    citation.file_name ||
    citation.source ||
    citation.library_path ||
    citation.path ||
    citation.chunk_id ||
    `引用 ${index + 1}`
  );
}

function detailFromCitation(citation) {
  const items = [];
  if (citation.department_name) items.push(String(citation.department_name));
  if (citation.library_path) items.push(String(citation.library_path));
  if (citation.section_label) items.push(String(citation.section_label));
  if (citation.page_no !== undefined && citation.page_no !== null) {
    items.push(`p.${citation.page_no}`);
  }
  if (citation.score !== undefined && citation.score !== null) {
    items.push(`score ${Number(citation.score).toFixed(3)}`);
  }
  return items.join(" · ");
}

function excerptFromCitation(citation) {
  return (
    citation.snippet ||
    citation.quote ||
    citation.text ||
    citation.excerpt ||
    citation.content ||
    "当前引用未返回可直接展示的片段。"
  );
}

function normalizeReasoningSummary(reasoningSummary) {
  if (!reasoningSummary || typeof reasoningSummary !== "object") return [];

  function formatReasoningValue(value) {
    if (Array.isArray(value)) {
      return value
        .map((item) => {
          if (item && typeof item === "object") {
            return [item.label, item.detail].filter(Boolean).join(" - ");
          }
          return String(item);
        })
        .join(" / ");
    }

    if (value && typeof value === "object") {
      return Object.entries(value)
        .map(([key, nestedValue]) => `${key}: ${String(nestedValue)}`)
        .join(" / ");
    }

    return String(value);
  }

  return Object.entries(reasoningSummary)
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([key, value]) => ({
      key,
      value: formatReasoningValue(value),
    }));
}

export function App() {
  const [question, setQuestion] = useState(starterPrompts[0]);
  const [history, setHistory] = useState([]);
  const [thread, setThread] = useState([]);
  const [result, setResult] = useState(emptyAnswer);
  const [isLoading, setIsLoading] = useState(false);
  const [selectedCitationIndex, setSelectedCitationIndex] = useState(0);
  const [bridgeState, setBridgeState] = useState({
    loading: true,
    configured: false,
    ready: false,
    authMode: "unknown",
    endpoint: "/api/agent/ask",
    errorMessage: "",
  });
  const [sessionId] = useState(() => loadOrCreateSessionId());

  // ── Boss Apply 状态 ──────────────────────────────────────────
  const [applyMode, setApplyMode] = useState(false);
  const [applyForm, setApplyForm] = useState({
    security_id: "",
    job_id: "",
    resume_name: "default",
    title: "",
    company: "",
    message: "",
  });
  const [applyResult, setApplyResult] = useState(null);
  const [applyLoading, setApplyLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchCity, setSearchCity] = useState("北京");
  const [searchResults, setSearchResults] = useState([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [chatTargets, setChatTargets] = useState([]);
  const [chatTargetsLoading, setChatTargetsLoading] = useState(false);
  const [chatTargetsError, setChatTargetsError] = useState("");
  const [chatTargetsMeta, setChatTargetsMeta] = useState({
    source: "cache",
    liveReadEnabled: false,
    refreshed: false,
  });
  const [isSendingToBoss, setIsSendingToBoss] = useState(false);
  const [sendResumeWithDraft, setSendResumeWithDraft] = useState(false);

  const reasoningItems = useMemo(
    () => normalizeReasoningSummary(result.reasoningSummary),
    [result.reasoningSummary],
  );
  const selectedCitation = result.citations[selectedCitationIndex] ?? null;
  const questionLength = question.replace(/\s/g, "").length;

  async function loadChatTargets() {
    setChatTargetsLoading(true);
    setChatTargetsError("");
    try {
      const response = await fetch("/api/agent/targets?limit=5");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "读取 Boss 对话目标失败。");
      }
      setChatTargets(Array.isArray(payload.targets) ? payload.targets : []);
      setChatTargetsMeta({
        source: String(payload.source || "cache"),
        liveReadEnabled: Boolean(payload.liveReadEnabled),
        refreshed: Boolean(payload.refreshed),
      });
      setChatTargetsError(payload.refreshError ? String(payload.refreshError) : "");
    } catch (error) {
      setChatTargets([]);
      setChatTargetsError(error instanceof Error ? error.message : "读取 Boss 对话目标失败。");
    } finally {
      setChatTargetsLoading(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function loadBridgeState() {
      try {
        const [response, threadResponse] = await Promise.all([
          fetch("/api/agent/health"),
          fetch(`/api/agent/thread?sessionId=${encodeURIComponent(sessionId)}`),
        ]);
        const data = await response.json();
        const threadPayload = await threadResponse.json();
        if (!cancelled) {
          setBridgeState({
            loading: false,
            configured: Boolean(data.configured),
            ready: Boolean(data.ready),
            authMode: String(data.authMode || "unknown"),
            endpoint: String(data.endpoint || "/api/agent/ask"),
            errorMessage: data.errorMessage ? String(data.errorMessage) : "",
          });
          if (threadPayload.ok && threadPayload.thread) {
            setThread(
              Array.isArray(threadPayload.thread.messages)
                ? threadPayload.thread.messages
                : [],
            );
          }
        }
      } catch (error) {
        if (!cancelled) {
          setBridgeState({
            loading: false,
            configured: false,
            ready: false,
            authMode: "unknown",
            endpoint: "/api/agent/ask",
            errorMessage: error instanceof Error ? error.message : "无法读取本地代理状态。",
          });
        }
      }
    }
    loadBridgeState();
    loadChatTargets();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // ── Boss Apply 处理函数 ──────────────────────────────────────
  async function handleSearch() {
    const q = searchQuery.trim();
    if (!q || searchLoading) return;
    setSearchLoading(true);
    setSearchResults([]);
    try {
      const resp = await fetch("/api/boss/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, city: searchCity }),
      });
      const payload = await resp.json();
      if (payload.ok && Array.isArray(payload.data)) {
        setSearchResults(payload.data);
      }
    } catch (e) {
      console.error("搜索失败", e);
    } finally {
      setSearchLoading(false);
    }
  }

  function pickJob(job) {
    setApplyForm((f) => ({
      ...f,
      security_id: job.security_id || "",
      job_id: job.encrypt_job_id || job.job_id || "",
      title: job.title || job.job_name || "",
      company: job.company || job.brand_name || "",
    }));
    setApplyMode(true);
  }

  function pickTarget(target) {
    setApplyForm((f) => ({
      ...f,
      security_id: target.security_id || "",
      job_id: target.job_id || f.job_id,
      title: target.title || f.title,
      company: target.company || f.company,
    }));
    setApplyMode(true);
  }

  async function handleApply() {
    if (!applyForm.security_id || !applyForm.job_id || applyLoading) return;
    setApplyLoading(true);
    setApplyResult(null);
    try {
      const resp = await fetch("/api/boss/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(applyForm),
      });
      const payload = await resp.json();
      setApplyResult(payload);
    } catch (e) {
      setApplyResult({ ok: false, errorMessage: String(e) });
    } finally {
      setApplyLoading(false);
    }
  }

  async function handleAsk() {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;

    setIsLoading(true);
    setResult({
      ...emptyAnswer,
      auditStatus: "requesting",
      askedAt: new Date().toLocaleTimeString("zh-CN", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    });

    const start = performance.now();

    try {
      const response = await fetch("/api/agent/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: trimmed,
          sessionId,
          mode: "accurate",
          job_id: applyForm.job_id.trim(),
          security_id: applyForm.security_id.trim(),
          auto_send_resume: true,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        if (payload.thread?.messages) {
          setThread(payload.thread.messages);
        }
        throw new Error(payload.errorMessage || "Agent 请求失败，请检查本地服务状态。");
      }

      const nextResult = {
        ok: true,
        answer: String(payload.answer || ""),
        citations: Array.isArray(payload.citations) ? payload.citations : [],
        reasoningSummary:
          payload.reasoningSummary && typeof payload.reasoningSummary === "object"
            ? payload.reasoningSummary
            : null,
        delivery:
          payload.delivery && typeof payload.delivery === "object"
            ? payload.delivery
            : null,
        draftId: String(payload.draftId || ""),
        draftIntent: String(payload.draftIntent || ""),
        auditStatus: String(payload.auditStatus || "answered"),
        errorMessage: "",
        latencyMs: Math.round(performance.now() - start),
        askedAt: new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      };

      setResult(nextResult);
      setSendResumeWithDraft(
        String(payload.draftIntent || "") === "resume_share_request",
      );
      setSelectedCitationIndex(0);
      if (payload.thread?.messages) {
        setThread(payload.thread.messages);
      }
      setHistory((current) => [
        {
          id: `${Date.now()}`,
          question: trimmed,
          askedAt: nextResult.askedAt,
          latencyMs: nextResult.latencyMs,
          status: "answered",
        },
        ...current,
      ]);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Agent 请求失败。";
      setResult({
        ...emptyAnswer,
        auditStatus: "agent_failed",
        errorMessage: message,
        latencyMs: Math.round(performance.now() - start),
        askedAt: new Date().toLocaleTimeString("zh-CN", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
        }),
      });
      setHistory((current) => [
        {
          id: `${Date.now()}`,
          question: trimmed,
          askedAt: new Date().toLocaleTimeString("zh-CN", {
            hour: "2-digit",
            minute: "2-digit",
          }),
          latencyMs: Math.round(performance.now() - start),
          status: "failed",
        },
        ...current,
      ]);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleSendToBoss() {
    if (!result.draftId || isSendingToBoss) return;

    setIsSendingToBoss(true);
    try {
      const response = await fetch("/api/agent/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          draftId: result.draftId,
          sessionId,
          security_id: applyForm.security_id.trim(),
          send_resume: sendResumeWithDraft,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        const errorMessage = payload.errorMessage || "发送到 Boss 对话失败。";
        setResult((current) => ({
          ...current,
          delivery:
            payload.delivery && typeof payload.delivery === "object"
              ? payload.delivery
              : {
                  status: errorMessage.includes("security_id")
                    ? "missing_security_id"
                    : "message_failed",
                  message_sent: false,
                  resume_sent: false,
                  error_message: errorMessage,
                },
        }));
        return;
      }

      setResult((current) => ({
        ...current,
        delivery:
          payload.delivery && typeof payload.delivery === "object"
            ? payload.delivery
            : current.delivery,
      }));
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "发送到 Boss 对话失败。";
      setResult((current) => ({
        ...current,
        delivery: {
          status: errorMessage.includes("security_id")
            ? "missing_security_id"
            : "message_failed",
          message_sent: false,
          resume_sent: false,
          error_message: errorMessage,
        },
      }));
    } finally {
      setIsSendingToBoss(false);
    }
  }

  return (
    <main className="app-shell app-shell--rag">
      <aside className="session-pane">
        <div className="brand-block">
          <div className="brand-mark">
            <Sparkle size={20} weight="bold" />
          </div>
          <div>
            <h1>AI 面试问答台</h1>
            <p>Agent 编排并调用 Enterprise RAG</p>
          </div>
        </div>

        <section className="session-card">
          <div className="session-card__header">
            <span>调用状态</span>
            <span
              className={`live-dot ${bridgeState.ready ? "is-success" : "is-muted"}`}
            >
              <span className="live-dot__point" />
              {bridgeState.loading ? "检查中" : bridgeState.ready ? "已连接" : "待配置"}
            </span>
          </div>
          <h2>本地 Agent 代理</h2>
          <p>会话 ID：{sessionId.slice(0, 12)}...</p>
          <p>多轮记忆：{thread.length ? `${Math.ceil(thread.length / 2)} 轮` : "尚未建立"}</p>
          <p>鉴权模式：{bridgeState.authMode}</p>
          <p>调用入口：{bridgeState.endpoint}</p>
        </section>

        <section className="progress-card">
          <div className="card-title-row">
            <h3>示例问题</h3>
            <span>{starterPrompts.length} 条</span>
          </div>
          <div className="prompt-list">
            {starterPrompts.map((item, index) => (
              <button
                key={item}
                type="button"
                className={`prompt-chip ${question === item ? "is-active" : ""}`}
                onClick={() => setQuestion(item)}
              >
                <span className="prompt-chip__index">{index + 1}</span>
                <span>{item}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="category-card">
          <div className="card-title-row">
            <h3>多轮对话</h3>
            <span>{thread.length} 条</span>
          </div>
          <ul className="history-list">
            {thread.length ? (
              thread.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`thread-item thread-item--${item.role}`}
                    onClick={() => {
                      if (item.role === "user") setQuestion(item.content);
                    }}
                  >
                    <strong>{item.role === "assistant" ? "Agent / Memory" : "你"}</strong>
                    <span>{item.content}</span>
                    <em>{item.source}</em>
                  </button>
                </li>
              ))
            ) : history.length ? (
              history.map((item) => (
                <li key={item.id}>
                  <button type="button" onClick={() => setQuestion(item.question)}>
                    <strong>{item.question}</strong>
                    <span>
                      {item.status === "answered" ? "已回答" : "失败"} · {item.askedAt}
                      {item.latencyMs ? ` · ${item.latencyMs}ms` : ""}
                    </span>
                  </button>
                </li>
              ))
            ) : (
              <li className="history-list__empty">还没有提问记录，先输入一个问题试试。</li>
            )}
          </ul>
        </section>

        <section className="category-card">
          <div className="card-title-row">
            <h3>最近 Boss 目标</h3>
            <button
              type="button"
              className="inline-action"
              onClick={loadChatTargets}
              disabled={chatTargetsLoading}
            >
              <ArrowClockwise size={16} />
              {chatTargetsLoading ? "刷新中" : "刷新"}
            </button>
          </div>
          <ul className="history-list">
            {chatTargets.length ? (
              chatTargets.map((target) => (
                <li key={target.conversation_id || target.security_id}>
                  <button type="button" onClick={() => pickTarget(target)}>
                    <strong>{target.company || "未知公司"} · {target.title || "未知职位"}</strong>
                    <span>
                      {(target.recruiter_name || "未命名 HR")}
                      {target.unread_count ? ` · 未读 ${target.unread_count}` : ""}
                    </span>
                    <em>{target.last_message || target.security_id}</em>
                  </button>
                </li>
              ))
            ) : (
              <li className="history-list__empty">
                {chatTargetsLoading
                  ? "正在读取最近 Boss 对话目标..."
                  : chatTargetsMeta.liveReadEnabled
                    ? "还没有读取到可发送目标，可以稍后刷新或手动填写 security_id。"
                    : "当前未开启 Boss 会话读取，暂时只能手动填写 security_id 或使用历史缓存目标。"}
              </li>
            )}
          </ul>
          {chatTargetsError ? (
            <p className="history-list__empty">{chatTargetsError}</p>
          ) : (
            <p className="history-list__empty">
              {chatTargetsMeta.source === "boss_live"
                ? "已从最近 Boss 对话刷新目标，点击即可填充发送目标。"
                : "当前展示的是本地缓存目标。"}
            </p>
          )}
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">Agent 问题输入</span>
            <h2>让 Agent 调用知识库回答</h2>
          </div>
          <div className="meta-pill">
            <Clock size={18} />
            适合 HR / 技术 / 项目 / 行为面试追问
          </div>
        </header>

        <section className="question-panel question-panel--input">
          <div className="input-headline">
            <h3>你的问题</h3>
            <span>{questionLength} 字</span>
          </div>
          <textarea
            className="prompt-editor"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="例如：请介绍一下企业级 RAG 项目的核心架构，以及你负责的模块。"
          />
          <div className="input-actions">
            <button
              type="button"
              className="inline-action"
              onClick={() => setQuestion("")}
            >
              <ArrowClockwise size={16} />
              清空
            </button>
            <button
              type="button"
              className="inline-action inline-action--primary"
              onClick={handleAsk}
              disabled={isLoading || !question.trim()}
            >
              {isLoading ? <Lightning size={16} weight="fill" /> : <PlayCircle size={16} weight="fill" />}
              {isLoading ? "Agent 回答中..." : "让 Agent 回答"}
            </button>
          </div>
        </section>

        <section className="answer-region">
          <div className="answer-region__header">
            <div>
              <h3>Agent 回答结果</h3>
              <p>
                <span className={`answer-region__verified-dot ${result.ok ? "is-success" : ""}`} />
                {result.ok
                  ? `已收到 Agent 最终回答${result.latencyMs ? ` · ${result.latencyMs}ms` : ""}`
                  : isLoading
                    ? "正在等待 Agent 完成编排"
                    : "等待你发起问题"}
              </p>
              {result.delivery?.status === "sent" ? (
                <p>
                  {result.delivery.resume_sent
                    ? "已通过 Boss 真实发送消息，并附带在线简历。"
                    : "已通过 Boss 真实发送这条 Agent 草稿消息。"}
                </p>
              ) : result.delivery?.status === "disabled" ? (
                <p>已识别为发简历请求，但本地未开启自动发送。</p>
              ) : result.delivery?.status === "missing_security_id" ? (
                <p>发送到 Boss 失败：当前没有可用的 `security_id`。</p>
              ) : result.delivery?.status === "resume_failed" || result.delivery?.status === "message_failed" ? (
                <p>
                  {result.delivery.status === "resume_failed"
                    ? `消息已发送，但在线简历发送失败：${result.delivery.error_message || "未知错误"}。`
                    : `发送到 Boss 失败：${result.delivery.error_message || "未知错误"}。`}
                </p>
              ) : null}
            </div>
            <div className="answer-region__status">
              {result.errorMessage ? <WarningCircle size={18} weight="fill" /> : <CheckCircle size={18} weight="fill" />}
              <span>{result.askedAt || "尚未提问"}</span>
            </div>
          </div>

          <div className="editor-shell editor-shell--answer">
            {isLoading ? (
              <div className="answer-state answer-state--loading">
                <div className="answer-loader" />
                <div>
                  <strong>Agent 正在整理回答</strong>
                  <p>这一步会由本地 Agent workflow 调用 `/api/v1/chat/ask`，再整理最终 answer / citations。</p>
                </div>
              </div>
            ) : result.errorMessage ? (
              <div className="answer-state answer-state--error">
                <WarningCircle size={22} weight="fill" />
                <div>
                  <strong>调用失败</strong>
                  <p>{result.errorMessage}</p>
                </div>
              </div>
            ) : result.answer ? (
              <article className="answer-markdown">
                {result.answer.split(/\n{2,}/).map((paragraph, index) => (
                  <p key={`${index}-${paragraph.slice(0, 18)}`}>{paragraph}</p>
                ))}
              </article>
            ) : (
              <div className="answer-state">
                <MagnifyingGlass size={22} />
                <div>
                  <strong>还没有回答结果</strong>
                  <p>先输入一个问题，然后点击“让 Agent 回答”。</p>
                </div>
              </div>
            )}
          </div>

          {result.answer ? (
            <div className="answer-actions">
              <div className="answer-actions__meta">
                <strong>发送到 Boss</strong>
                <span>
                  {result.draftId
                    ? "这一步会复用 `boss agent send`，由后端通过 CDP 真实发送。"
                    : "当前回答还没有可发送的 draft_id。"}
                </span>
              </div>
              <div className="answer-actions__controls">
                <label className="send-toggle">
                  <input
                    type="checkbox"
                    checked={sendResumeWithDraft}
                    onChange={(event) => setSendResumeWithDraft(event.target.checked)}
                  />
                  <span>同时发送在线简历</span>
                </label>
                <button
                  type="button"
                  className="inline-action inline-action--primary"
                  onClick={handleSendToBoss}
                  disabled={
                    isSendingToBoss ||
                    !result.draftId
                  }
                >
                  <PaperPlaneTilt size={16} weight="fill" />
                  {isSendingToBoss ? "发送中..." : "发送到 Boss"}
                </button>
              </div>
            </div>
          ) : null}
        </section>

{/* ── BOSS 直聘全自动投递 ──────────────────────────────── */}
      <section className="apply-panel apply-panel--inline">
        <div className="apply-panel__header" onClick={() => setApplyMode((m) => !m)}>
          <div className="apply-panel__title-row">
            <PaperPlaneTilt size={22} weight="bold" />
            <h2>BOSS 直聘 · 全自动投递</h2>
          </div>
          <span className="apply-panel__toggle">{applyMode ? "收起 ▲" : "展开 ▼"}</span>
        </div>

        {applyMode && (
          <div className="apply-panel__body">
            {/* 搜索职位 */}
            <div className="apply-search">
              <div className="apply-search__inputs">
                <input
                  className="apply-input"
                  placeholder="搜索职位关键词，如：AI大模型 RAG"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                />
                <input
                  className="apply-input apply-input--city"
                  placeholder="城市"
                  value={searchCity}
                  onChange={(e) => setSearchCity(e.target.value)}
                />
                <button
                  className="apply-btn apply-btn--search"
                  onClick={handleSearch}
                  disabled={searchLoading || !searchQuery.trim()}
                >
                  {searchLoading ? "搜索中..." : "搜职位"}
                </button>
              </div>
              {searchResults.length > 0 && (
                <div className="apply-job-list">
                  {searchResults.slice(0, 8).map((job, i) => (
                    <button
                      key={job.security_id || i}
                      className="apply-job-item"
                      onClick={() => pickJob(job)}
                    >
                      <div className="apply-job-item__main">
                        <strong>{job.title || job.job_name || "未知职位"}</strong>
                        <span>{job.company || job.brand_name || "未知公司"}</span>
                      </div>
                      <span className="apply-job-item__meta">
                        {job.city || ""} {job.salary || ""}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* 投递表单 */}
            <div className="apply-form">
              <div className="apply-form__row">
                <div className="apply-field">
                  <label>Security ID</label>
                  <input
                    className="apply-input"
                    placeholder="security_id"
                    value={applyForm.security_id}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, security_id: e.target.value }))
                    }
                  />
                </div>
                <div className="apply-field">
                  <label>Job ID</label>
                  <input
                    className="apply-input"
                    placeholder="job_id"
                    value={applyForm.job_id}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, job_id: e.target.value }))
                    }
                  />
                </div>
              </div>
              <div className="apply-form__row">
                <div className="apply-field">
                  <label>职位名称</label>
                  <input
                    className="apply-input"
                    placeholder="如：AI大模型应用开发"
                    value={applyForm.title}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, title: e.target.value }))
                    }
                  />
                </div>
                <div className="apply-field">
                  <label>公司名称</label>
                  <input
                    className="apply-input"
                    placeholder="如：迪原创新"
                    value={applyForm.company}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, company: e.target.value }))
                    }
                  />
                </div>
              </div>
              <div className="apply-form__row">
                <div className="apply-field">
                  <label>简历名称</label>
                  <input
                    className="apply-input"
                    placeholder="default"
                    value={applyForm.resume_name}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, resume_name: e.target.value }))
                    }
                  />
                </div>
                <div className="apply-field">
                  <label>自定义消息（可选）</label>
                  <input
                    className="apply-input"
                    placeholder="留空自动生成打招呼文案"
                    value={applyForm.message}
                    onChange={(e) =>
                      setApplyForm((f) => ({ ...f, message: e.target.value }))
                    }
                  />
                </div>
              </div>

              <button
                className="apply-btn apply-btn--send"
                onClick={handleApply}
                disabled={
                  applyLoading ||
                  !applyForm.security_id.trim() ||
                  !applyForm.job_id.trim()
                }
              >
                <PaperPlaneTilt size={18} weight="fill" />
                {applyLoading ? "投递中..." : "全自动发简历"}
              </button>

              {applyResult && (
                <div
                  className={`apply-result ${
                    applyResult.ok ? "apply-result--ok" : "apply-result--error"
                  }`}
                >
                  {applyResult.ok ? (
                    <>
                      <CheckCircle size={18} weight="fill" />
                      <span>投递成功！{applyResult.data?.message || ""}</span>
                    </>
                  ) : (
                    <>
                      <WarningCircle size={18} weight="fill" />
                      <span>
                        投递失败：{applyResult.errorMessage || applyResult.error?.message || "未知错误"}
                      </span>
                    </>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      </section>

      <aside className="evidence-pane">
        <section className="evidence-card">
          <div className="card-title-row">
            <h3>引用证据</h3>
            <span>{result.citations.length} 条</span>
          </div>
          <div className="source-list">
            {result.citations.length ? (
              result.citations.map((citation, index) => (
                <button
                  key={`${titleFromCitation(citation, index)}-${index}`}
                  type="button"
                  className={`source-item ${selectedCitationIndex === index ? "is-selected" : ""}`}
                  onClick={() => setSelectedCitationIndex(index)}
                >
                  <div className="source-item__icon">
                    <FileText size={18} />
                  </div>
                  <div className="source-item__body">
                    <strong>{titleFromCitation(citation, index)}</strong>
                    <span className="source-badge source-badge--verified">
                      引用 {index + 1}
                    </span>
                    <em>{detailFromCitation(citation) || "可展开查看片段"}</em>
                  </div>
                </button>
              ))
            ) : (
              <div className="empty-card-copy">
                当前回答还没有可展示的 citations。若底层 RAG 命中证据，这里会展示引用列表。
              </div>
            )}
          </div>

          {selectedCitation ? (
            <div className="source-summary">
              <div className="source-summary__header">
                <Quotes size={16} />
                <span>{titleFromCitation(selectedCitation, selectedCitationIndex)}</span>
              </div>
              <p>{excerptFromCitation(selectedCitation)}</p>
            </div>
          ) : null}
        </section>

        <section className="outline-card">
          <div className="card-title-row">
            <h3>Agent 执行信息</h3>
          </div>
          <ol className="agent-meta-list">
            <li>
              <span className="outline-index">1</span>
              <span>输入问题写入当前 thread</span>
            </li>
            <li className={bridgeState.ready ? "is-current" : ""}>
              <span className="outline-index">2</span>
              <span>转发到 `POST /api/v1/chat/ask`</span>
            </li>
            <li className={result.ok ? "is-current" : ""}>
              <span className="outline-index">3</span>
              <span>返回 answer / citations / reasoning，并同步多轮 memory</span>
            </li>
            {result.draftId ? (
              <li className={result.delivery?.status === "sent" ? "is-current" : ""}>
                <span className="outline-index">4</span>
                <span>
                  {result.delivery?.status === "sent"
                    ? result.delivery?.resume_sent
                      ? "已调用 Boss 对话真实发送消息，并附带在线简历"
                      : "已调用 Boss 对话真实发送 Agent 草稿"
                    : "草稿已生成，可继续调用 `/api/agent/send` 真实发送"}
                </span>
              </li>
            ) : null}
          </ol>

          <div className="reasoning-panel">
            <h4>reasoning_summary</h4>
            {reasoningItems.length ? (
              <ul>
                {reasoningItems.map((item) => (
                  <li key={item.key}>
                    <strong>{item.key}</strong>
                    <span>{item.value}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p>当前响应未返回结构化 reasoning_summary，或尚未发起请求。</p>
            )}
          </div>

          {!bridgeState.ready && bridgeState.errorMessage ? (
            <div className="bridge-warning">
              <WarningCircle size={18} weight="fill" />
              <p>{bridgeState.errorMessage}</p>
            </div>
          ) : null}
        </section>
      </aside>

      <footer className="action-bar">
        <button type="button" className="action-btn action-btn--ghost" onClick={() => setQuestion(starterPrompts[0])}>
          <Sparkle size={20} />
          <span>
            载入示例
            <em>回到推荐问题</em>
          </span>
        </button>

        <button type="button" className="action-btn action-btn--ghost" onClick={() => setQuestion("请基于企业级 RAG 面试参考文档，总结我最可信的候选人画像。")}>
          <Quotes size={20} />
          <span>
            候选人画像
            <em>快速验证 Agent 回答风格</em>
          </span>
        </button>

        <button type="button" className="action-btn action-btn--primary" onClick={handleAsk} disabled={isLoading || !question.trim()}>
          <ArrowRight size={20} />
          <span>
            立即提问
            <em>通过 Agent 调用 RAG</em>
          </span>
        </button>

        <div className="countdown-card">
          <span>{bridgeState.ready ? "代理已就绪" : "等待代理可用"}</span>
          <strong>
            {result.ok
              ? `${result.citations.length} 条引用`
              : bridgeState.loading
                ? "检查中"
                : bridgeState.configured
                  ? "可发起请求"
                  : "缺少配置"}
          </strong>
        </div>
      </footer>

      </main>
  );
}
