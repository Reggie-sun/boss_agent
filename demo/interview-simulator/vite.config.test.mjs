import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBossDeliveryBlockPayload,
  detectBossDeliveryChannel,
  resolveBossAutoGreetCommandTimeoutMs,
  resolveCommandTimeoutMs,
  resetDeliveryProbeCacheForTests,
} from "./vite.config.mjs";

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

test("detectBossDeliveryChannel reuses an in-flight CDP probe", async () => {
  const originalFetch = globalThis.fetch;
  const originalWebSocket = globalThis.WebSocket;
  let createdTargets = 0;
  let closedTargets = 0;

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
    const method = options.method || "GET";

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
    if (requestUrl.startsWith("http://cdp.test/json/new?")) {
      assert.equal(method, "PUT");
      createdTargets += 1;
      return Response.json({
        id: `target-${createdTargets}`,
        webSocketDebuggerUrl: `ws://cdp.test/target-${createdTargets}`,
      });
    }
    if (requestUrl.startsWith("http://cdp.test/json/close/")) {
      closedTargets += 1;
      return new Response("OK");
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

    assert.equal(first.available, true);
    assert.equal(second.available, true);
    assert.equal(first.preflightStatus, "ready");
    assert.equal(second.preflightStatus, "ready");
    assert.equal(createdTargets, 1);
    assert.equal(closedTargets, 1);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
    globalThis.WebSocket = originalWebSocket;
  }
});
