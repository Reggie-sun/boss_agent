export const bossAccountRiskCode = "ACCOUNT_RISK";

const bossLoginRefreshMessage =
  "Boss 登录状态已失效或 token 刷新失败。请回到 BOSS 官方页面确认已登录，再刷新本页面后重试。";
const bossAccountRiskMessage =
  "Boss 账号触发风控，已停止自动化访问。请回到 BOSS 官方页面手动处理，恢复后刷新本页面。";
const bossAuthRecoveryCodes = new Set([
  "AUTH_REQUIRED",
  "AUTH_EXPIRED",
  "TOKEN_REFRESH_FAILED",
]);
const bossAccountRiskTokens = ["异常访问", "风控", "安全验证"];
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
