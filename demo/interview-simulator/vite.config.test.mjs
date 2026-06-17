import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBossDeliveryBlockPayload,
  detectBossDeliveryChannel,
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
