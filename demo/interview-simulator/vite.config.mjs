import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const BOSS_GEEK_CHAT_URL = "https://www.zhipin.com/web/geek/chat";
const CDP_REQUIRED_FOR_BOSS_DELIVERY_MESSAGE =
  "Boss 自动开聊/发送需要 CDP 真实 Chrome（127.0.0.1:9229）。当前只检测到 Bridge 扩展；为保护账号，已停止本次自动触达。请用 --remote-debugging-port=9229 打开真实 Chrome 后刷新本页面。";
const DELIVERY_PROBE_CACHE_TTL_MS = 10_000;
const DELIVERY_PROBE_SOCKET_OPEN_TIMEOUT_MS = 3_000;
const DELIVERY_PROBE_COMMAND_TIMEOUT_MS = 3_000;
const DEFAULT_COMMAND_TIMEOUT_SECONDS = 45;
const MIN_COMMAND_TIMEOUT_SECONDS = 5;
const MAX_BOSS_AUTO_GREET_COUNT = 150;
const BOSS_AUTO_GREET_TIMEOUT_BASE_SECONDS = 180;
const BOSS_AUTO_GREET_TIMEOUT_PER_ITEM_SECONDS = 10;
let cachedDeliveryProbe = null;
let pendingDeliveryProbe = null;

function parseEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const values = {};
  for (const line of fs.readFileSync(filePath, "utf8").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
    const [key, ...rest] = trimmed.split("=");
    values[key] = rest.join("=").trim().replace(/^['"]|['"]$/g, "");
  }
  return values;
}

function resolveCommandTimeoutMs(rawValue) {
  const parsed = Number.parseInt(String(rawValue ?? DEFAULT_COMMAND_TIMEOUT_SECONDS), 10);
  const seconds = Number.isFinite(parsed) && parsed > 0
    ? Math.max(parsed, MIN_COMMAND_TIMEOUT_SECONDS)
    : DEFAULT_COMMAND_TIMEOUT_SECONDS;
  return seconds * 1000;
}

function resolveBossAutoGreetCommandTimeoutMs(commandTimeoutMs, rawCount) {
  const parsed = Number.parseInt(String(rawCount ?? ""), 10);
  const count = Number.isFinite(parsed)
    ? Math.min(Math.max(parsed, 1), MAX_BOSS_AUTO_GREET_COUNT)
    : 3;
  const batchTimeoutMs = (
    BOSS_AUTO_GREET_TIMEOUT_BASE_SECONDS +
    count * BOSS_AUTO_GREET_TIMEOUT_PER_ITEM_SECONDS
  ) * 1000;
  return Math.max(commandTimeoutMs || 0, batchTimeoutMs);
}

function loadBridgeConfig() {
  const repoRoot = path.resolve(process.cwd(), "..", "..");
  const repoEnv = parseEnvFile(path.join(repoRoot, ".env"));
  const get = (key, fallback = "") =>
    process.env[key] || repoEnv[key] || fallback;

  return {
    repoRoot,
    dataDir: get("BOSS_RAG_DATA_DIR", "~/.boss-agent"),
    pythonBin: get("BOSS_RAG_PYTHON_BIN", get("PYTHON", "python")),
    resumeAttachmentPath: get(
      "BOSS_RAG_RESUME_ATTACHMENT_PATH",
      path.join(repoRoot, "孙瑞杰的简历.pdf"),
    ),
    commandTimeoutMs: resolveCommandTimeoutMs(
      get("BOSS_RAG_COMMAND_TIMEOUT_SECONDS", String(DEFAULT_COMMAND_TIMEOUT_SECONDS)),
    ),
    baseUrl: get("BOSS_RAG_RAG_BASE_URL", "").replace(/\/$/, ""),
    cdpUrl: get("BOSS_RAG_CDP_URL", get("BOSS_CDP_URL", "http://localhost:9229")).replace(/\/$/, ""),
    bridgeUrl: get("BOSS_RAG_BRIDGE_URL", "http://127.0.0.1:19826").replace(/\/$/, ""),
    authMode: get("BOSS_RAG_RAG_AUTH_MODE", "none").toLowerCase(),
    apiKey:
      get("BOSS_RAG_RAG_API_KEY") ||
      get("RAG_API_KEY") ||
      get("RAG_AUTH_API_KEY") ||
      "",
  };
}

function buildBossCliArgs(config, args) {
  const cliArgs = [
    "-c",
    "from boss_agent_cli.main import cli; import sys; cli.main(args=sys.argv[1:], standalone_mode=False)",
    "--json",
    "--data-dir",
    config.dataDir,
  ];
  if (config.cdpUrl) {
    cliArgs.push("--cdp-url", config.cdpUrl);
  }
  cliArgs.push(...args);
  return cliArgs;
}

async function readJsonWithTimeout(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

async function postJsonWithTimeout(url, payload, timeoutMs = 3000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      return {
        ok: false,
        errorMessage: await response.text(),
      };
    }
    return await response.json();
  } catch (error) {
    return {
      ok: false,
      errorMessage: error instanceof Error ? error.message : "Bridge probe 请求失败。",
    };
  } finally {
    clearTimeout(timer);
  }
}

async function detectBrowserChannel(config) {
  const cdpVersion = await readJsonWithTimeout(`${config.cdpUrl}/json/version`);
  const bridgeStatus = await readJsonWithTimeout(`${config.bridgeUrl}/status`);

  const cdpAvailable = Boolean(cdpVersion?.webSocketDebuggerUrl);
  const bridgeAvailable = Boolean(bridgeStatus?.extensionConnected);
  const available = cdpAvailable || bridgeAvailable;

  let mode = "none";
  if (cdpAvailable && bridgeAvailable) {
    mode = "cdp+bridge";
  } else if (cdpAvailable) {
    mode = "cdp";
  } else if (bridgeAvailable) {
    mode = "bridge";
  }

  return {
    available,
    mode,
    cdpAvailable,
    bridgeAvailable,
    cdpUrl: config.cdpUrl,
    bridgeUrl: config.bridgeUrl,
    errorMessage: available
      ? ""
      : `未检测到可用的浏览器发送通道：CDP (${config.cdpUrl}) / Bridge (${config.bridgeUrl})。请先启动带 remote debugging 的 Chrome，或连接 BOSS Agent Bridge 扩展。`,
  };
}

async function evaluateBridgeProbe(bridgeUrl) {
  const result = await postJsonWithTimeout(`${bridgeUrl}/command`, {
    id: `vite_probe_${Date.now()}`,
    action: "exec",
    workspace: "boss",
    allowCreate: false,
    code: "(() => ({ href: location.href, title: document.title }))()",
  });
  if (!result?.ok) {
    return {
      ok: false,
      errorMessage: result?.error || result?.errorMessage || "Bridge exec 探针失败。",
    };
  }

  const data = result.data && typeof result.data === "object" ? result.data : {};
  return {
    ok: true,
    href: String(data.href || ""),
    title: String(data.title || ""),
  };
}

async function listCdpTargets(cdpUrl) {
  const payload = await readJsonWithTimeout(`${cdpUrl}/json/list`, 2000);
  return Array.isArray(payload)
    ? payload.filter((item) => item && typeof item === "object")
    : [];
}

function findCandidateChatTarget(targets) {
  return targets.find((target) => {
    if (target?.type !== "page") return false;
    const url = String(target?.url || "");
    return url.includes("/web/geek/chat");
  }) || null;
}

async function evaluateCdpProbeTarget(target, { url = BOSS_GEEK_CHAT_URL, navigate = true } = {}) {
  if (!target?.webSocketDebuggerUrl) {
    return {
      ok: false,
      href: "",
      title: "",
      hasUserList: false,
      bodySnippet: "",
      navigationEvents: [],
      errorMessage: "CDP probe target 缺少 webSocketDebuggerUrl。",
    };
  }

  const navigationEvents = [];
  const ws = new WebSocket(target.webSocketDebuggerUrl);
  let requestId = 0;
  const pending = new Map();
  let socketOpened = false;
  let probeFinished = false;

  function rejectPending(error) {
    for (const [id, entry] of pending.entries()) {
      pending.delete(id);
      entry.reject(error);
    }
  }

  const waitForSocketOpen = new Promise((resolve, reject) => {
    const openTimer = setTimeout(() => {
      reject(new Error(`CDP probe WebSocket did not open within ${DELIVERY_PROBE_SOCKET_OPEN_TIMEOUT_MS}ms.`));
    }, DELIVERY_PROBE_SOCKET_OPEN_TIMEOUT_MS);

    ws.onopen = () => {
      clearTimeout(openTimer);
      socketOpened = true;
      resolve();
    };
    ws.onerror = (error) => {
      clearTimeout(openTimer);
      const failure = error instanceof Error
        ? error
        : new Error("CDP probe WebSocket error.");
      if (!socketOpened) {
        reject(failure);
      }
      if (!probeFinished) {
        rejectPending(failure);
      }
    };
    ws.onclose = () => {
      clearTimeout(openTimer);
      const failure = new Error("CDP probe WebSocket closed before probe completed.");
      if (!socketOpened) {
        reject(failure);
      }
      if (!probeFinished) {
        rejectPending(failure);
      }
    };
  });

  function trackNavigationEvent(data) {
    const candidateUrl =
      data?.params?.url ||
      data?.params?.frame?.url ||
      "";
    if (!candidateUrl) return;
    navigationEvents.push({
      method: String(data.method || "unknown"),
      url: String(candidateUrl),
    });
  }

  function send(method, params = {}) {
    const id = ++requestId;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error(`CDP probe ${method} timed out after ${DELIVERY_PROBE_COMMAND_TIMEOUT_MS}ms.`));
      }, DELIVERY_PROBE_COMMAND_TIMEOUT_MS);

      pending.set(id, {
        resolve: (result) => {
          clearTimeout(timer);
          resolve(result);
        },
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
      });

      try {
        ws.send(JSON.stringify({ id, method, params }));
      } catch (error) {
        clearTimeout(timer);
        pending.delete(id);
        reject(error instanceof Error ? error : new Error(`CDP probe ${method} send failed.`));
      }
    });
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.id && pending.has(data.id)) {
      const { resolve, reject } = pending.get(data.id);
      pending.delete(data.id);
      if (data.error) reject(new Error(JSON.stringify(data.error)));
      else resolve(data.result);
      return;
    }

    if (
      data.method === "Page.frameScheduledNavigation" ||
      data.method === "Page.frameRequestedNavigation" ||
      data.method === "Page.frameStartedNavigating" ||
      data.method === "Page.frameNavigated" ||
      data.method === "Page.navigatedWithinDocument"
    ) {
      trackNavigationEvent(data);
    }
  };

  try {
    await waitForSocketOpen;
    await send("Page.enable");
    await send("Runtime.enable");
    if (navigate) {
      await send("Page.navigate", { url });
      await new Promise((resolve) => setTimeout(resolve, 6500));
    }

    const result = await send("Runtime.evaluate", {
      expression: `(() => JSON.stringify({
        href: location.href,
        title: document.title,
        hasUserList: !!document.querySelector('.user-list-content'),
        bodySnippet: (document.body?.innerText || '').slice(0, 500)
      }))()`,
      returnByValue: true,
      awaitPromise: true,
    });

    let snapshot = {
      href: "",
      title: "",
      hasUserList: false,
      bodySnippet: "",
    };
    try {
      snapshot = JSON.parse(result?.result?.value || "{}");
    } catch {
      snapshot = {
        href: "",
        title: "",
        hasUserList: false,
        bodySnippet: "",
      };
    }

    return {
      ok: true,
      ...snapshot,
      navigationEvents,
      errorMessage: "",
    };
  } catch (error) {
    return {
      ok: false,
      href: "",
      title: "",
      hasUserList: false,
      bodySnippet: "",
      navigationEvents,
      errorMessage: error instanceof Error ? error.message : "CDP probe 执行失败。",
    };
  } finally {
    probeFinished = true;
    try {
      ws.close();
    } catch {
      // noop
    }
  }
}

async function detectBossDeliveryChannel(config) {
  const transport = await detectBrowserChannel(config);
  const baseState = {
    ...transport,
    transportAvailable: transport.available,
    chatPageReachable: false,
    chatPageUrl: BOSS_GEEK_CHAT_URL,
    preflightStatus: transport.available ? "pending" : "transport_unavailable",
    lastObservedUrl: "",
    lastObservedTitle: "",
    redirectUrl: "",
  };

  if (!transport.cdpAvailable) {
    if (transport.bridgeAvailable) {
      return {
        ...baseState,
        available: false,
        preflightStatus: "cdp_required",
        errorMessage: CDP_REQUIRED_FOR_BOSS_DELIVERY_MESSAGE,
      };
    }
    return {
      ...baseState,
      available: false,
    };
  }

  const cacheKey = config.cdpUrl;
  if (
    cachedDeliveryProbe &&
    cachedDeliveryProbe.key === cacheKey &&
    cachedDeliveryProbe.expiresAt > Date.now()
  ) {
    return cachedDeliveryProbe.value;
  }

  if (pendingDeliveryProbe?.key === cacheKey) {
    return pendingDeliveryProbe.promise;
  }

  const probePromise = runCdpDeliveryProbe(config, baseState, cacheKey);
  pendingDeliveryProbe = {
    key: cacheKey,
    promise: probePromise,
  };
  try {
    return await probePromise;
  } finally {
    if (pendingDeliveryProbe?.promise === probePromise) {
      pendingDeliveryProbe = null;
    }
  }
}

async function runCdpDeliveryProbe(config, baseState, cacheKey) {
  const existingChatTarget = findCandidateChatTarget(await listCdpTargets(config.cdpUrl));

  if (!existingChatTarget) {
    const missing = {
      ...baseState,
      available: false,
      preflightStatus: "chat_tab_missing",
      errorMessage:
        "未检测到已打开的 Boss 聊天页。为避免自动创建或导航 BOSS 页面，请手动打开 https://www.zhipin.com/web/geek/chat 后刷新本页面。",
    };
    cachedDeliveryProbe = {
      key: cacheKey,
      expiresAt: Date.now() + DELIVERY_PROBE_CACHE_TTL_MS,
      value: missing,
    };
    return missing;
  }

  if (!existingChatTarget?.id && !existingChatTarget?.webSocketDebuggerUrl) {
    const unavailable = {
      ...baseState,
      available: false,
      preflightStatus: "probe_target_unavailable",
      errorMessage: "无法创建 CDP 临时探针页面，暂时不能验证 Boss 聊天页是否可达。",
    };
    cachedDeliveryProbe = {
      key: cacheKey,
      expiresAt: Date.now() + DELIVERY_PROBE_CACHE_TTL_MS,
      value: unavailable,
    };
    return unavailable;
  }

  let probeResult;
  probeResult = await evaluateCdpProbeTarget(existingChatTarget, {
    url: BOSS_GEEK_CHAT_URL,
    navigate: false,
  });

  const redirectEvent = Array.isArray(probeResult?.navigationEvents)
    ? probeResult.navigationEvents.find((item) => String(item?.url || "").includes("/web/user/"))
    : null;
  const redirectedToLogin =
    Boolean(redirectEvent) ||
    String(probeResult?.href || "").includes("/web/user/");

  let resolved;
  if (!probeResult?.ok) {
    resolved = {
      ...baseState,
      available: false,
      preflightStatus: "probe_failed",
      errorMessage:
        probeResult?.errorMessage || "Boss 聊天页预检失败，暂时不能确认发送链路可用。",
    };
  } else if (probeResult.hasUserList) {
    resolved = {
      ...baseState,
      available: true,
      chatPageReachable: true,
      preflightStatus: "ready",
      lastObservedUrl: String(probeResult.href || ""),
      lastObservedTitle: String(probeResult.title || ""),
      errorMessage: "",
    };
  } else if (redirectedToLogin) {
    resolved = {
      ...baseState,
      available: false,
      preflightStatus: "chat_login_redirect",
      lastObservedUrl: String(probeResult.href || ""),
      lastObservedTitle: String(probeResult.title || ""),
      redirectUrl: String(redirectEvent?.url || probeResult?.href || ""),
      errorMessage:
        "Boss 聊天页当前不可达：CDP Chrome 访问 `/web/geek/chat` 时被重定向到了 `/web/user/`。这通常表示当前 9229 profile 的 Boss 聊天登录前置态无效。",
    };
  } else {
    resolved = {
      ...baseState,
      available: false,
      preflightStatus: "chat_page_unreachable",
      lastObservedUrl: String(probeResult.href || ""),
      lastObservedTitle: String(probeResult.title || ""),
      errorMessage:
        "Boss 聊天页未能进入可发送状态：没有检测到候选人聊天列表（`.user-list-content`）。",
    };
  }

  cachedDeliveryProbe = {
    key: cacheKey,
    expiresAt: Date.now() + DELIVERY_PROBE_CACHE_TTL_MS,
    value: resolved,
  };
  return resolved;
}

function buildBossDeliveryBlockPayload(browserChannel) {
  if (browserChannel?.available && browserChannel?.cdpAvailable) return null;

  const errorMessage = String(
    browserChannel?.errorMessage || CDP_REQUIRED_FOR_BOSS_DELIVERY_MESSAGE,
  );
  const code = browserChannel?.cdpAvailable
    ? "BROWSER_CHANNEL_UNAVAILABLE"
    : "BROWSER_CDP_REQUIRED";

  return {
    statusCode: 503,
    body: {
      ok: false,
      errorMessage,
      browserChannel,
      error: {
        code,
        message: errorMessage,
        recoverable: true,
      },
      delivery: {
        status: "browser_channel_unavailable",
        message_sent: false,
        resume_sent: false,
        error_message: errorMessage,
      },
    },
  };
}

export function resetDeliveryProbeCacheForTests() {
  cachedDeliveryProbe = null;
  pendingDeliveryProbe = null;
}

export {
  buildBossCliArgs,
  buildBossDeliveryBlockPayload,
  detectBossDeliveryChannel,
  resolveBossAutoGreetCommandTimeoutMs,
  resolveCommandTimeoutMs,
};

function readBody(req) {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (chunk) => {
      data += chunk;
    });
    req.on("end", () => resolve(data));
    req.on("error", reject);
  });
}

function normalizeThread(sessionId, messages) {
  const safeMessages = Array.isArray(messages) ? messages : [];
  return {
    sessionId,
    turnCount: safeMessages.filter((item) => item.role === "user").length,
    messageCount: safeMessages.length,
    messages: safeMessages,
  };
}

function runBossJsonCommand(config, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(
      config.pythonBin,
      buildBossCliArgs(config, args),
      {
        cwd: config.repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: process.env.PYTHONPATH
            ? `${config.repoRoot}/src:${process.env.PYTHONPATH}`
            : `${config.repoRoot}/src`,
        },
      },
    );

    let stdout = "";
    let stderr = "";
    let timedOut = false;
    const timeoutMs = options.timeoutMs ?? config.commandTimeoutMs;
    const timer = timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          child.kill("SIGTERM");
        }, timeoutMs)
      : null;

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", (error) => {
      if (timer) clearTimeout(timer);
      reject(error);
    });
    child.on("close", (status) => {
      if (timer) clearTimeout(timer);
      if (timedOut) {
        const seconds = Math.round((timeoutMs || 0) / 1000);
        reject(new Error(`boss-agent-cli 执行超过 ${seconds}s，已停止本次请求。请检查 CDP 发送链路或稍后重试。`));
        return;
      }
      if (status !== 0 && !stdout.trim()) {
        reject(new Error(stderr.trim() || `boss command failed with exit code ${status}`));
        return;
      }

      let parsed = {};
      try {
        parsed = stdout.trim() ? JSON.parse(stdout) : {};
      } catch (error) {
        reject(new Error(`无法解析 boss-agent-cli 输出: ${stdout.trim() || stderr.trim() || String(error)}`));
        return;
      }

      if (!parsed.ok) {
        const errorMessage =
          parsed.error?.message ||
          parsed.errorMessage ||
          stderr.trim() ||
          "boss-agent-cli 返回错误。";
        const commandError = new Error(errorMessage);
        commandError.commandPayload = parsed;
        reject(commandError);
        return;
      }
      resolve(parsed);
    });
  });
}

function writeNdjson(res, event) {
  res.write(`${JSON.stringify(event)}\n`);
}

function parseBossProgressLine(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{")) return null;
  try {
    const event = JSON.parse(trimmed);
    return event?.type === "boss_auto_greet_progress" ? event : null;
  } catch {
    return null;
  }
}

function runBossJsonCommandStream(config, args, res, options = {}) {
  return new Promise((resolve) => {
    const child = spawn(
      config.pythonBin,
      buildBossCliArgs(config, args),
      {
        cwd: config.repoRoot,
        env: {
          ...process.env,
          PYTHONPATH: process.env.PYTHONPATH
            ? `${config.repoRoot}/src:${process.env.PYTHONPATH}`
            : `${config.repoRoot}/src`,
        },
      },
    );

    let stdout = "";
    let stderr = "";
    let stderrBuffer = "";
    let timedOut = false;
    const timeoutMs = options.timeoutMs ?? config.commandTimeoutMs;
    const timer = timeoutMs
      ? setTimeout(() => {
          timedOut = true;
          child.kill("SIGTERM");
        }, timeoutMs)
      : null;

    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      stdout += chunk;
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
      stderrBuffer += chunk;
      const lines = stderrBuffer.split(/\r?\n/);
      stderrBuffer = lines.pop() || "";
      for (const line of lines) {
        const progress = parseBossProgressLine(line);
        if (progress) {
          writeNdjson(res, { type: "progress", data: progress });
        }
      }
    });
    child.on("error", (error) => {
      if (timer) clearTimeout(timer);
      writeNdjson(res, {
        type: "error",
        ok: false,
        errorMessage: error instanceof Error ? error.message : "自动开聊失败",
        error: null,
      });
      resolve();
    });
    child.on("close", (status) => {
      if (timer) clearTimeout(timer);
      if (stderrBuffer.trim()) {
        const progress = parseBossProgressLine(stderrBuffer);
        if (progress) {
          writeNdjson(res, { type: "progress", data: progress });
        }
      }
      if (timedOut) {
        const seconds = Math.round((timeoutMs || 0) / 1000);
        writeNdjson(res, {
          type: "error",
          ok: false,
          errorMessage: `boss-agent-cli 执行超过 ${seconds}s，已停止本次请求。请检查 CDP 发送链路或稍后重试。`,
          error: null,
        });
        resolve();
        return;
      }
      if (status !== 0 && !stdout.trim()) {
        writeNdjson(res, {
          type: "error",
          ok: false,
          errorMessage: stderr.trim() || `boss command failed with exit code ${status}`,
          error: null,
        });
        resolve();
        return;
      }

      let parsed = {};
      try {
        parsed = stdout.trim() ? JSON.parse(stdout) : {};
      } catch (error) {
        writeNdjson(res, {
          type: "error",
          ok: false,
          errorMessage: `无法解析 boss-agent-cli 输出: ${stdout.trim() || stderr.trim() || String(error)}`,
          error: null,
        });
        resolve();
        return;
      }

      if (!parsed.ok) {
        writeNdjson(res, {
          type: "error",
          ok: false,
          errorMessage:
            parsed.error?.message ||
            parsed.errorMessage ||
            stderr.trim() ||
            "boss-agent-cli 返回错误。",
          error: parsed.error || null,
        });
        resolve();
        return;
      }
      writeNdjson(res, {
        type: "result",
        ok: true,
        data: parsed.data,
        hints: parsed.hints,
      });
      resolve();
    });
  });
}

function createRagBridgePlugin() {
  const bridgeConfig = loadBridgeConfig();

  async function handler(req, res) {
    if (!req.url) return false;
    const isAgentHealth = req.url === "/api/agent/health" || req.url === "/api/rag/health";
    const isAgentThread = req.url.startsWith("/api/agent/thread") || req.url.startsWith("/api/rag/thread");
    const isAgentTargets = req.url.startsWith("/api/agent/targets") || req.url.startsWith("/api/rag/targets");
    const isAgentAsk = req.url === "/api/agent/ask" || req.url === "/api/rag/ask";
    const isAgentSend = req.url === "/api/agent/send" || req.url === "/api/rag/send";
    const isWatcherStatus = req.url === "/api/agent/watcher/status";
    const isWatcherRun = req.url === "/api/agent/watcher/run";
    const isWatcherControl = req.url === "/api/agent/watcher/control";

    if (req.method === "GET" && isAgentHealth) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        await runBossJsonCommand(bridgeConfig, ["agent", "init"]);
        const browserChannel = await detectBossDeliveryChannel(bridgeConfig);
        const ready =
          Boolean(bridgeConfig.baseUrl) &&
          (bridgeConfig.authMode === "none" || Boolean(bridgeConfig.apiKey));
        res.end(
          JSON.stringify({
            configured: Boolean(bridgeConfig.baseUrl),
            ready,
            authMode: bridgeConfig.authMode || "none",
            endpoint: "/api/agent/ask + /api/agent/send",
            workflow: "boss-agent-cli",
            dataDir: bridgeConfig.dataDir,
            browserChannel,
            errorMessage: bridgeConfig.baseUrl
              ? ""
              : "未找到 BOSS_RAG_RAG_BASE_URL，BOSS_AGENT workflow 无法调用 Enterprise RAG。",
          }),
        );
      } catch (error) {
        res.statusCode = 500;
        res.end(
          JSON.stringify({
            configured: Boolean(bridgeConfig.baseUrl),
            ready: false,
            authMode: bridgeConfig.authMode || "none",
            endpoint: "/api/agent/ask + /api/agent/send",
            workflow: "boss-agent-cli",
            dataDir: bridgeConfig.dataDir,
            browserChannel: await detectBossDeliveryChannel(bridgeConfig),
            errorMessage:
              error instanceof Error ? error.message : "本地 workflow 初始化失败。",
          }),
        );
      }
      return true;
    }

    if (req.method === "GET" && isAgentThread) {
      const requestUrl = new URL(req.url, "http://127.0.0.1");
      const sessionId = String(requestUrl.searchParams.get("sessionId") || "").trim();
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      if (!sessionId) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, errorMessage: "sessionId 不能为空。" }));
        return true;
      }
      try {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "thread",
          "--conversation-id",
          sessionId,
        ]);
        res.end(
          JSON.stringify({
            ok: true,
            thread: normalizeThread(sessionId, payload.data?.messages),
          }),
        );
      } catch (error) {
        const payload = error?.commandPayload;
        res.statusCode = payload?.error?.code === "INVALID_PARAM" ? 400 : 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "读取多轮 memory 失败。",
          }),
        );
      }
      return true;
    }

    if (req.method === "GET" && isAgentTargets) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const requestUrl = new URL(req.url, "http://127.0.0.1");
        const parsedLimit = Number.parseInt(requestUrl.searchParams.get("limit") || "5", 10);
        const safeLimit = Number.isFinite(parsedLimit) ? Math.min(Math.max(parsedLimit, 1), 20) : 5;
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "targets",
          "--limit",
          String(safeLimit),
        ]);
        const data = payload.data || {};
        res.end(
          JSON.stringify({
            ok: true,
            targets: Array.isArray(data.targets) ? data.targets : [],
            count: Number(data.count || 0),
            source: String(data.source || "cache"),
            liveReadEnabled: Boolean(data.live_read_enabled),
            refreshed: Boolean(data.refreshed),
            refreshError: String(data.refresh_error || ""),
          }),
        );
      } catch (error) {
        const payload = error?.commandPayload;
        res.statusCode =
          payload?.error?.code === "INVALID_PARAM"
            ? 400
            : payload?.error?.recoverable
              ? 502
              : 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "读取 Boss 对话目标失败。",
            targets: [],
          }),
        );
      }
      return true;
    }

    if (req.method === "GET" && isWatcherStatus) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = await runBossJsonCommand(bridgeConfig, ["agent", "watcher-status"]);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "读取 watcher 状态失败。",
            data: { running: false, dry_run: true, tasks: [] },
          }),
        );
      }
      return true;
    }

    if (req.method === "POST" && isWatcherRun) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        const liveSync = Boolean(body.liveSync);
        const ensureChatPage = Boolean(body.ensureChatPage);
        const args = ["agent", "watcher-run", "--once"];
        if (liveSync) args.push("--live-sync");
        if (ensureChatPage) args.push("--ensure-chat-page");
        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        const payload = error?.commandPayload;
        res.statusCode = payload?.error?.recoverable ? 502 : 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "运行 watcher 失败。",
          }),
        );
      }
      return true;
    }

    if (req.method === "POST" && isWatcherControl) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const parsed = rawBody ? JSON.parse(rawBody) : {};
        const action = String(parsed.action || "").trim();
        const conversationId = String(parsed.conversation_id || "").trim();
        if (!["pause", "resume"].includes(action)) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "action 必须是 pause 或 resume。" }));
          return true;
        }
        const args = ["agent", action === "pause" ? "watcher-pause" : "watcher-resume"];
        if (conversationId) args.push("--conversation-id", conversationId);
        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({ ok: true, data: payload.data || {} }));
      } catch (error) {
        res.statusCode = 500;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              error instanceof Error ? error.message : "更新 watcher 控制状态失败。",
          }),
        );
      }
      return true;
    }

    if (req.method === "POST" && isAgentSend) {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const parsed = rawBody ? JSON.parse(rawBody) : {};
        const draftId = String(parsed.draftId || "").trim();
        const securityId = String(parsed.security_id || "").trim();
        const sendResume = Boolean(parsed.send_resume);
        const sendAttachmentResume = Boolean(parsed.send_attachment_resume);
        const resumeFile = String(parsed.resume_file || bridgeConfig.resumeAttachmentPath || "").trim();
        const target = parsed.target && typeof parsed.target === "object" ? parsed.target : {};
        const targetRecruiterName = String(
          parsed.target_recruiter_name || target.recruiter_name || "",
        ).trim();
        const targetCompany = String(parsed.target_company || target.company || "").trim();
        const targetTitle = String(parsed.target_title || target.title || "").trim();

        if (!draftId) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "draftId 不能为空。" }));
          return true;
        }

        const browserChannel = await detectBossDeliveryChannel(bridgeConfig);
        if (!browserChannel.available) {
          res.statusCode = 503;
          res.end(
            JSON.stringify({
              ok: false,
              errorMessage: browserChannel.errorMessage,
              browserChannel,
              delivery: {
                status: "browser_channel_unavailable",
                message_sent: false,
                resume_sent: false,
                error_message: browserChannel.errorMessage,
              },
            }),
          );
          return true;
        }

        const args = ["agent", "send", draftId];
        if (securityId) args.push("--security-id", securityId);
        if (sendResume) args.push("--send-resume");
        if (sendAttachmentResume) args.push("--send-attachment-resume");
        if (sendAttachmentResume && resumeFile) args.push("--resume-file", resumeFile);
        if (targetRecruiterName) args.push("--target-recruiter-name", targetRecruiterName);
        if (targetCompany) args.push("--target-company", targetCompany);
        if (targetTitle) args.push("--target-title", targetTitle);

        const payload = await runBossJsonCommand(bridgeConfig, args);
        const data = payload.data || {};
        const deliveryStatus = sendAttachmentResume
          ? (data.resume_sent ? "sent" : "resume_failed")
          : !data.message_sent
            ? "message_failed"
            : sendResume && !data.resume_sent
              ? "resume_failed"
              : "sent";

        res.end(
          JSON.stringify({
            ok: true,
            draftId: String(data.draft?.draft_id || draftId),
            delivery: {
              status: deliveryStatus,
              message_sent: Boolean(data.message_sent),
              resume_sent: Boolean(data.resume_sent),
              send_resume: Boolean(data.send_resume),
              send_attachment_resume: Boolean(data.send_attachment_resume),
              resume_file: String(data.resume_file || resumeFile),
              security_id: String(data.security_id || securityId),
              target: data.target || {
                recruiter_name: targetRecruiterName,
                company: targetCompany,
                title: targetTitle,
              },
              results: Array.isArray(data.results) ? data.results : [],
              error_message: String(data.error_message || ""),
            },
            rawResponse: {
              command: payload.command,
              draft: data.draft || null,
            },
            browserChannel,
          }),
        );
      } catch (error) {
        const payload = error?.commandPayload;
        const errorMessage =
          error instanceof Error ? error.message : "发送到 Boss 对话失败。";
        const normalizedStatus = errorMessage.includes("security_id")
          ? "missing_security_id"
          : "message_failed";
        const status =
          payload?.error?.code === "INVALID_PARAM"
            ? 400
            : payload?.error?.recoverable
              ? 502
              : 500;
        res.statusCode = status;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage,
            browserChannel: await detectBossDeliveryChannel(bridgeConfig),
            delivery: {
              status: normalizedStatus,
              message_sent: false,
              resume_sent: false,
              error_message: errorMessage,
            },
          }),
        );
      }
      return true;
    }

    // ── Boss Apply API ────────────────────────────────────────────
    if (req.method === "POST" && req.url === "/api/boss/apply") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        const securityId = String(body.security_id || "").trim();
        const jobId = String(body.job_id || "").trim();
        const resumeName = String(body.resume_name || "").trim();
        const title = String(body.title || "").trim();
        const company = String(body.company || "").trim();
        const message = String(body.message || "").trim();
        const lid = String(body.lid || "").trim();

        if (!securityId || !jobId) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "security_id 和 job_id 不能为空。" }));
          return true;
        }

        const args = ["apply", securityId, jobId];
        if (lid) args.push("--lid", lid);
        if (resumeName) args.push("--resume", resumeName);
        if (title) args.push("--title", title);
        if (company) args.push("--company", company);
        if (message) args.push("--message", message);

        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({
          ok: true,
          data: payload.data,
          hints: payload.hints,
        }));
      } catch (error) {
        const p = error?.commandPayload;
        res.statusCode = p?.error?.recoverable ? 400 : 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "投递失败",
          error: p?.error || null,
        }));
      }
      return true;
    }

    // ── Boss Search API ───────────────────────────────────────────
    if (req.method === "POST" && req.url === "/api/boss/search") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        const query = String(body.query || "").trim();
        const city = String(body.city || "北京").trim();
        const salary = String(body.salary || "").trim();
        const experience = String(body.experience || "").trim();
        const education = String(body.education || "").trim();
        const industry = String(body.industry || "").trim();
        const scale = String(body.scale || "").trim();
        const stage = String(body.stage || "").trim();
        const jobType = String(body.jobType || body.job_type || "").trim();
        const welfare = String(body.welfare || "").trim();

        if (!query) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "query 不能为空。" }));
          return true;
        }

        const args = ["search", query, "--no-cache"];
        if (city) args.push("--city", city);
        if (salary) args.push("--salary", salary);
        if (experience) args.push("--experience", experience);
        if (education) args.push("--education", education);
        if (industry) args.push("--industry", industry);
        if (scale) args.push("--scale", scale);
        if (stage) args.push("--stage", stage);
        if (jobType) args.push("--job-type", jobType);
        if (welfare) args.push("--welfare", welfare);

        const payload = await runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({
          ok: true,
          data: payload.data,
        }));
      } catch (error) {
        const p = error?.commandPayload;
        res.statusCode = p?.error?.recoverable ? 400 : 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "搜索失败",
          error: p?.error || null,
        }));
      }
      return true;
    }

    // ── Boss Auto Greet API ───────────────────────────────────────
    if (req.method === "POST" && req.url === "/api/boss/auto-greet") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const rawBody = await readBody(req);
        const body = rawBody ? JSON.parse(rawBody) : {};
        const query = String(body.query || "").trim();
        const city = String(body.city || "北京").trim();
        const salary = String(body.salary || "").trim();
        const experience = String(body.experience || "").trim();
        const education = String(body.education || "").trim();
        const industry = String(body.industry || "").trim();
        const scale = String(body.scale || "").trim();
        const stage = String(body.stage || "").trim();
        const jobType = String(body.jobType || body.job_type || "").trim();
        const welfare = String(body.welfare || "").trim();
        const rawCount = Number.parseInt(String(body.count || "3"), 10);
        const count = Number.isFinite(rawCount)
          ? Math.min(Math.max(rawCount, 1), MAX_BOSS_AUTO_GREET_COUNT)
          : 3;
        const stream = Boolean(body.stream);

        if (!query) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "query 不能为空。" }));
          return true;
        }

        const browserChannel = await detectBossDeliveryChannel(bridgeConfig);
        const blocked = buildBossDeliveryBlockPayload(browserChannel);
        if (blocked) {
          res.statusCode = blocked.statusCode;
          res.end(JSON.stringify(blocked.body));
          return true;
        }

        const args = [
          "batch-greet",
          query,
          "--count",
          String(count),
        ];
        if (city) args.push("--city", city);
        if (salary) args.push("--salary", salary);
        if (experience) args.push("--experience", experience);
        if (education) args.push("--education", education);
        if (industry) args.push("--industry", industry);
        if (scale) args.push("--scale", scale);
        if (stage) args.push("--stage", stage);
        if (jobType) args.push("--job-type", jobType);
        if (welfare) args.push("--welfare", welfare);
        if (stream) args.push("--progress-json");

        if (stream) {
          res.setHeader("Content-Type", "application/x-ndjson; charset=utf-8");
          res.setHeader("Cache-Control", "no-cache");
          writeNdjson(res, {
            type: "status",
            status: "searching",
            message: "正在搜索可开聊候选，还没有开始聊天。",
          });
          await runBossJsonCommandStream(bridgeConfig, args, res, {
            timeoutMs: resolveBossAutoGreetCommandTimeoutMs(bridgeConfig.commandTimeoutMs, count),
          });
          res.end();
          return true;
        }

        const payload = await runBossJsonCommand(bridgeConfig, args, {
          timeoutMs: resolveBossAutoGreetCommandTimeoutMs(bridgeConfig.commandTimeoutMs, count),
        });
        res.end(JSON.stringify({
          ok: true,
          data: payload.data,
          hints: payload.hints,
        }));
      } catch (error) {
        const p = error?.commandPayload;
        res.statusCode = p?.error?.recoverable ? 400 : 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "自动开聊失败",
          error: p?.error || null,
        }));
      }
      return true;
    }

    // ── Boss Resume List API ──────────────────────────────────────
    if (req.method === "GET" && req.url === "/api/boss/resumes") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = await runBossJsonCommand(bridgeConfig, ["resume", "list"]);
        res.end(JSON.stringify({ ok: true, data: payload.data }));
      } catch (error) {
        res.statusCode = 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "读取简历列表失败",
        }));
      }
      return true;
    }

    if (req.method !== "POST" || !isAgentAsk) return false;

    res.setHeader("Content-Type", "application/json; charset=utf-8");

    if (!bridgeConfig.baseUrl) {
      res.statusCode = 500;
      res.end(
        JSON.stringify({
          ok: false,
          errorMessage:
            "BOSS_RAG_RAG_BASE_URL 未配置，无法通过 BOSS_AGENT workflow 调用 Enterprise RAG。",
        }),
      );
      return true;
    }

    try {
      const rawBody = await readBody(req);
      const parsed = rawBody ? JSON.parse(rawBody) : {};
      const question = String(parsed.question || "").trim();
      const sessionId = String(parsed.sessionId || "").trim() || `session-${Date.now()}`;
      const jobId = String(parsed.job_id || "").trim();
      const recruiterId = String(parsed.recruiter_id || "").trim();
      const securityId = String(parsed.security_id || "").trim();
      const autoSendResume = Boolean(parsed.auto_send_resume);

      if (!question) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, errorMessage: "question 不能为空。" }));
        return true;
      }

      const args = [
        "agent",
        "ask",
        "--conversation-id",
        sessionId,
        "--question",
        question,
      ];
      if (jobId) args.push("--job-id", jobId);
      if (recruiterId) args.push("--recruiter-id", recruiterId);
      if (securityId) args.push("--security-id", securityId);
      if (autoSendResume) args.push("--auto-send-resume");

      const payload = await runBossJsonCommand(bridgeConfig, args);
      const data = payload.data || {};
      const draft = data.draft || {};
      const thread = normalizeThread(sessionId, data.thread);

      if (data.audit_status === "rag_failed" && !String(data.answer || "").trim()) {
        res.statusCode = 502;
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              data.error_message || "BOSS_AGENT workflow 未能生成可用回答。",
            auditStatus: String(data.audit_status || "rag_failed"),
            thread,
          }),
        );
        return true;
      }

      res.end(
          JSON.stringify({
            ok: true,
            answer: String(data.answer || draft.draft_text || ""),
            citations: Array.isArray(data.citations) ? data.citations : [],
          reasoningSummary:
            data.reasoning_summary && typeof data.reasoning_summary === "object"
              ? data.reasoning_summary
              : null,
          auditStatus: String(data.audit_status || draft.audit_status || "answered"),
          draftId: String(draft.draft_id || ""),
          draftIntent: String(draft.intent || ""),
          draft,
          rawResponse: {
            command: payload.command,
            conversationId: data.conversation_id,
            draft,
            question,
          },
          delivery:
            data.delivery && typeof data.delivery === "object"
              ? data.delivery
              : null,
          thread,
        }),
      );
      return true;
    } catch (error) {
      const payload = error?.commandPayload;
      const message =
        error instanceof Error ? error.message : "本地 RAG 代理调用失败。";
      const status =
        payload?.error?.code === "INVALID_PARAM"
          ? 400
          : payload?.error?.recoverable
            ? 502
            : 500;
      res.statusCode = status;
      res.end(
        JSON.stringify({
          ok: false,
          errorMessage: message,
          auditStatus: "rag_failed",
        }),
      );
      return true;
    }
  }

  function attach(server) {
    server.middlewares.use((req, res, next) => {
      handler(req, res).then((handled) => {
        if (!handled) next();
      });
    });
  }

  return {
    name: "local-rag-bridge",
    configureServer(server) {
      attach(server);
    },
    configurePreviewServer(server) {
      attach(server);
    },
  };
}

export default defineConfig({
  optimizeDeps: {
    include: ["react", "react-dom/client"],
  },
  server: {
    warmup: {
      clientFiles: ["./src/main.jsx"],
    },
  },
  plugins: [react(), createRagBridgePlugin()],
});
