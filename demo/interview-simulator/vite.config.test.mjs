import assert from "node:assert/strict";
import test from "node:test";

import {
  detectBossDeliveryChannel,
  resetDeliveryProbeCacheForTests,
} from "./vite.config.mjs";

test("detectBossDeliveryChannel accepts bridge-only channel after safe exec probe", async () => {
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
      const body = JSON.parse(String(options.body || "{}"));
      assert.equal(body.action, "exec");
      assert.match(body.code, /location\.href/);
      assert.equal(body.workspace, "boss");
      assert.equal(body.allowCreate, false);
      return Response.json({
        id: body.id,
        ok: true,
        data: {
          href: "https://www.zhipin.com/",
          title: "BOSS直聘",
        },
      });
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
    assert.equal(state.mode, "bridge");
    assert.equal(state.preflightStatus, "bridge_ready");
    assert.equal(state.lastObservedUrl, "https://www.zhipin.com/");
    assert.equal(state.errorMessage, "");
    assert.equal(calls.some((call) => call.url.includes("/json/new")), false);
  } finally {
    resetDeliveryProbeCacheForTests();
    globalThis.fetch = originalFetch;
  }
});
