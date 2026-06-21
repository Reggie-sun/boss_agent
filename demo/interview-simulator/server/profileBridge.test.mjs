import assert from "node:assert/strict";
import test from "node:test";

import { createProfileBridgeHandlers } from "./profileBridge.mjs";

function createResponseRecorder() {
  return {
    body: "",
    headers: {},
    statusCode: 0,
    setHeader(name, value) {
      this.headers[name] = value;
    },
    end(body) {
      this.body = body;
    },
  };
}

test("profile binding bridge normalizes unsupported binding source to manual", async () => {
  let capturedArgs = [];
  const handler = createProfileBridgeHandlers({
    bridgeConfig: {},
    readBody: async () =>
      JSON.stringify({
        conversation_id: "conv_001",
        tenant_id: "tenant_local",
        user_id: "user_local",
        profile_id: "profile_001",
        binding_source: "frontend_profile_hub",
      }),
    runBossJsonCommand: async (_config, args) => {
      capturedArgs = args;
      return { data: { binding: { profile_id: "profile_001" } } };
    },
  });
  const res = createResponseRecorder();

  const handled = await handler(
    { method: "POST", url: "/api/agent/profile-binding" },
    res,
  );

  assert.equal(handled, true);
  assert.equal(res.statusCode, 200);
  assert.deepEqual(
    capturedArgs.slice(capturedArgs.indexOf("--binding-source")),
    ["--binding-source", "manual"],
  );
});
