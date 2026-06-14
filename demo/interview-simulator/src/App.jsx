import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  Lightning,
  MagnifyingGlass,
  PlayCircle,
  Quotes,
  Sparkle,
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
    endpoint: "/api/rag/ask",
    errorMessage: "",
  });
  const [sessionId] = useState(() => loadOrCreateSessionId());

  const reasoningItems = useMemo(
    () => normalizeReasoningSummary(result.reasoningSummary),
    [result.reasoningSummary],
  );
  const selectedCitation = result.citations[selectedCitationIndex] ?? null;
  const questionLength = question.replace(/\s/g, "").length;

  useEffect(() => {
    let cancelled = false;
    async function loadBridgeState() {
      try {
        const [response, threadResponse] = await Promise.all([
          fetch("/api/rag/health"),
          fetch(`/api/rag/thread?sessionId=${encodeURIComponent(sessionId)}`),
        ]);
        const data = await response.json();
        const threadPayload = await threadResponse.json();
        if (!cancelled) {
          setBridgeState({
            loading: false,
            configured: Boolean(data.configured),
            ready: Boolean(data.ready),
            authMode: String(data.authMode || "unknown"),
            endpoint: String(data.endpoint || "/api/rag/ask"),
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
            endpoint: "/api/rag/ask",
            errorMessage: error instanceof Error ? error.message : "无法读取本地代理状态。",
          });
        }
      }
    }
    loadBridgeState();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

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
      const response = await fetch("/api/rag/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: trimmed,
          sessionId,
          mode: "accurate",
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        if (payload.thread?.messages) {
          setThread(payload.thread.messages);
        }
        throw new Error(payload.errorMessage || "RAG 请求失败，请检查本地服务状态。");
      }

      const nextResult = {
        ok: true,
        answer: String(payload.answer || ""),
        citations: Array.isArray(payload.citations) ? payload.citations : [],
        reasoningSummary:
          payload.reasoningSummary && typeof payload.reasoningSummary === "object"
            ? payload.reasoningSummary
            : null,
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
      const message = error instanceof Error ? error.message : "RAG 请求失败。";
      setResult({
        ...emptyAnswer,
        auditStatus: "rag_failed",
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

  return (
    <main className="app-shell app-shell--rag">
      <aside className="session-pane">
        <div className="brand-block">
          <div className="brand-mark">
            <Sparkle size={20} weight="bold" />
          </div>
          <div>
            <h1>AI 面试问答台</h1>
            <p>Agent 代调用 Enterprise RAG</p>
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
          <h2>本地 RAG 代理</h2>
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
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">RAG 问题输入</span>
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
              <h3>RAG 回答结果</h3>
              <p>
                <span className={`answer-region__verified-dot ${result.ok ? "is-success" : ""}`} />
                {result.ok
                  ? `已收到 grounded answer${result.latencyMs ? ` · ${result.latencyMs}ms` : ""}`
                  : isLoading
                    ? "正在等待 Enterprise RAG 返回"
                    : "等待你发起问题"}
              </p>
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
                  <p>这一步会由本地代理向 `/api/v1/chat/ask` 发起请求，并回收 answer / citations。</p>
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
                当前回答还没有可展示的 citations。真实 RAG 返回后，会在这里展示证据列表。
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
            <em>快速验证 RAG 风格</em>
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
