import { useEffect, useMemo, useState } from "react";
import {
  ArrowClockwise,
  ArrowRight,
  CheckCircle,
  Clock,
  FileText,
  Lightning,
  MagnifyingGlass,
  PauseCircle,
  PaperPlaneTilt,
  PlayCircle,
  Quotes,
  Sparkle,
  User,
  WarningCircle,
} from "@phosphor-icons/react";
import {
  bossAccountRiskCode,
  bossBridgeErrorCode,
  bossBridgeErrorFromPayload,
  bossBridgeErrorMessage,
  isBossAccountRiskMessage,
} from "./bossBridgeErrors.js";
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
const defaultBrowserChannel = {
  available: false,
  transportAvailable: false,
  chatPageReachable: false,
  mode: "none",
  cdpAvailable: false,
  bridgeAvailable: false,
  cdpUrl: "http://localhost:9229",
  bridgeUrl: "http://127.0.0.1:19826",
  chatPageUrl: "https://www.zhipin.com/web/geek/chat",
  preflightStatus: "none",
  lastObservedUrl: "",
  lastObservedTitle: "",
  redirectUrl: "",
  errorMessage: "",
};

const bossCityOptions = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "南京", "苏州"];
const bossSalaryOptions = ["", "3-5K", "3K以下", "5-7K", "7-9K", "9-12K", "10-15K", "11-22K", "12-24K", "13-26K"];
const bossExperienceOptions = ["", "应届", "1年以内", "1-3年", "3-5年", "5-10年", "10年以上"];
const bossEducationOptions = ["", "大专", "本科", "硕士", "博士"];
const bossIndustryOptions = ["", "人工智能", "互联网", "软件/信息服务", "大数据", "云计算", "电子商务", "游戏", "金融", "教育培训", "医疗健康", "制造业"];
const bossScaleOptions = ["", "0-20人", "20-99人", "100-499人", "500-999人", "1000-9999人", "10000人以上"];
const bossStageOptions = ["", "未融资", "天使轮", "A轮", "B轮", "C轮", "D轮及以上", "已上市", "不需要融资"];
const bossJobTypeOptions = ["", "全职", "兼职", "实习"];
const defaultBossSearchForm = {
  query: "RAG",
  city: "杭州",
  salary: "12-24K",
  experience: "1年以内",
  education: "本科",
  industry: "",
  scale: "",
  stage: "",
  jobType: "全职",
  welfare: "",
  count: "10",
};

function splitBossExperienceValue(value) {
  return String(value || "")
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

function formatBossExperienceSummary(value) {
  const selected = splitBossExperienceValue(value);
  if (!selected.length) return "经验不限";
  if (selected.length <= 2) return selected.join("、");
  return `${selected[0]} +${selected.length - 1}`;
}

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

function targetOptionValue(target) {
  return String(target.conversation_id || target.security_id || "");
}

function normalizeBossJob(item) {
  return {
    security_id: String(item?.security_id || item?.securityId || ""),
    job_id: String(item?.job_id || item?.jobId || item?.encryptJobId || ""),
    title: String(item?.title || item?.jobName || "未知职位"),
    company: String(item?.company || item?.brandName || "未知公司"),
    salary: String(item?.salary || item?.salaryDesc || ""),
    city: String(item?.city || item?.cityName || ""),
    experience: String(item?.experience || item?.jobExperience || ""),
  };
}

function watcherRiskHint(watcherState) {
  const directMessage = String(watcherState?.errorMessage || "").trim();
  if (directMessage && isBossAccountRiskMessage(directMessage)) {
    return directMessage;
  }

  const tasks = Array.isArray(watcherState?.tasks) ? watcherState.tasks.slice().reverse() : [];
  const riskyTask = tasks.find((task) => {
    const detail = String(task?.error_message || task?.action?.message || "").trim();
    return Boolean(detail) && isBossAccountRiskMessage(detail);
  });
  if (!riskyTask) return "";
  return String(riskyTask.error_message || riskyTask.action?.message || "").trim();
}

function resolveSecurityId({ manualSecurityId = "", selectedChatTarget = null, chatTargets = [] }) {
  const direct = String(manualSecurityId).trim();
  if (direct) return direct;
  if (selectedChatTarget?.security_id) return String(selectedChatTarget.security_id).trim();
  const fallbackTarget = Array.isArray(chatTargets) ? chatTargets.find((item) => item?.security_id) : null;
  return fallbackTarget?.security_id ? String(fallbackTarget.security_id).trim() : "";
}

function resolveTargetIdentity({ selectedChatTarget = null, chatTargets = [], securityId = "" }) {
  const normalizedSecurityId = String(securityId || "").trim();
  const target =
    selectedChatTarget ||
    (normalizedSecurityId
      ? chatTargets.find(
          (item) => String(item?.security_id || "").trim() === normalizedSecurityId,
        )
      : null);
  if (!target) return null;

  const identity = {
    recruiter_name: String(target.recruiter_name || target.name || "").trim(),
    company: String(target.company || target.brand_name || "").trim(),
    title: String(target.title || target.job_title || "").trim(),
  };
  return Object.values(identity).some(Boolean) ? identity : null;
}

function shouldSendResumeByDefault({ question = "", draftIntent = "", securityId = "" }) {
  const normalizedQuestion = String(question).toLowerCase();
  const normalizedIntent = String(draftIntent);
  const hasSecurityId = Boolean(String(securityId).trim());
  if (!hasSecurityId) return false;
  if (normalizedIntent === "resume_share_request") return true;
  return ["简历", "resume", "cv"].some((keyword) =>
    normalizedQuestion.includes(keyword),
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

function normalizeBridgeStatePayload(data, fallbackErrorMessage = "") {
  const browserChannel =
    data?.browserChannel && typeof data.browserChannel === "object"
      ? {
          ...defaultBrowserChannel,
          ...data.browserChannel,
        }
      : defaultBrowserChannel;

  return {
    loading: false,
    configured: Boolean(data?.configured),
    ready: Boolean(data?.ready),
    authMode: String(data?.authMode || "unknown"),
    endpoint: String(data?.endpoint || "/api/agent/ask"),
    errorMessage: data?.errorMessage
      ? String(data.errorMessage)
      : fallbackErrorMessage,
    browserChannel,
  };
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
    browserChannel: defaultBrowserChannel,
  });
  const [sessionId] = useState(() => loadOrCreateSessionId());

  const [applyMode, setApplyMode] = useState(false);
  const [applyForm, setApplyForm] = useState({
    security_id: "",
  });
  const [bossSearchForm, setBossSearchForm] = useState(defaultBossSearchForm);
  const [bossSearchJobs, setBossSearchJobs] = useState([]);
  const [bossAutomationResult, setBossAutomationResult] = useState(null);
  const [bossAutomationError, setBossAutomationError] = useState("");
  const [bossAutomationProgress, setBossAutomationProgress] = useState(null);
  const [bossAutomationRiskLocked, setBossAutomationRiskLocked] = useState(false);
  const [isBossSearching, setIsBossSearching] = useState(false);
  const [isBossAutoRunning, setIsBossAutoRunning] = useState(false);
  const [chatTargets, setChatTargets] = useState([]);
  const [chatTargetsLoading, setChatTargetsLoading] = useState(false);
  const [chatTargetsError, setChatTargetsError] = useState("");
  const [chatTargetsMeta, setChatTargetsMeta] = useState({
    source: "cache",
    liveReadEnabled: false,
    refreshed: false,
  });
  const [selectedTargetValue, setSelectedTargetValue] = useState("");
  const [isSendingToBoss, setIsSendingToBoss] = useState(false);
  const [sendResumeWithDraft, setSendResumeWithDraft] = useState(false);
  const [watcherState, setWatcherState] = useState({
    running: false,
    dry_run: true,
    tasks: [],
    errorMessage: "",
  });
  const [isWatcherBusy, setIsWatcherBusy] = useState(false);

  const reasoningItems = useMemo(
    () => normalizeReasoningSummary(result.reasoningSummary),
    [result.reasoningSummary],
  );
  const selectedChatTarget = useMemo(
    () =>
      chatTargets.find((target) => targetOptionValue(target) === selectedTargetValue) ||
      null,
    [chatTargets, selectedTargetValue],
  );
  const selectedCitation = result.citations[selectedCitationIndex] ?? null;
  const questionLength = question.replace(/\s/g, "").length;
  const recentWatcherTasks = useMemo(
    () => watcherState.tasks.slice().reverse().slice(0, 6),
    [watcherState.tasks],
  );
  const watcherRiskStatusMessage = useMemo(
    () => watcherRiskHint(watcherState),
    [watcherState],
  );
  const normalizedBossJobs = useMemo(
    () => bossSearchJobs.map(normalizeBossJob),
    [bossSearchJobs],
  );
  const selectedBossExperiences = splitBossExperienceValue(bossSearchForm.experience);
  const bossExperienceSummary = formatBossExperienceSummary(bossSearchForm.experience);
  const bossAutomationFailedItems = Array.isArray(bossAutomationResult?.failed)
    ? bossAutomationResult.failed
    : [];
  const bossAutomationHasIssue =
    Boolean(bossAutomationResult?.stopped_reason) ||
    Number(bossAutomationResult?.total_failed || 0) > 0;
  const bossAutomationProgressCurrent = Number(bossAutomationProgress?.current || 0);
  const bossAutomationProgressTotal = Number(
    bossAutomationProgress?.total || bossSearchForm.count || 0,
  );
  const bossAutomationIsGreeting =
    bossAutomationProgress?.phase === "greeting" && bossAutomationProgressCurrent > 0;
  const bossAutoButtonLabel = isBossAutoRunning
    ? bossAutomationIsGreeting
      ? `第${bossAutomationProgressCurrent}${bossAutomationProgressTotal ? `/${bossAutomationProgressTotal}` : ""}个`
      : "搜索中..."
    : "Agent 全自动";
  const bossSearchActionsDisabled = bossAutomationRiskLocked || !bossSearchForm.query.trim();

  function updateBossSearchForm(field, value) {
    setBossSearchForm((current) => ({
      ...current,
      [field]: value,
    }));
  }

  function toggleBossExperience(value) {
    setBossSearchForm((current) => {
      if (!value) {
        return {
          ...current,
          experience: "",
        };
      }
      const selected = splitBossExperienceValue(current.experience);
      const next = selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value];
      return {
        ...current,
        experience: next.join(","),
      };
    });
  }

  async function loadChatTargets() {
    setChatTargetsLoading(true);
    setChatTargetsError("");
    try {
      const response = await fetch("/api/agent/targets?limit=5");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "读取 Boss 对话目标失败。");
      }
      const nextTargets = Array.isArray(payload.targets) ? payload.targets : [];
      setChatTargets(nextTargets);
      setChatTargetsMeta({
        source: String(payload.source || "cache"),
        liveReadEnabled: Boolean(payload.liveReadEnabled),
        refreshed: Boolean(payload.refreshed),
      });
      setChatTargetsError(payload.refreshError ? String(payload.refreshError) : "");
      if (!selectedTargetValue && !applyForm.security_id.trim() && nextTargets.length) {
        pickTarget(nextTargets[0]);
      }
    } catch (error) {
      setChatTargets([]);
      setChatTargetsError(error instanceof Error ? error.message : "读取 Boss 对话目标失败。");
    } finally {
      setChatTargetsLoading(false);
    }
  }

  async function refreshWatcherStatus() {
    try {
      const response = await fetch("/api/agent/watcher/status");
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "读取 watcher 状态失败。");
      }
      setWatcherState({
        running: Boolean(payload.data?.running),
        dry_run: Boolean(payload.data?.dry_run),
        tasks: Array.isArray(payload.data?.tasks) ? payload.data.tasks : [],
        errorMessage: "",
      });
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage:
          error instanceof Error ? error.message : "读取 watcher 状态失败。",
      }));
    }
  }

  async function runWatcherOnce() {
    setIsWatcherBusy(true);
    try {
      const response = await fetch("/api/agent/watcher/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ liveSync: true, ensureChatPage: true }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "运行 watcher 失败。");
      }
      const runData = payload.data || {};
      await refreshWatcherStatus();
      if (Array.isArray(runData.tasks) && runData.tasks.length) {
        setWatcherState((current) => ({
          ...current,
          tasks: runData.tasks,
        }));
      }
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage: error instanceof Error ? error.message : "运行 watcher 失败。",
      }));
    } finally {
      setIsWatcherBusy(false);
    }
  }

  useEffect(() => {
    if (!watcherState.running || isWatcherBusy) return undefined;
    const timer = window.setInterval(() => {
      runWatcherOnce();
    }, 20_000);
    return () => window.clearInterval(timer);
  }, [watcherState.running, isWatcherBusy]);

  async function controlWatcher(action, conversationId = "") {
    setIsWatcherBusy(true);
    try {
      const response = await fetch("/api/agent/watcher/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, conversation_id: conversationId }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw new Error(payload.errorMessage || "更新 watcher 控制状态失败。");
      }
      await refreshWatcherStatus();
    } catch (error) {
      setWatcherState((current) => ({
        ...current,
        errorMessage:
          error instanceof Error ? error.message : "更新 watcher 控制状态失败。",
      }));
    } finally {
      setIsWatcherBusy(false);
    }
  }

  async function handleBossSearchPreview() {
    const query = bossSearchForm.query.trim();
    if (!query || isBossSearching || bossAutomationRiskLocked) return;
    setIsBossSearching(true);
    setBossAutomationError("");
    setBossAutomationResult(null);
    setBossAutomationProgress(null);
    try {
      const response = await fetch("/api/boss/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          city: bossSearchForm.city,
          salary: bossSearchForm.salary,
          experience: bossSearchForm.experience,
          education: bossSearchForm.education,
          industry: bossSearchForm.industry,
          scale: bossSearchForm.scale,
          stage: bossSearchForm.stage,
          jobType: bossSearchForm.jobType,
          welfare: bossSearchForm.welfare,
        }),
      });
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw bossBridgeErrorFromPayload(payload, "BOSS 搜索失败。");
      }
      const jobs = Array.isArray(payload.data) ? payload.data : [];
      setBossSearchJobs(jobs);
      if (!jobs.length) {
        setBossAutomationError("预览没有找到职位，请放宽筛选条件后再开聊。");
      }
    } catch (error) {
      setBossSearchJobs([]);
      const errorCode = bossBridgeErrorCode(error);
      const watcherRiskOverride =
        watcherRiskStatusMessage && (errorCode === "NETWORK_ERROR" || !errorCode)
          ? `Boss 账号当前已被平台限制访问。${watcherRiskStatusMessage} 请回到 BOSS 官方页面手动处理或等待恢复后刷新重试。`
          : "";
      if (errorCode === bossAccountRiskCode || watcherRiskOverride) {
        setBossAutomationRiskLocked(true);
      }
      setBossAutomationError(
        watcherRiskOverride || bossBridgeErrorMessage(error, "BOSS 搜索失败。"),
      );
    } finally {
      setIsBossSearching(false);
    }
  }

  async function handleBossAutoGreet() {
    const query = bossSearchForm.query.trim();
    if (!query || isBossAutoRunning || bossAutomationRiskLocked) return;
    setIsBossAutoRunning(true);
    setBossAutomationError("");
    setBossAutomationResult(null);
    setBossAutomationProgress({
      phase: "searching",
      current: 0,
      total: Number.parseInt(String(bossSearchForm.count || "0"), 10) || 0,
      message: "正在搜索可开聊候选，还没有开始聊天。",
    });
    try {
      const response = await fetch("/api/boss/auto-greet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query,
          city: bossSearchForm.city,
          salary: bossSearchForm.salary,
          experience: bossSearchForm.experience,
          education: bossSearchForm.education,
          industry: bossSearchForm.industry,
          scale: bossSearchForm.scale,
          stage: bossSearchForm.stage,
          jobType: bossSearchForm.jobType,
          welfare: bossSearchForm.welfare,
          count: bossSearchForm.count,
          stream: true,
        }),
      });
      const contentType = response.headers.get("Content-Type") || "";
      if (response.body && contentType.includes("application/x-ndjson")) {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let finalPayload = null;
        let streamError = null;
        const consumeLine = (line) => {
          const trimmed = line.trim();
          if (!trimmed) return;
          const event = JSON.parse(trimmed);
          if (event.type === "status") {
            setBossAutomationProgress((current) => ({
              ...current,
              phase: event.status || "searching",
              message: event.message || "正在搜索可开聊候选，还没有开始聊天。",
            }));
          } else if (event.type === "progress") {
            const data = event.data || {};
            setBossAutomationProgress({
              phase: "greeting",
              current: Number(data.current || 0),
              total: Number(data.total || 0),
              title: String(data.title || ""),
              company: String(data.company || ""),
              message: "正在开聊候选。",
            });
          } else if (event.type === "result") {
            finalPayload = event;
          } else if (event.type === "error") {
            streamError = event;
          }
        };

        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split(/\r?\n/);
          buffer = lines.pop() || "";
          lines.forEach(consumeLine);
        }
        buffer += decoder.decode();
        if (buffer.trim()) consumeLine(buffer);
        if (streamError) {
          throw bossBridgeErrorFromPayload(streamError, "Agent 自动开聊失败。");
        }
        if (!finalPayload?.ok) {
          throw new Error("Agent 自动开聊没有返回结果。");
        }
        setBossAutomationResult(finalPayload.data || {});
        setBossAutomationProgress(null);
        await loadChatTargets();
        return;
      }
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        throw bossBridgeErrorFromPayload(payload, "Agent 自动开聊失败。");
      }
      setBossAutomationResult(payload.data || {});
      setBossAutomationProgress(null);
      await loadChatTargets();
    } catch (error) {
      setBossAutomationProgress(null);
      const errorCode = bossBridgeErrorCode(error);
      const watcherRiskOverride =
        watcherRiskStatusMessage && (errorCode === "NETWORK_ERROR" || !errorCode)
          ? `Boss 账号当前已被平台限制访问。${watcherRiskStatusMessage} 请回到 BOSS 官方页面手动处理或等待恢复后刷新重试。`
          : "";
      if (errorCode === bossAccountRiskCode || watcherRiskOverride) {
        setBossAutomationRiskLocked(true);
      }
      setBossAutomationError(
        watcherRiskOverride || bossBridgeErrorMessage(error, "Agent 自动开聊失败。"),
      );
    } finally {
      setIsBossAutoRunning(false);
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
          setBridgeState(normalizeBridgeStatePayload(data));
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
          setBridgeState(
            normalizeBridgeStatePayload(
              null,
              error instanceof Error ? error.message : "无法读取本地代理状态。",
            ),
          );
        }
      }
    }
    loadBridgeState();
    loadChatTargets();
    void refreshWatcherStatus();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  function pickTarget(target) {
    setApplyForm({
      security_id: target.security_id || "",
    });
    setSelectedTargetValue(targetOptionValue(target));
    setApplyMode(true);
  }

  function handleTargetSelection(value) {
    setSelectedTargetValue(value);
    if (!value) {
      setApplyForm({ security_id: "" });
      return;
    }
    const target = chatTargets.find((item) => targetOptionValue(item) === value);
    if (target) {
      pickTarget(target);
    }
  }

  async function handleAsk() {
    const trimmed = question.trim();
    if (!trimmed || isLoading) return;
    const resolvedSecurityId = resolveSecurityId({
      manualSecurityId: applyForm.security_id,
      selectedChatTarget,
      chatTargets,
    });
    const targetIdentity = resolveTargetIdentity({
      selectedChatTarget,
      chatTargets,
      securityId: resolvedSecurityId,
    });

    if (resolvedSecurityId && resolvedSecurityId !== applyForm.security_id.trim()) {
      setApplyForm({ security_id: resolvedSecurityId });
    }

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
          security_id: resolvedSecurityId,
          auto_send_resume: false,
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
      const shouldAutoSendResume = shouldSendResumeByDefault({
        question: trimmed,
        draftIntent: payload.draftIntent,
        securityId: resolvedSecurityId,
      });
      const resumeRequested = String(payload.draftIntent || "") === "resume_share_request";
      if (resumeRequested && !resolvedSecurityId) {
        nextResult.delivery = {
          status: "missing_security_id",
          message_sent: false,
          resume_sent: false,
          send_resume: true,
          send_attachment_resume: true,
          error_message: "已识别为发简历请求，但当前没有可用的 Boss security_id。",
        };
      }

      setResult(nextResult);
      setSendResumeWithDraft(shouldAutoSendResume);
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
      if (shouldAutoSendResume && nextResult.draftId) {
        void sendDraftToBoss({
          draftId: nextResult.draftId,
          securityId: resolvedSecurityId,
          sendAttachmentResume: true,
          targetIdentity,
        });
      }
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

  async function sendDraftToBoss({ draftId, securityId, sendAttachmentResume, targetIdentity = null }) {
    if (!draftId || isSendingToBoss) return;
    if (securityId && securityId !== applyForm.security_id.trim()) {
      setApplyForm({ security_id: securityId });
    }

    let latestBridgeState = bridgeState;
    try {
      const healthResponse = await fetch("/api/agent/health");
      const healthPayload = await healthResponse.json();
      latestBridgeState = normalizeBridgeStatePayload(healthPayload);
      setBridgeState(latestBridgeState);
    } catch (error) {
      latestBridgeState = normalizeBridgeStatePayload(
        null,
        error instanceof Error ? error.message : "无法检查浏览器发送通道状态。",
      );
      setBridgeState(latestBridgeState);
    }

    if (!latestBridgeState.browserChannel.available) {
      setResult((current) => ({
        ...current,
        delivery: {
          status: "browser_channel_unavailable",
          message_sent: false,
          resume_sent: false,
          error_message:
            latestBridgeState.browserChannel.errorMessage ||
            latestBridgeState.errorMessage ||
            "未检测到可用的浏览器发送通道。",
        },
      }));
      return;
    }

    setIsSendingToBoss(true);
    setResult((current) => ({
      ...current,
      delivery: {
        status: "sending",
        message_sent: false,
        resume_sent: false,
        send_attachment_resume: sendAttachmentResume,
        security_id: securityId,
        target: targetIdentity,
      },
    }));
    try {
      const response = await fetch("/api/agent/send", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          draftId,
          sessionId,
          security_id: securityId,
          send_resume: false,
          send_attachment_resume: sendAttachmentResume,
          target: targetIdentity,
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

  async function handleSendToBoss() {
    if (!result.draftId || isSendingToBoss) return;
    const resolvedSecurityId = resolveSecurityId({
      manualSecurityId: applyForm.security_id,
      selectedChatTarget,
      chatTargets,
    });
    const targetIdentity = resolveTargetIdentity({
      selectedChatTarget,
      chatTargets,
      securityId: resolvedSecurityId,
    });
    await sendDraftToBoss({
      draftId: result.draftId,
      securityId: resolvedSecurityId,
      sendAttachmentResume: sendResumeWithDraft,
      targetIdentity,
    });
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
          <p>
            Boss 发送预检：
            {bridgeState.browserChannel.available
              ? bridgeState.browserChannel.chatPageReachable
                ? " 聊天页可达"
                : " 通道可用"
              : bridgeState.browserChannel.errorMessage
                ? " 未就绪"
                : " 未检查"}
          </p>
        </section>

        <section className="session-card watcher-console">
          <div className="session-card__header">
            <span>Watcher Console</span>
            <span
              className={`live-dot ${watcherState.running ? "is-success" : "is-muted"}`}
            >
              <span className="live-dot__point" />
              {watcherState.running ? "enabled" : "paused"}
            </span>
          </div>
          <div className="watcher-console__summary">
            <strong>{watcherState.dry_run ? "dry-run" : "live-send"}</strong>
            <span>{watcherState.tasks.length} recent tasks</span>
          </div>
          <div className="watcher-console__actions">
            <button
              type="button"
              className="watcher-console__button"
              onClick={refreshWatcherStatus}
              disabled={isWatcherBusy}
            >
              <ArrowClockwise size={15} />
              刷新
            </button>
            <button
              type="button"
              className="watcher-console__button"
              onClick={runWatcherOnce}
              disabled={isWatcherBusy}
            >
              <Lightning size={15} />
              单轮
            </button>
            <button
              type="button"
              className="watcher-console__button"
              onClick={() => controlWatcher("pause")}
              disabled={isWatcherBusy}
            >
              <PauseCircle size={15} />
              暂停
            </button>
            <button
              type="button"
              className="watcher-console__button"
              onClick={() => controlWatcher("resume")}
              disabled={isWatcherBusy}
            >
              <PlayCircle size={15} />
              恢复
            </button>
          </div>
          {watcherState.errorMessage ? (
            <div className="watcher-console__error">
              <WarningCircle size={16} />
              <span>{watcherState.errorMessage}</span>
            </div>
          ) : null}
          <ul className="watcher-task-list">
            {recentWatcherTasks.length ? (
              recentWatcherTasks.map((task, index) => {
                const conversationId = String(task.conversation_id || "").trim();
                const messageId = String(task.message_id || "").trim();
                const detail =
                  task.error_message ||
                  task.action?.message ||
                  "未返回执行说明。";
                return (
                  <li key={`${task.log_id || conversationId || messageId || index}`}>
                    <div className="watcher-task">
                      <div className="watcher-task__main">
                        <strong>
                          {task.intent || "unknown_intent"} / {task.status || "unknown_status"}
                        </strong>
                        <span>{detail}</span>
                        <em>
                          {conversationId || "no conversation"}
                          {messageId ? ` · ${messageId}` : ""}
                        </em>
                      </div>
                      {conversationId ? (
                        <button
                          type="button"
                          className="watcher-task__pause"
                          onClick={() => controlWatcher("pause", conversationId)}
                          disabled={isWatcherBusy}
                          title="暂停此对话"
                        >
                          <PauseCircle size={14} />
                        </button>
                      ) : null}
                    </div>
                  </li>
                );
              })
            ) : (
              <li className="history-list__empty">暂无 watcher task。</li>
            )}
          </ul>
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
              thread.map((item, index) => (
                <li key={`${item.id || item.content || item.role}-${index}`}>
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
              history.map((item, index) => (
                <li key={`${item.id || item.question || item.status}-${index}`}>
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
              chatTargets.map((target, index) => {
                const isSelected = targetOptionValue(target) === selectedTargetValue;
                return (
                  <li key={`${target.conversation_id || target.security_id}-${index}`}>
                    <button
                      type="button"
                      className={isSelected ? "is-selected" : ""}
                      aria-pressed={isSelected}
                      onClick={() => pickTarget(target)}
                    >
                      <strong>{target.company || "未知公司"} · {target.title || "未知职位"}</strong>
                      <span>
                        {(target.recruiter_name || "未命名 HR")}
                        {target.unread_count ? ` · 未读 ${target.unread_count}` : ""}
                        {isSelected ? " · 已选" : ""}
                      </span>
                      <em>{target.last_message || target.security_id}</em>
                    </button>
                  </li>
                );
              })
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
          <div className="target-picker">
            <div className="target-picker__summary">
              <strong>Boss 发送目标</strong>
              <span>
                {selectedChatTarget
                  ? `${selectedChatTarget.company || "未知公司"} / ${selectedChatTarget.recruiter_name || "未命名 HR"}`
                  : applyForm.security_id.trim()
                    ? "已手动填写 security_id"
                    : "未选择，发简历请求不会真实发送"}
              </span>
            </div>
            <div className="target-picker__controls">
              {chatTargets.length ? (
                <select
                  className="target-picker__select"
                  value={selectedTargetValue}
                  onChange={(event) => handleTargetSelection(event.target.value)}
                >
                  <option value="">选择真实 Boss 对话目标</option>
                  {chatTargets.map((target, index) => (
                    <option
                      key={`${targetOptionValue(target)}-${index}`}
                      value={targetOptionValue(target)}
                    >
                      {`${target.company || "未知公司"} · ${target.recruiter_name || "未命名 HR"} · ${target.title || "未知职位"}`}
                    </option>
                  ))}
                </select>
              ) : (
                <span className="target-picker__empty">
                  {chatTargetsLoading ? "正在读取目标..." : "暂无可选目标"}
                </span>
              )}
              <button
                type="button"
                className="inline-action"
                onClick={loadChatTargets}
                disabled={chatTargetsLoading}
              >
                <ArrowClockwise size={16} />
                {chatTargetsLoading ? "刷新中" : "刷新目标"}
              </button>
            </div>
          </div>
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
                    ? "已通过 Boss 真实发送附件简历 PDF。"
                    : result.delivery.send_attachment_resume
                      ? "附件简历 PDF 没有成功发出。"
                    : "已通过 Boss 真实发送这条 Agent 草稿消息。"}
                </p>
              ) : result.delivery?.status === "sending" ? (
                <p>
                  已识别为发简历请求，正在通过 Boss 真实发送{result.delivery.send_attachment_resume ? "附件简历 PDF" : "这条 Agent 草稿"}。
                </p>
              ) : result.delivery?.status === "browser_channel_unavailable" ? (
                <p>
                  发送到 Boss 失败：{result.delivery.error_message || "当前 CDP / Bridge 不可用。"}
                </p>
              ) : result.delivery?.status === "disabled" ? (
                <p>已识别为发简历请求，但本地未开启自动发送。</p>
              ) : result.delivery?.status === "missing_security_id" ? (
                <p>发送到 Boss 失败：当前没有可用的 `security_id`。</p>
              ) : result.delivery?.status === "resume_failed" || result.delivery?.status === "message_failed" ? (
                <p>
                  {result.delivery.status === "resume_failed"
                    ? `附件简历 PDF 发送失败：${result.delivery.error_message || "未知错误"}。`
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
                  <p>这一步会提交到本地 Agent bridge `/api/agent/ask`，再整理最终 answer / citations。</p>
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
                {!bridgeState.browserChannel.available &&
                bridgeState.browserChannel.errorMessage ? (
                  <span>
                    当前浏览器发送通道不可用：{bridgeState.browserChannel.errorMessage}
                  </span>
                ) : null}
              </div>
              <div className="answer-actions__controls">
                <label className="send-toggle">
                  <input
                    type="checkbox"
                    checked={sendResumeWithDraft}
                    onChange={(event) => setSendResumeWithDraft(event.target.checked)}
                  />
                  <span>发送附件简历 PDF</span>
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

{/* ── Boss 自动开聊 ──────────────────────────────── */}
      <section className="apply-panel apply-panel--inline">
        <div className="apply-panel__header" onClick={() => setApplyMode((m) => !m)}>
          <div className="apply-panel__title-row">
            <Lightning size={22} weight="bold" />
            <h2>Boss 自动开聊</h2>
          </div>
          <span className="apply-panel__toggle">{applyMode ? "收起 ▲" : "展开 ▼"}</span>
        </div>

        {applyMode && (
          <div className="apply-panel__body">
            <div className="apply-search__inputs">
              <input
                className="apply-input"
                placeholder="关键词"
                value={bossSearchForm.query}
                onChange={(event) => updateBossSearchForm("query", event.target.value)}
              />
              <select
                className="apply-input apply-input--city"
                value={bossSearchForm.city}
                onChange={(event) => updateBossSearchForm("city", event.target.value)}
              >
                {bossCityOptions.map((city) => (
                  <option key={city} value={city}>{city}</option>
                ))}
              </select>
              <select
                className="apply-input apply-input--salary"
                value={bossSearchForm.salary}
                onChange={(event) => updateBossSearchForm("salary", event.target.value)}
              >
                {bossSalaryOptions.map((salary) => (
                  <option key={salary || "none"} value={salary}>
                    {salary || "薪资不限"}
                  </option>
                ))}
              </select>
              <details className="apply-multi-select apply-input--experience">
                <summary className="apply-multi-select__summary">
                  <span>{bossExperienceSummary}</span>
                </summary>
                <div className="apply-multi-select__menu">
                  <label className="apply-multi-select__option">
                    <input
                      type="checkbox"
                      checked={selectedBossExperiences.length === 0}
                      onChange={() => toggleBossExperience("")}
                    />
                    <span>经验不限</span>
                  </label>
                  {bossExperienceOptions.filter(Boolean).map((experience) => (
                    <label className="apply-multi-select__option" key={experience}>
                      <input
                        type="checkbox"
                        checked={selectedBossExperiences.includes(experience)}
                        onChange={() => toggleBossExperience(experience)}
                      />
                      <span>{experience}</span>
                    </label>
                  ))}
                </div>
              </details>
              <select
                className="apply-input apply-input--education"
                value={bossSearchForm.education}
                onChange={(event) => updateBossSearchForm("education", event.target.value)}
              >
                {bossEducationOptions.map((education) => (
                  <option key={education || "none"} value={education}>
                    {education || "学历不限"}
                  </option>
                ))}
              </select>
              <select
                className="apply-input apply-input--industry"
                value={bossSearchForm.industry}
                onChange={(event) => updateBossSearchForm("industry", event.target.value)}
              >
                {bossIndustryOptions.map((industry) => (
                  <option key={industry || "none"} value={industry}>
                    {industry || "行业不限"}
                  </option>
                ))}
              </select>
              <select
                className="apply-input apply-input--scale"
                value={bossSearchForm.scale}
                onChange={(event) => updateBossSearchForm("scale", event.target.value)}
              >
                {bossScaleOptions.map((scale) => (
                  <option key={scale || "none"} value={scale}>
                    {scale || "规模不限"}
                  </option>
                ))}
              </select>
              <select
                className="apply-input apply-input--stage"
                value={bossSearchForm.stage}
                onChange={(event) => updateBossSearchForm("stage", event.target.value)}
              >
                {bossStageOptions.map((stage) => (
                  <option key={stage || "none"} value={stage}>
                    {stage || "融资不限"}
                  </option>
                ))}
              </select>
              <select
                className="apply-input apply-input--job-type"
                value={bossSearchForm.jobType}
                onChange={(event) => updateBossSearchForm("jobType", event.target.value)}
              >
                {bossJobTypeOptions.map((jobType) => (
                  <option key={jobType || "none"} value={jobType}>
                    {jobType || "类型不限"}
                  </option>
                ))}
              </select>
              <input
                className="apply-input apply-input--welfare"
                placeholder="福利关键词"
                value={bossSearchForm.welfare}
                onChange={(event) => updateBossSearchForm("welfare", event.target.value)}
              />
              <select
                className="apply-input apply-input--count"
                value={bossSearchForm.count}
                onChange={(event) => updateBossSearchForm("count", event.target.value)}
              >
                {["1", "2", "3", "5", "10", "20", "50", "100", "150"].map((count) => (
                  <option key={count} value={count}>{count} 个</option>
                ))}
              </select>
              <button
                type="button"
                className="apply-btn apply-btn--search"
                onClick={handleBossSearchPreview}
                disabled={isBossSearching || bossSearchActionsDisabled}
              >
                <MagnifyingGlass size={16} />
                {isBossSearching ? "搜索中..." : "预览"}
              </button>
              <button
                type="button"
                className="apply-btn apply-btn--send apply-btn--compact"
                onClick={handleBossAutoGreet}
                disabled={isBossAutoRunning || bossSearchActionsDisabled}
              >
                <PaperPlaneTilt size={16} weight="fill" />
                {bossAutoButtonLabel}
              </button>
            </div>

            {bossAutomationError ? (
              <div className="apply-result apply-result--error">
                <WarningCircle size={18} weight="fill" />
                <span>{bossAutomationError}</span>
              </div>
            ) : null}

            {isBossAutoRunning ? (
              <div className="apply-result apply-result--pending">
                <Lightning size={18} weight="fill" />
                <div className="apply-result__content">
                  <span>
                    {bossAutomationIsGreeting
                      ? `正在和第 ${bossAutomationProgressCurrent}${bossAutomationProgressTotal ? ` / ${bossAutomationProgressTotal}` : ""} 个候选开聊`
                      : bossAutomationProgress?.message || "正在搜索可开聊候选，还没有开始聊天。"}
                  </span>
                  {bossAutomationIsGreeting && (bossAutomationProgress?.title || bossAutomationProgress?.company) ? (
                    <span className="apply-result__detail">
                      {[bossAutomationProgress.title, bossAutomationProgress.company].filter(Boolean).join(" @ ")}
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}

            {bossAutomationResult ? (
              <div className={`apply-result ${bossAutomationHasIssue ? "apply-result--error" : "apply-result--ok"}`}>
                {bossAutomationHasIssue ? (
                  <WarningCircle size={18} weight="fill" />
                ) : (
                  <CheckCircle size={18} weight="fill" />
                )}
                <div className="apply-result__content">
                  <span>
                    已开聊 {bossAutomationResult.total_greeted || 0} 个，
                    失败 {bossAutomationResult.total_failed || 0} 个
                    {bossAutomationResult.stopped_reason ? `，停止原因：${bossAutomationResult.stopped_reason}` : ""}
                  </span>
                  {bossAutomationResult.stopped_error ? (
                    <span className="apply-result__detail">{bossAutomationResult.stopped_error}</span>
                  ) : null}
                  {bossAutomationFailedItems.length ? (
                    <ul className="apply-result__failure-list">
                      {bossAutomationFailedItems.slice(0, 4).map((item, index) => {
                        const label = [item?.title, item?.company].filter(Boolean).join(" @ ") ||
                          item?.security_id ||
                          `候选 ${index + 1}`;
                        return (
                          <li key={`${item?.security_id || item?.job_id || label}-${index}`}>
                            {label}：{item?.error || "未知失败"}
                          </li>
                        );
                      })}
                      {bossAutomationFailedItems.length > 4 ? (
                        <li>还有 {bossAutomationFailedItems.length - 4} 个失败项</li>
                      ) : null}
                    </ul>
                  ) : null}
                </div>
              </div>
            ) : null}

            {normalizedBossJobs.length ? (
              <div className="apply-job-list">
                {normalizedBossJobs.slice(0, 6).map((job, index) => (
                  <button
                    type="button"
                    className="apply-job-item"
                    key={`${job.security_id || job.job_id}-${index}`}
                    onClick={() => {
                      if (job.security_id) {
                        setApplyForm({ security_id: job.security_id });
                        setSelectedTargetValue("");
                      }
                    }}
                  >
                    <span className="apply-job-item__main">
                      <strong>{job.title}</strong>
                      <span>{job.company}</span>
                    </span>
                    <span className="apply-job-item__meta">
                      {[job.city, job.salary, job.experience].filter(Boolean).join(" · ")}
                    </span>
                  </button>
                ))}
              </div>
            ) : null}

            <div className="apply-form">
              {chatTargets.length ? (
                <div className="apply-form__row">
                  <div className="apply-field">
                    <label>对话发送目标</label>
                    <select
                      className="apply-input"
                      value={selectedTargetValue}
                      onChange={(e) => handleTargetSelection(e.target.value)}
                    >
                      <option value="">选择已回复的 Boss 对话目标</option>
                      {chatTargets.map((target, index) => (
                        <option
                          key={`${targetOptionValue(target)}-${index}`}
                          value={targetOptionValue(target)}
                        >
                          {`${target.company || "未知公司"} · ${target.recruiter_name || "未命名 HR"} · ${target.title || "未知职位"}`}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : null}

              {selectedChatTarget ? (
                <div className="apply-result apply-result--ok">
                  <CheckCircle size={18} weight="fill" />
                  <span>
                    已选对话目标：{selectedChatTarget.company || "未知公司"} /{" "}
                    {selectedChatTarget.recruiter_name || "未命名 HR"} /{" "}
                    {selectedChatTarget.security_id || "无 security_id"}
                  </span>
                </div>
              ) : null}

              <div className="apply-form__row">
                <div className="apply-field">
                  <label>Security ID</label>
                  <input
                    className="apply-input"
                    placeholder="已回复对话的 security_id"
                    value={applyForm.security_id}
                    onChange={(e) => {
                      setApplyForm({ security_id: e.target.value });
                      setSelectedTargetValue("");
                    }}
                  />
                </div>
              </div>
              <div className="apply-result">
                <span>
                  选好目标后，直接去上面的提问区输入“麻烦发一下简历”，再看 `发送到 Boss` /
                  auto-send 的真实返回即可。
                </span>
              </div>
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
              <span>转发到 `POST /api/agent/ask`</span>
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
                      ? "已调用 Boss 对话真实发送附件简历 PDF"
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
