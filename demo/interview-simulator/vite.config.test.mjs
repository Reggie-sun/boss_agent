import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentAskResponsePayload,
  buildBossCliArgs,
  buildBossDeliveryBlockPayload,
  buildWatcherRunCommandOptions,
  detectBossDeliveryChannel,
  resolveBossAutoGreetCommandTimeoutMs,
  resolveCommandTimeoutMs,
  resetDeliveryProbeCacheForTests,
} from "./vite.config.mjs";

test("buildBossCliArgs injects cdp url into spawned boss commands", () => {
  const args = buildBossCliArgs(
    {
      dataDir: "~/.boss-agent",
      cdpUrl: "http://localhost:9229",
    },
    ["search", "RAG"],
  );

  assert.deepEqual(args, [
    "-c",
    "from boss_agent_cli.main import cli; import sys; cli.main(args=sys.argv[1:], standalone_mode=False)",
    "--json",
    "--data-dir",
    "~/.boss-agent",
    "--cdp-url",
    "http://localhost:9229",
    "search",
    "RAG",
  ]);
});

test("buildWatcherRunCommandOptions defaults prototype watcher runs to dry-run", () => {
  assert.deepEqual(buildWatcherRunCommandOptions(true), {
    env: {
      BOSS_RAG_SEND_ENABLED: "false",
      BOSS_RAG_WATCHER_DRY_RUN: "true",
    },
  });

  assert.deepEqual(buildWatcherRunCommandOptions(false), { env: {} });
});

test("detectBossDeliveryChannel requires CDP instead of bridge-only exec probe", async () => {
  const originalFetch = globalThis.fetch;
  const calls = [];

  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);
    calls.push({ url: requestUrl, method: options.method || "GET", body: options.body || "" });

    if (requestUrl === "http://cdp.test/json/version") {
      return Response.json({}, { status: 404 });
    }
    if (requestUrl === "http://bridge.test/status") {
      return Response.json({
        ok: true,
        extensionConnected: true,
        extensionVersion: "1.0.0",
      });
    }
    if (requestUrl === "http://bridge.test/command") {
      throw new Error("bridge exec probe should not run for delivery preflight");
    }
    throw new Error(`unexpected fetch: ${requestUrl}`);
  };

  try {
    resetDeliveryProbeCacheForTests();
    const state = await detectBossDeliveryChannel({
      cdpUrl: "http://cdp.test",
      bridgeUrl: "http://bridge.test",
    });

    assert.equal(state.available, false);
    assert.equal(state.mode, "bridge");
    assert.equal(state.preflightStatus, "cdp_required");
    assert.equal(state.lastObservedUrl, "");
    assert.match(state.errorMessage, /CDP/);
    assert.match(state.errorMessage, /Bridge/);
    assert.doesNotMatch(state.errorMessage, /环境存在异常|异常访问|风控|安全验证/);
    assert.equal(calls.some((call) => call.url.includes("/json/new")), false);
    assert.equal(calls.some((call) => call.url.endsWith("/command")), false);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
  }
});

test("buildBossDeliveryBlockPayload returns a non-risk CDP-required response", () => {
  const browserChannel = {
    available: false,
    cdpAvailable: false,
    bridgeAvailable: true,
    errorMessage: "Boss 自动开聊/发送需要 CDP 真实 Chrome。",
  };

  const blocked = buildBossDeliveryBlockPayload(browserChannel);

  assert.equal(blocked.statusCode, 503);
  assert.equal(blocked.body.ok, false);
  assert.equal(blocked.body.error.code, "BROWSER_CDP_REQUIRED");
  assert.equal(blocked.body.error.recoverable, true);
  assert.equal(blocked.body.browserChannel, browserChannel);
  assert.equal(blocked.body.delivery.status, "browser_channel_unavailable");
  assert.doesNotMatch(blocked.body.errorMessage, /环境存在异常|异常访问|风控|安全验证/);
});

test("buildAgentAskResponsePayload rejects empty successful agent drafts", () => {
  const response = buildAgentAskResponsePayload({
    payload: {
      command: ["agent", "ask"],
      data: {
        answer: "",
        audit_status: "draft_created",
        draft: {
          draft_text: "",
          audit_status: "draft_created",
          intent: "unsafe_or_unclear",
        },
      },
    },
    question: "解释一下神经网络",
    sessionId: "session-test",
  });

  assert.equal(response.statusCode, 502);
  assert.equal(response.body.ok, false);
  assert.match(response.body.errorMessage, /未能生成可用回答/);
  assert.equal(response.body.auditStatus, "draft_created");
  assert.equal(response.body.draftIntent, "unsafe_or_unclear");
});

test("buildAgentAskResponsePayload surfaces nested profile RAG errors", () => {
  const response = buildAgentAskResponsePayload({
    payload: {
      command: ["agent", "ask"],
      data: {
        answer: "",
        audit_status: "profile_context_invalid",
        draft: {
          draft_text: "",
          audit_status: "profile_context_invalid",
          intent: "project_question",
          evidence: {
            error_message:
              "tenant_id/user_id/profile_id/knowledge_base_id/conversation_id are required.",
          },
        },
      },
    },
    question: "介绍一下 RAG 项目",
    sessionId: "boss_conv_1",
  });

  assert.equal(response.statusCode, 502);
  assert.equal(response.body.ok, false);
  assert.match(response.body.errorMessage, /knowledge_base_id/);
  assert.equal(response.body.auditStatus, "profile_context_invalid");
});

test("buildAgentAskResponsePayload explains missing profile binding", () => {
  const response = buildAgentAskResponsePayload({
    payload: {
      command: ["agent", "ask"],
      data: {
        answer: "",
        audit_status: "profile_binding_required",
        draft: {
          draft_text: "",
          audit_status: "profile_binding_required",
          intent: "project_question",
        },
      },
    },
    question: "请介绍一下候选人的 RAG 项目",
    sessionId: "boss_conv_without_profile",
  });

  assert.equal(response.statusCode, 502);
  assert.equal(response.body.ok, false);
  assert.match(response.body.errorMessage, /绑定当前对话/);
  assert.equal(response.body.auditStatus, "profile_binding_required");
});

test("detectBossDeliveryChannel does not open a CDP probe tab when chat tab is missing", async () => {
  const originalFetch = globalThis.fetch;
  let createdTargets = 0;

  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);

    if (requestUrl === "http://cdp.test/json/version") {
      return Response.json({
        webSocketDebuggerUrl: "ws://cdp.test/browser",
      });
    }
    if (requestUrl === "http://bridge.test/status") {
      return Response.json({
        ok: true,
        extensionConnected: false,
      });
    }
    if (requestUrl === "http://cdp.test/json/list") {
      return Response.json([
        {
          id: "jobs-tab",
          type: "page",
          url: "https://www.zhipin.com/web/geek/jobs",
          webSocketDebuggerUrl: "ws://cdp.test/jobs-tab",
        },
      ]);
    }
    if (requestUrl.startsWith("http://cdp.test/json/new?")) {
      createdTargets += 1;
      throw new Error(`delivery health probe must not open CDP target via ${options.method || "GET"}`);
    }
    throw new Error(`unexpected fetch: ${requestUrl}`);
  };

  try {
    resetDeliveryProbeCacheForTests();
    const state = await detectBossDeliveryChannel({
      cdpUrl: "http://cdp.test",
      bridgeUrl: "http://bridge.test",
    });

    assert.equal(state.available, false);
    assert.equal(state.preflightStatus, "chat_tab_missing");
    assert.match(state.errorMessage, /手动打开|chat/);
    assert.equal(createdTargets, 0);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
  }
});

test("resolveCommandTimeoutMs treats zero as default instead of infinite wait", () => {
  assert.equal(resolveCommandTimeoutMs("0"), 45_000);
  assert.equal(resolveCommandTimeoutMs(""), 45_000);
  assert.equal(resolveCommandTimeoutMs("3"), 5_000);
  assert.equal(resolveCommandTimeoutMs("120"), 120_000);
});

test("resolveBossAutoGreetCommandTimeoutMs scales for 150-candidate batches", () => {
  assert.equal(resolveBossAutoGreetCommandTimeoutMs(45_000, "1"), 190_000);
  assert.equal(resolveBossAutoGreetCommandTimeoutMs(45_000, "10"), 280_000);
  assert.equal(resolveBossAutoGreetCommandTimeoutMs(45_000, "150"), 1_680_000);
  assert.equal(resolveBossAutoGreetCommandTimeoutMs(1_800_000, "150"), 1_800_000);
  assert.equal(resolveBossAutoGreetCommandTimeoutMs(45_000, "999"), 1_680_000);
});

test("detectBossDeliveryChannel reuses an in-flight missing-chat probe", async () => {
  const originalFetch = globalThis.fetch;
  let listCalls = 0;
  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);

    if (requestUrl === "http://cdp.test/json/version") {
      return Response.json({
        webSocketDebuggerUrl: "ws://cdp.test/browser",
      });
    }
    if (requestUrl === "http://bridge.test/status") {
      return Response.json({
        ok: true,
        extensionConnected: false,
      });
    }
    if (requestUrl === "http://cdp.test/json/list") {
      listCalls += 1;
      await new Promise((resolve) => setTimeout(resolve, 25));
      return Response.json([
        {
          id: "jobs-tab",
          type: "page",
          url: "https://www.zhipin.com/web/geek/jobs",
          webSocketDebuggerUrl: "ws://cdp.test/jobs-tab",
        },
      ]);
    }
    if (requestUrl.startsWith("http://cdp.test/json/new?")) {
      throw new Error(`missing-chat probe must not open CDP target via ${options.method || "GET"}`);
    }
    throw new Error(`unexpected fetch: ${requestUrl}`);
  };

  try {
    resetDeliveryProbeCacheForTests();
    const [first, second] = await Promise.all([
      detectBossDeliveryChannel({
        cdpUrl: "http://cdp.test",
        bridgeUrl: "http://bridge.test",
      }),
      detectBossDeliveryChannel({
        cdpUrl: "http://cdp.test",
        bridgeUrl: "http://bridge.test",
      }),
    ]);

    assert.equal(first.available, false);
    assert.equal(second.available, false);
    assert.equal(first.preflightStatus, "chat_tab_missing");
    assert.equal(second.preflightStatus, "chat_tab_missing");
    assert.equal(listCalls, 1);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
  }
});

test("detectBossDeliveryChannel reuses an existing candidate chat tab before opening a probe tab", async () => {
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  let createdTargets = 0;

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      queueMicrotask(() => this.onopen?.());
    }

    send(raw) {
      const message = JSON.parse(raw);
      const result = message.method === "Runtime.evaluate"
        ? {
            result: {
              value: JSON.stringify({
                href: "https://www.zhipin.com/web/geek/chat",
                title: "BOSS直聘",
                hasUserList: true,
                bodySnippet: "候选人列表",
              }),
            },
          }
        : {};
      queueMicrotask(() => {
        this.onmessage?.({
          data: JSON.stringify({
            id: message.id,
            result,
          }),
        });
      });
    }

    close() {}
  }

  globalThis.WebSocket = FakeWebSocket;
  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);

    if (requestUrl === "http://cdp.test/json/version") {
      return Response.json({
        webSocketDebuggerUrl: "ws://cdp.test/browser",
      });
    }
    if (requestUrl === "http://bridge.test/status") {
      return Response.json({
        ok: true,
        extensionConnected: false,
      });
    }
    if (requestUrl === "http://cdp.test/json/list") {
      return Response.json([
        {
          id: "jobs-tab",
          type: "page",
          url: "https://www.zhipin.com/web/geek/jobs",
          webSocketDebuggerUrl: "ws://cdp.test/jobs-tab",
        },
        {
          id: "chat-tab",
          type: "page",
          url: "https://www.zhipin.com/web/geek/chat",
          webSocketDebuggerUrl: "ws://cdp.test/chat-tab",
        },
      ]);
    }
    if (requestUrl.startsWith("http://cdp.test/json/new?")) {
      createdTargets += 1;
      throw new Error("existing chat tab should be reused before opening a probe tab");
    }
    throw new Error(`unexpected fetch: ${requestUrl}`);
  };

  try {
    resetDeliveryProbeCacheForTests();
    const state = await detectBossDeliveryChannel({
      cdpUrl: "http://cdp.test",
      bridgeUrl: "http://bridge.test",
    });

    assert.equal(state.available, true);
    assert.equal(state.preflightStatus, "ready");
    assert.equal(state.lastObservedUrl, "https://www.zhipin.com/web/geek/chat");
    assert.equal(createdTargets, 0);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
  }
});

test("detectBossDeliveryChannel fails fast when an in-flight CDP probe socket closes", async () => {
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  let createdTargets = 0;

  class FakeWebSocket {
    constructor(url) {
      this.url = url;
      queueMicrotask(() => this.onopen?.());
    }

    send() {
      queueMicrotask(() => this.onclose?.());
    }

    close() {}
  }

  globalThis.WebSocket = FakeWebSocket;
  globalThis.fetch = async (url, options = {}) => {
    const requestUrl = String(url);
    if (requestUrl === "http://cdp.test/json/version") {
      return Response.json({
        webSocketDebuggerUrl: "ws://cdp.test/browser",
      });
    }
    if (requestUrl === "http://bridge.test/status") {
      return Response.json({
        ok: true,
        extensionConnected: false,
      });
    }
    if (requestUrl === "http://cdp.test/json/list") {
      return Response.json([
        {
          id: "chat-tab",
          type: "page",
          url: "https://www.zhipin.com/web/geek/chat",
          webSocketDebuggerUrl: "ws://cdp.test/chat-tab",
        },
      ]);
    }
    if (requestUrl.startsWith("http://cdp.test/json/new?")) {
      createdTargets += 1;
      throw new Error(`existing-chat probe must not open CDP target via ${options.method || "GET"}`);
    }
    throw new Error(`unexpected fetch: ${requestUrl}`);
  };

  try {
    resetDeliveryProbeCacheForTests();
    const [first, second] = await Promise.race([
      Promise.all([
        detectBossDeliveryChannel({
          cdpUrl: "http://cdp.test",
          bridgeUrl: "http://bridge.test",
        }),
        detectBossDeliveryChannel({
          cdpUrl: "http://cdp.test",
          bridgeUrl: "http://bridge.test",
        }),
      ]),
      new Promise((_, reject) => {
        setTimeout(() => reject(new Error("probe promise remained pending")), 1_000);
      }),
    ]);

    assert.equal(first.available, false);
    assert.equal(second.available, false);
    assert.equal(first.preflightStatus, "probe_failed");
    assert.equal(second.preflightStatus, "probe_failed");
    assert.match(first.errorMessage, /WebSocket closed/);
    assert.match(second.errorMessage, /WebSocket closed/);
    assert.equal(createdTargets, 0);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
  }
});
