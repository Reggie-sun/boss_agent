import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
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

function loadBridgeConfig() {
  const repoRoot = path.resolve(process.cwd(), "..", "..");
  const repoEnv = parseEnvFile(path.join(repoRoot, ".env"));
  const get = (key, fallback = "") =>
    process.env[key] || repoEnv[key] || fallback;

  return {
    repoRoot,
    dataDir: get("BOSS_RAG_DATA_DIR", "~/.boss-agent"),
    pythonBin: get("BOSS_RAG_PYTHON_BIN", get("PYTHON", "python")),
    baseUrl: get("BOSS_RAG_RAG_BASE_URL", "").replace(/\/$/, ""),
    authMode: get("BOSS_RAG_RAG_AUTH_MODE", "none").toLowerCase(),
    apiKey:
      get("BOSS_RAG_RAG_API_KEY") ||
      get("RAG_API_KEY") ||
      get("RAG_AUTH_API_KEY") ||
      "",
  };
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

function normalizeThread(sessionId, messages) {
  const safeMessages = Array.isArray(messages) ? messages : [];
  return {
    sessionId,
    turnCount: safeMessages.filter((item) => item.role === "user").length,
    messageCount: safeMessages.length,
    messages: safeMessages,
  };
}

function runBossJsonCommand(config, args) {
  const child = spawnSync(
    config.pythonBin,
    [
      "-c",
      "from boss_agent_cli.main import cli; import sys; cli.main(args=sys.argv[1:], standalone_mode=False)",
      "--json",
      "--data-dir",
      config.dataDir,
      ...args,
    ],
    {
      cwd: config.repoRoot,
      encoding: "utf8",
      env: {
        ...process.env,
        PYTHONPATH: process.env.PYTHONPATH
          ? `${config.repoRoot}/src:${process.env.PYTHONPATH}`
          : `${config.repoRoot}/src`,
      },
    },
  );

  if (child.error) {
    throw child.error;
  }
  if (child.status !== 0 && !child.stdout.trim()) {
    throw new Error(child.stderr.trim() || `boss command failed with exit code ${child.status}`);
  }

  let parsed = {};
  try {
    parsed = child.stdout.trim() ? JSON.parse(child.stdout) : {};
  } catch (error) {
    throw new Error(
      `无法解析 boss-agent-cli 输出: ${child.stdout.trim() || child.stderr.trim() || String(error)}`,
    );
  }

  if (!parsed.ok) {
    const errorMessage =
      parsed.error?.message ||
      parsed.errorMessage ||
      child.stderr.trim() ||
      "boss-agent-cli 返回错误。";
    const commandError = new Error(errorMessage);
    commandError.commandPayload = parsed;
    throw commandError;
  }
  return parsed;
}

function createRagBridgePlugin() {
  const bridgeConfig = loadBridgeConfig();

  async function handler(req, res) {
    if (!req.url) return false;

    if (req.method === "GET" && req.url === "/api/rag/health") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        runBossJsonCommand(bridgeConfig, ["rag", "init"]);
        const ready =
          Boolean(bridgeConfig.baseUrl) &&
          (bridgeConfig.authMode === "none" || Boolean(bridgeConfig.apiKey));
        res.end(
          JSON.stringify({
            configured: Boolean(bridgeConfig.baseUrl),
            ready,
            authMode: bridgeConfig.authMode || "none",
            endpoint: "/api/rag/ask",
            workflow: "boss-agent-cli",
            dataDir: bridgeConfig.dataDir,
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
            endpoint: "/api/rag/ask",
            workflow: "boss-agent-cli",
            dataDir: bridgeConfig.dataDir,
            errorMessage:
              error instanceof Error ? error.message : "本地 workflow 初始化失败。",
          }),
        );
      }
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
      try {
        const payload = runBossJsonCommand(bridgeConfig, [
          "rag",
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

        const payload = runBossJsonCommand(bridgeConfig, args);
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

        if (!query) {
          res.statusCode = 400;
          res.end(JSON.stringify({ ok: false, errorMessage: "query 不能为空。" }));
          return true;
        }

        const args = ["search", query];
        if (city) args.push("--city", city);

        const payload = runBossJsonCommand(bridgeConfig, args);
        res.end(JSON.stringify({
          ok: true,
          data: payload.data,
        }));
      } catch (error) {
        const p = error?.commandPayload;
        res.statusCode = 500;
        res.end(JSON.stringify({
          ok: false,
          errorMessage: error instanceof Error ? error.message : "搜索失败",
          error: p?.error || null,
        }));
      }
      return true;
    }

    // ── Boss Resume List API ──────────────────────────────────────
    if (req.method === "GET" && req.url === "/api/boss/resumes") {
      res.setHeader("Content-Type", "application/json; charset=utf-8");
      try {
        const payload = runBossJsonCommand(bridgeConfig, ["resume", "list"]);
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

    if (req.method !== "POST" || req.url !== "/api/rag/ask") return false;

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

      if (!question) {
        res.statusCode = 400;
        res.end(JSON.stringify({ ok: false, errorMessage: "question 不能为空。" }));
        return true;
      }

      const payload = runBossJsonCommand(bridgeConfig, [
        "rag",
        "ask",
        "--conversation-id",
        sessionId,
        "--question",
        question,
      ]);
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
          rawResponse: {
            command: payload.command,
            conversationId: data.conversation_id,
            draft,
            question,
          },
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
