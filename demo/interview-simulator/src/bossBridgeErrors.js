export const bossAccountRiskCode = "ACCOUNT_RISK";
export const watcherRiskLockWindowMs = 10 * 60 * 1000;

const bossLoginRefreshMessage =
  "Boss 登录状态已失效或 token 刷新失败。请回到 BOSS 官方页面确认已登录，再刷新本页面后重试。";
const bossAccountRiskMessage =
  "当前 Boss 页面或自动化通道被安全检查拦截，已停止自动化访问。请先在 BOSS 官方页面确认页面可正常访问，恢复后回到本页解除本地锁再重试。";
const bossAuthRecoveryCodes = new Set([
  "AUTH_REQUIRED",
  "AUTH_EXPIRED",
  "TOKEN_REFRESH_FAILED",
]);
const bossAccountRiskTokens = [
  "异常访问",
  "风控",
  "安全验证",
  "访问受限",
  "限制访问",
  "异常行为",
  "禁止使用",
  "403.html",
  "code=32",
];
const bossAuthExpiredTokens = [
  "登录状态已失效",
  "登录态过期",
  "token 刷新失败",
  "stoken",
  "token",
  "未认证",
  "unauthorized",
];

function includesAnyToken(message, tokens) {
  const normalized = String(message || "");
  const lowered = normalized.toLowerCase();
  return tokens.some((token) => {
    const candidate = String(token);
    return normalized.includes(candidate) || lowered.includes(candidate.toLowerCase());
  });
}

export function isBossAccountRiskMessage(message) {
  return includesAnyToken(message, bossAccountRiskTokens);
}

function isBossTokenRefreshMessage(message) {
  return String(message || "").includes("环境存在异常");
}

function isBossAuthExpiredMessage(message) {
  return includesAnyToken(message, bossAuthExpiredTokens);
}

export function inferBossBridgeErrorCodeFromMessage(message) {
  if (isBossAccountRiskMessage(message)) {
    return bossAccountRiskCode;
  }
  if (isBossTokenRefreshMessage(message)) {
    return "TOKEN_REFRESH_FAILED";
  }
  if (isBossAuthExpiredMessage(message)) {
    return "AUTH_EXPIRED";
  }
  return "";
}

export function bossBridgeErrorFromPayload(payload, fallback) {
  const message =
    payload?.errorMessage ||
    payload?.error?.message ||
    fallback;
  const error = new Error(message);
  error.bossCode =
    String(payload?.error?.code || "").trim() ||
    inferBossBridgeErrorCodeFromMessage(message);
  return error;
}

export function bossBridgeErrorCode(error) {
  return error?.bossCode || "";
}

export function bossBridgeErrorMessage(error, fallback) {
  const message = error instanceof Error ? error.message : "";
  const code = bossBridgeErrorCode(error);
  if (code === bossAccountRiskCode || (!code && isBossAccountRiskMessage(message))) {
    return bossAccountRiskMessage;
  }
  if (
    bossAuthRecoveryCodes.has(code) ||
    (!code && (isBossTokenRefreshMessage(message) || isBossAuthExpiredMessage(message)))
  ) {
    return bossLoginRefreshMessage;
  }
  if (message === "Failed to fetch" || message.includes("NetworkError")) {
    return "本地 Vite bridge 无响应。请刷新页面，或确认当前页面打开的是正在运行的 demo/interview-simulator dev server。";
  }
  return message || fallback;
}

function taskRiskMessage(task) {
  return String(task?.error_message || task?.action?.message || "").trim();
}

function taskCreatedAtMs(task) {
  const createdAt = Date.parse(String(task?.created_at || ""));
  return Number.isFinite(createdAt) ? createdAt : null;
}

function isFreshWatcherTask(task, nowMs, riskWindowMs) {
  const createdAt = taskCreatedAtMs(task);
  if (createdAt === null) return true;
  return nowMs - createdAt <= riskWindowMs;
}

export function watcherRiskHint(watcherState, options = {}) {
  const directMessage = String(watcherState?.errorMessage || "").trim();
  if (directMessage && isBossAccountRiskMessage(directMessage)) {
    return directMessage;
  }

  const nowMs = Number.isFinite(options.nowMs) ? options.nowMs : Date.now();
  const riskWindowMs = Number.isFinite(options.riskWindowMs)
    ? options.riskWindowMs
    : watcherRiskLockWindowMs;
  const ignoreBeforeMs = Number.isFinite(options.ignoreBeforeMs)
    ? options.ignoreBeforeMs
    : null;
  const tasks = Array.isArray(watcherState?.tasks) ? watcherState.tasks.slice().reverse() : [];
  const riskyTask = tasks.find((task) => {
    const detail = taskRiskMessage(task);
    const createdAt = taskCreatedAtMs(task);
    const isLocallyAcknowledged =
      ignoreBeforeMs !== null && createdAt !== null && createdAt <= ignoreBeforeMs;
    return (
      Boolean(detail) &&
      isBossAccountRiskMessage(detail) &&
      isFreshWatcherTask(task, nowMs, riskWindowMs) &&
      !isLocallyAcknowledged
    );
  });
  return riskyTask ? taskRiskMessage(riskyTask) : "";
}

export function bossWatcherRiskLockMessage(watcherRiskStatusMessage) {
  return watcherRiskStatusMessage
    ? `当前 Boss 页面或自动化通道被安全检查拦截。${watcherRiskStatusMessage} 请先在 BOSS 官方页面确认页面可正常访问，恢复后回到本页解除本地锁再重试。`
    : "";
}
