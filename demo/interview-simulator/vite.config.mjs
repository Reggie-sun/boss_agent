import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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

function loadRagConfig() {
  const repoRoot = path.resolve(process.cwd(), "..", "..");
  const repoEnv = parseEnvFile(path.join(repoRoot, ".env"));
  const get = (key, fallback = "") =>
    process.env[key] || repoEnv[key] || fallback;

  return {
    baseUrl: get("BOSS_RAG_RAG_BASE_URL", "").replace(/\/$/, ""),
    authMode: get("BOSS_RAG_RAG_AUTH_MODE", "none").toLowerCase(),
    apiKey:
      get("BOSS_RAG_RAG_API_KEY") ||
      get("RAG_API_KEY") ||
      get("RAG_AUTH_API_KEY") ||
      "",
  };
}

function buildHeaders(config) {
  if (!config.authMode || config.authMode === "none") return {};
  if (config.authMode === "x_api_key") {
    return config.apiKey ? { "X-API-Key": config.apiKey } : {};
  }
  if (config.authMode === "bearer") {
    return config.apiKey ? { Authorization: `Bearer ${config.apiKey}` } : {};
  }
  return {};
}

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

function createRagBridgePlugin() {
  const ragConfig = loadRagConfig();
  const sessionThreads = new Map();

  function getThread(sessionId) {
    const existing = sessionThreads.get(sessionId);
    if (existing) return existing;
    const created = [];
    sessionThreads.set(sessionId, created);
    return created;
  }

  function serializeThread(sessionId) {
    const messages = getThread(sessionId).slice(-24);
    return {
      sessionId,
      turnCount: messages.filter((item) => item.role === "user").length,
      messageCount: messages.length,
      messages,
    };
  }

  async function handler(req, res) {
    if (!req.url) return false;

    if (req.method === "GET" && req.url === "/api/rag/health") {
      const ready =
        Boolean(ragConfig.baseUrl) &&
        (ragConfig.authMode === "none" || Boolean(buildHeaders(ragConfig)));
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      res.end(
        JSON.stringify({
          configured: Boolean(ragConfig.baseUrl),
          ready,
          authMode: ragConfig.authMode || "none",
          endpoint: "/api/rag/ask",
          errorMessage: ragConfig.baseUrl
            ? ""
            : "未找到 BOSS_RAG_RAG_BASE_URL，无法把前端请求转发给 Enterprise RAG。",
        }),
      );
      return true;
    }

    if (req.method === "GET" && req.url.startsWith("/api/rag/thread")) {
      const requestUrl = new URL(req.url, "http://127.0.0.1");
      const sessionId = String(requestUrl.searchParams.get("sessionId") || "").trim();
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      if (!sessionId) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, errorMessage: "sessionId 不能为空。" }));
        return true;
      }
      res.end(
        JSON.stringify({
          ok: true,
          thread: serializeThread(sessionId),
        }),
      );
      return true;
    }

    if (req.method !== "POST" || req.url !== "/api/rag/ask") return false;

    res.setHeader("Content-Type", "application/json; charset=utf-8");

    if (!ragConfig.baseUrl) {
      res.statusCode = 500;
      res.end(
        JSON.stringify({
          ok: false,
          errorMessage:
            "BOSS_RAG_RAG_BASE_URL 未配置，无法调用 Enterprise RAG。",
        }),
      );
      return true;
    }

    try {
      const rawBody = await readBody(req);
      const parsed = rawBody ? JSON.parse(rawBody) : {};
      const question = String(parsed.question || "").trim();
      const sessionId = String(parsed.sessionId || "").trim() || `session-${Date.now()}`;
      const mode = String(parsed.mode || "accurate");
      const thread = getThread(sessionId);

      if (!question) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, errorMessage: "question 不能为空。" }));
        return true;
      }

      thread.push({
        id: `user-${Date.now()}`,
        role: "user",
        content: question,
        source: "frontend_prompt",
        createdAt: new Date().toISOString(),
      });

      const upstream = await fetch(`${ragConfig.baseUrl}/api/v1/chat/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...buildHeaders(ragConfig),
        },
        body: JSON.stringify({
          question,
          session_id: sessionId,
          mode,
        }),
      });

      const text = await upstream.text();
      let payload = {};
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        payload = { answer: text };
      }

      if (!upstream.ok) {
        res.statusCode = upstream.status;
        thread.push({
          id: `error-${Date.now()}`,
          role: "assistant",
          content:
            payload.error?.message ||
            payload.message ||
            `上游 RAG 返回 HTTP ${upstream.status}`,
          source: "rag_error",
          createdAt: new Date().toISOString(),
        });
        res.end(
          JSON.stringify({
            ok: false,
            errorMessage:
              payload.error?.message ||
              payload.message ||
              `上游 RAG 返回 HTTP ${upstream.status}`,
            thread: serializeThread(sessionId),
          }),
        );
        return true;
      }

      thread.push({
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: String(payload.answer || ""),
        source: "enterprise_rag",
        createdAt: new Date().toISOString(),
      });

      res.end(
        JSON.stringify({
          ok: true,
          answer: String(payload.answer || ""),
          citations: Array.isArray(payload.citations) ? payload.citations : [],
          reasoningSummary:
            payload.reasoning_summary && typeof payload.reasoning_summary === "object"
              ? payload.reasoning_summary
              : null,
          auditStatus: "answered",
          rawResponse: payload,
          thread: serializeThread(sessionId),
        }),
      );
      return true;
    } catch (error) {
      res.statusCode = 500;
      res.end(
        JSON.stringify({
          ok: false,
          errorMessage:
            error instanceof Error ? error.message : "本地 RAG 代理调用失败。",
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
