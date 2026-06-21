export const bossAccountRiskCode = "ACCOUNT_RISK";
export const watcherRiskLockWindowMs = 10 * 60 * 1000;

const bossLoginRefreshMessage =
  "Boss 登录状态已失效或 token 刷新失败。请回到 BOSS 官方页面确认已登录，再刷新本页面后重试。";
const bossAccountRiskMessage =
  "Boss 账号触发风控，已停止自动化访问。请回到 BOSS 官方页面手动处理，恢复后刷新本页面。";
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

function isFreshWatcherTask(task, nowMs, riskWindowMs) {
  const createdAt = Date.parse(String(task?.created_at || ""));
  if (!Number.isFinite(createdAt)) return true;
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
  const tasks = Array.isArray(watcherState?.tasks) ? watcherState.tasks.slice().reverse() : [];
  const riskyTask = tasks.find((task) => {
    const detail = taskRiskMessage(task);
    return (
      Boolean(detail) &&
      isBossAccountRiskMessage(detail) &&
      isFreshWatcherTask(task, nowMs, riskWindowMs)
    );
  });
  return riskyTask ? taskRiskMessage(riskyTask) : "";
}

export function bossWatcherRiskLockMessage(watcherRiskStatusMessage) {
  return watcherRiskStatusMessage
    ? `Boss 账号当前已被平台限制访问。${watcherRiskStatusMessage} 请回到 BOSS 官方页面手动处理或等待恢复后刷新重试。`
    : "";
}
