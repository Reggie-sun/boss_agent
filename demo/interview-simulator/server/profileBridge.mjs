function sendJson(res, statusCode, payload) {
  res.statusCode = statusCode;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(payload));
}

function responseData(payload) {
  return payload && typeof payload === "object" && "data" in payload
    ? payload.data
    : payload;
}

function appendTextOption(args, flag, value) {
  const normalized = String(value || "").trim();
  if (normalized) args.push(flag, normalized);
}

function appendBooleanOption(args, enabledFlag, disabledFlag, value) {
  if (value === true) args.push(enabledFlag);
  if (value === false) args.push(disabledFlag);
}

function normalizeBindingSource(value) {
  const normalized = String(value || "").trim();
  return ["default", "imported", "manual"].includes(normalized)
    ? normalized
    : "manual";
}

function profileIdFromPath(pathname, suffix) {
  return decodeURIComponent(
    pathname.slice("/api/agent/profiles/".length, -suffix.length),
  );
}

export function createProfileBridgeHandlers({
  bridgeConfig,
  runBossJsonCommand,
  readBody,
}) {
  return async function handleProfileBridge(req, res) {
    const url = new URL(req.url, "http://127.0.0.1");
    try {
      if (req.method === "GET" && url.pathname === "/api/agent/profiles") {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "list",
          "--tenant-id",
          String(url.searchParams.get("tenant_id") || "tenant_local"),
          "--user-id",
          String(url.searchParams.get("user_id") || "user_local"),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (req.method === "POST" && url.pathname === "/api/agent/profiles") {
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "profile",
          "create",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--name",
          String(body.name || body.display_name || ""),
          "--target-title",
          String(body.target_title || ""),
        ];
        appendTextOption(args, "--knowledge-base-id", body.knowledge_base_id);
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (
        req.method === "GET" &&
        url.pathname.startsWith("/api/agent/profiles/") &&
        url.pathname.endsWith("/config")
      ) {
        const profileId = profileIdFromPath(url.pathname, "/config");
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "config",
          "get",
          "--profile-id",
          profileId,
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (
        req.method === "PATCH" &&
        url.pathname.startsWith("/api/agent/profiles/") &&
        url.pathname.endsWith("/config")
      ) {
        const profileId = profileIdFromPath(url.pathname, "/config");
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "profile",
          "config",
          "set",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--profile-id",
          profileId,
        ];
        appendTextOption(args, "--contact-phone", body.contact_phone);
        appendTextOption(args, "--contact-wechat", body.contact_wechat);
        appendTextOption(args, "--interview-windows", body.interview_windows);
        appendTextOption(args, "--salary-reply-policy", body.salary_reply_policy);
        appendTextOption(
          args,
          "--resume-attachment-path",
          body.resume_attachment_path,
        );
        appendBooleanOption(
          args,
          "--reply-auto-send-enabled",
          "--no-reply-auto-send-enabled",
          body.reply_auto_send_enabled,
        );
        appendBooleanOption(
          args,
          "--outreach-auto-send-enabled",
          "--no-outreach-auto-send-enabled",
          body.outreach_auto_send_enabled,
        );
        appendBooleanOption(
          args,
          "--proactive-resume-enabled",
          "--no-proactive-resume-enabled",
          body.proactive_resume_enabled,
        );
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (
        req.method === "POST" &&
        url.pathname.startsWith("/api/agent/profiles/") &&
        url.pathname.endsWith("/uploads")
      ) {
        const profileId = profileIdFromPath(url.pathname, "/uploads");
        const body = JSON.parse((await readBody(req)) || "{}");
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "upload",
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--profile-id",
          profileId,
          "--type",
          String(body.source_type || "other"),
          "--file",
          String(body.file_path || ""),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (
        req.method === "GET" &&
        url.pathname.startsWith("/api/agent/profiles/") &&
        url.pathname.endsWith("/uploads")
      ) {
        const profileId = profileIdFromPath(url.pathname, "/uploads");
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "profile",
          "upload-status",
          "--profile-id",
          profileId,
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (req.method === "POST" && url.pathname === "/api/agent/profile-binding") {
        const body = JSON.parse((await readBody(req)) || "{}");
        const args = [
          "agent",
          "conversation",
          "bind-profile",
          "--conversation-id",
          String(body.conversation_id || ""),
          "--tenant-id",
          String(body.tenant_id || "tenant_local"),
          "--user-id",
          String(body.user_id || "user_local"),
          "--profile-id",
          String(body.profile_id || ""),
        ];
        appendTextOption(args, "--binding-source", normalizeBindingSource(body.binding_source));
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (req.method === "GET" && url.pathname === "/api/agent/profile-binding") {
        const payload = await runBossJsonCommand(bridgeConfig, [
          "agent",
          "conversation",
          "profile",
          "--conversation-id",
          String(url.searchParams.get("conversation_id") || ""),
        ]);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }

      if (req.method === "GET" && url.pathname === "/api/agent/usage") {
        const args = [
          "agent",
          "usage",
          "summary",
          "--tenant-id",
          String(url.searchParams.get("tenant_id") || "tenant_local"),
        ];
        appendTextOption(args, "--user-id", url.searchParams.get("user_id"));
        appendTextOption(args, "--profile-id", url.searchParams.get("profile_id"));
        const payload = await runBossJsonCommand(bridgeConfig, args);
        sendJson(res, 200, { ok: true, data: responseData(payload) });
        return true;
      }
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        errorMessage:
          error instanceof Error ? error.message : "Profile bridge request failed.",
      });
      return true;
    }
    return false;
  };
}
