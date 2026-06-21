import { useEffect, useMemo, useState } from "react";
import { LinkSimple, PlusCircle, TrendUp } from "@phosphor-icons/react";
import {
  bindConversationProfile,
  createProfile,
  fetchProfileConfig,
  fetchProfiles,
  fetchUsage,
  updateProfileConfig,
} from "../api/agentClient.js";
import { ProfileConfigPanel } from "../components/profile/ProfileConfigPanel.jsx";
import { ProfileSelector } from "../components/profile/ProfileSelector.jsx";

const emptyConfig = {
  contact_phone: "",
  contact_wechat: "",
  interview_windows: "",
  salary_reply_policy: "",
  resume_attachment_path: "",
  reply_auto_send_enabled: false,
  outreach_auto_send_enabled: false,
  proactive_resume_enabled: false,
};

export function ProfileHub({
  tenantId,
  userId,
  selectedProfileId,
  onSelectProfile,
  selectedChatTarget,
}) {
  const [profiles, setProfiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [binding, setBinding] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [configDraft, setConfigDraft] = useState(emptyConfig);
  const [usageSummary, setUsageSummary] = useState([]);
  const [newProfile, setNewProfile] = useState({
    name: "AI 应用工程师",
    target_title: "AI Application Engineer",
    knowledge_base_id: "",
  });

  const selectedProfile = useMemo(
    () =>
      profiles.find(
        (profile) => String(profile.profile_id || "") === selectedProfileId,
      ) || null,
    [profiles, selectedProfileId],
  );

  async function loadProfiles() {
    setLoading(true);
    setErrorMessage("");
    try {
      const data = await fetchProfiles({ tenantId, userId });
      const nextProfiles = Array.isArray(data.profiles) ? data.profiles : [];
      setProfiles(nextProfiles);
      if (!selectedProfileId && nextProfiles.length) {
        onSelectProfile(String(nextProfiles[0].profile_id || ""));
      }
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "读取 profile 失败。");
    } finally {
      setLoading(false);
    }
  }

  async function loadSelectedProfileConfig(profileId) {
    if (!profileId) {
      setConfigDraft(emptyConfig);
      setUsageSummary([]);
      return;
    }
    try {
      const [configData, usageData] = await Promise.all([
        fetchProfileConfig(profileId).catch(() => ({ config: emptyConfig })),
        fetchUsage({ tenant_id: tenantId, user_id: userId, profile_id: profileId }).catch(() => ({
          usage: [],
        })),
      ]);
      setConfigDraft({
        ...emptyConfig,
        ...(configData.config || {}),
      });
      setUsageSummary(Array.isArray(usageData.usage) ? usageData.usage : []);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "读取 profile 配置失败。");
    }
  }

  async function handleCreateProfile() {
    if (!newProfile.name.trim() || saving) return;
    setSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const data = await createProfile({
        tenant_id: tenantId,
        user_id: userId,
        name: newProfile.name,
        target_title: newProfile.target_title,
        knowledge_base_id: newProfile.knowledge_base_id,
      });
      await loadProfiles();
      const profileId = String(data.profile?.profile_id || "");
      if (profileId) onSelectProfile(profileId);
      setStatusMessage("Profile 已创建。");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "创建 profile 失败。");
    } finally {
      setSaving(false);
    }
  }

  async function handleSaveConfig() {
    if (!selectedProfileId || saving) return;
    setSaving(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      const data = await updateProfileConfig(selectedProfileId, {
        tenant_id: tenantId,
        ...configDraft,
      });
      setConfigDraft({
        ...emptyConfig,
        ...(data.config || {}),
      });
      setStatusMessage("Profile gate 已保存。");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "保存 profile gate 失败。");
    } finally {
      setSaving(false);
    }
  }

  async function handleBindCurrentConversation() {
    const conversationId = String(selectedChatTarget?.conversation_id || "").trim();
    if (!selectedProfileId || !conversationId || binding) return;
    setBinding(true);
    setErrorMessage("");
    setStatusMessage("");
    try {
      await bindConversationProfile({
        tenant_id: tenantId,
        user_id: userId,
        conversation_id: conversationId,
        profile_id: selectedProfileId,
        binding_source: "frontend_profile_hub",
      });
      setStatusMessage("当前 Boss 对话已绑定 profile。");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "绑定对话 profile 失败。");
    } finally {
      setBinding(false);
    }
  }

  useEffect(() => {
    loadProfiles();
  }, [tenantId, userId]);

  useEffect(() => {
    loadSelectedProfileConfig(selectedProfileId);
  }, [selectedProfileId, tenantId, userId]);

  return (
    <section className="session-card profile-hub">
      <div className="session-card__header">
        <span>Profile Hub</span>
        <span>{selectedProfile ? selectedProfile.profile_id : "未选择"}</span>
      </div>

      <ProfileSelector
        profiles={profiles}
        selectedProfileId={selectedProfileId}
        loading={loading}
        errorMessage={errorMessage}
        onRefresh={loadProfiles}
        onSelectProfile={onSelectProfile}
      />

      <div className="profile-create-row">
        <input
          value={newProfile.name}
          onChange={(event) =>
            setNewProfile((current) => ({ ...current, name: event.target.value }))
          }
          placeholder="profile 名称"
        />
        <input
          value={newProfile.target_title}
          onChange={(event) =>
            setNewProfile((current) => ({
              ...current,
              target_title: event.target.value,
            }))
          }
          placeholder="目标岗位"
        />
        <input
          value={newProfile.knowledge_base_id}
          onChange={(event) =>
            setNewProfile((current) => ({
              ...current,
              knowledge_base_id: event.target.value,
            }))
          }
          placeholder="knowledge_base_id"
        />
        <button
          type="button"
          className="inline-action"
          onClick={handleCreateProfile}
          disabled={saving || !newProfile.name.trim()}
        >
          <PlusCircle size={16} />
          创建 profile
        </button>
      </div>

      <ProfileConfigPanel
        selectedProfile={selectedProfile}
        config={configDraft}
        saving={saving}
        statusMessage={statusMessage}
        errorMessage=""
        onChange={setConfigDraft}
        onSave={handleSaveConfig}
      />

      <div className="profile-bridge-actions">
        <button
          type="button"
          className="inline-action"
          onClick={handleBindCurrentConversation}
          disabled={
            binding ||
            !selectedProfileId ||
            !String(selectedChatTarget?.conversation_id || "").trim()
          }
        >
          <LinkSimple size={16} />
          {binding ? "绑定中..." : "绑定当前对话"}
        </button>
        <div className="profile-usage-pill">
          <TrendUp size={16} />
          <span>{usageSummary.length ? `${usageSummary.length} 条 usage` : "暂无 usage"}</span>
        </div>
      </div>
    </section>
  );
}
