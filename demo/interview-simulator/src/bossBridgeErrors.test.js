import assert from "node:assert/strict";
import test from "node:test";

import {
  bossAccountRiskCode,
  bossBridgeErrorCode,
  bossBridgeErrorFromPayload,
  bossBridgeErrorMessage,
  inferBossBridgeErrorCodeFromMessage,
} from "./bossBridgeErrors.js";

test("inferBossBridgeErrorCodeFromMessage treats 环境存在异常 as token refresh failure", () => {
  assert.equal(inferBossBridgeErrorCodeFromMessage("您的环境存在异常."), "TOKEN_REFRESH_FAILED");
});

test("bossBridgeErrorMessage shows login recovery guidance for token refresh failures", () => {
  const error = bossBridgeErrorFromPayload(
    {
      ok: false,
      errorMessage: "您的环境存在异常.",
      error: {
        code: "TOKEN_REFRESH_FAILED",
        message: "您的环境存在异常.",
      },
    },
    "Agent 自动开聊失败。",
  );

  assert.equal(bossBridgeErrorCode(error), "TOKEN_REFRESH_FAILED");
  assert.match(bossBridgeErrorMessage(error, "Agent 自动开聊失败。"), /登录状态已失效|token 刷新失败/);
  assert.doesNotMatch(bossBridgeErrorMessage(error, "Agent 自动开聊失败。"), /风控|安全验证/);
});

test("bossBridgeErrorMessage keeps explicit account risk responses locked", () => {
  const error = bossBridgeErrorFromPayload(
    {
      ok: false,
      error: {
        code: bossAccountRiskCode,
        message: "请先完成安全验证",
      },
    },
    "BOSS 搜索失败。",
  );

  assert.equal(bossBridgeErrorCode(error), bossAccountRiskCode);
  assert.match(bossBridgeErrorMessage(error, "BOSS 搜索失败。"), /风控|安全验证/);
});

test("bossBridgeErrorMessage keeps auth-expired responses out of the risk bucket", () => {
  const error = bossBridgeErrorFromPayload(
    {
      ok: false,
      error: {
        code: "AUTH_EXPIRED",
        message: "当前登录状态已失效",
      },
    },
    "BOSS 搜索失败。",
  );

  assert.equal(bossBridgeErrorCode(error), "AUTH_EXPIRED");
  assert.match(bossBridgeErrorMessage(error, "BOSS 搜索失败。"), /已失效|token 刷新失败/);
  assert.doesNotMatch(bossBridgeErrorMessage(error, "BOSS 搜索失败。"), /风控|安全验证/);
});
