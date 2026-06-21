function query(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) {
      search.set(key, String(value));
    }
  });
  const value = search.toString();
  return value ? `?${value}` : "";
}

async function requestJson(path, options = {}) {
  const init = { method: options.method || "GET" };
  if (options.body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.errorMessage || `Request failed: ${path}`);
  }
  return payload.data === undefined ? payload : payload.data;
}

export async function fetchProfiles({ tenantId, userId }) {
  return requestJson(
    `/api/agent/profiles${query({ tenant_id: tenantId, user_id: userId })}`,
  );
}

export async function createProfile(payload) {
  return requestJson("/api/agent/profiles", { method: "POST", body: payload });
}

export async function fetchProfileConfig(profileId) {
  return requestJson(
    `/api/agent/profiles/${encodeURIComponent(profileId)}/config`,
  );
}

export async function updateProfileConfig(profileId, payload) {
  return requestJson(
    `/api/agent/profiles/${encodeURIComponent(profileId)}/config`,
    { method: "PATCH", body: payload },
  );
}

export async function fetchProfileUploads(profileId) {
  return requestJson(
    `/api/agent/profiles/${encodeURIComponent(profileId)}/uploads`,
  );
}

export async function bindConversationProfile(payload) {
  return requestJson("/api/agent/profile-binding", {
    method: "POST",
    body: payload,
  });
}

export async function fetchConversationProfile(conversationId) {
  return requestJson(
    `/api/agent/profile-binding${query({ conversation_id: conversationId })}`,
  );
}

export async function fetchUsage(params) {
  return requestJson(`/api/agent/usage${query(params)}`);
}

export async function askAgent(payload) {
  return requestJson("/api/agent/ask", { method: "POST", body: payload });
}

export async function sendAgentDraft(payload) {
  return requestJson("/api/agent/send", { method: "POST", body: payload });
}

export async function fetchWatcherStatus() {
  return requestJson("/api/agent/watcher/status");
}

export async function runWatcherOnce(payload) {
  return requestJson("/api/agent/watcher/run", {
    method: "POST",
    body: payload || {},
  });
}

export async function searchBoss(payload) {
  return requestJson("/api/boss/search", { method: "POST", body: payload });
}

export async function autoGreetBoss(payload) {
  return requestJson("/api/boss/auto-greet", { method: "POST", body: payload });
}
