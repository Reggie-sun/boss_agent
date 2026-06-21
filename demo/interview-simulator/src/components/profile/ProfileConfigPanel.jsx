import { FloppyDisk, ShieldCheck } from "@phosphor-icons/react";

export function ProfileConfigPanel({
  selectedProfile,
  config,
  saving,
  statusMessage,
  errorMessage,
  onChange,
  onSave,
}) {
  const disabled = !selectedProfile || saving;

  function update(field, value) {
    onChange({ ...config, [field]: value });
  }

  return (
    <section className="profile-config-panel">
      <div className="profile-section-head">
        <div>
          <span>Profile Gates</span>
          <strong>{selectedProfile ? "自动化边界" : "请选择 profile"}</strong>
        </div>
        <ShieldCheck size={18} weight="fill" />
      </div>

      <div className="profile-config-grid">
        <label>
          <span>手机号</span>
          <input
            value={config.contact_phone || ""}
            onChange={(event) => update("contact_phone", event.target.value)}
            disabled={disabled}
            placeholder="用于 contact_exchange"
          />
        </label>
        <label>
          <span>微信号</span>
          <input
            value={config.contact_wechat || ""}
            onChange={(event) => update("contact_wechat", event.target.value)}
            disabled={disabled}
            placeholder="用于 contact_exchange"
          />
        </label>
        <label className="profile-config-grid__wide">
          <span>可面试时间</span>
          <input
            value={config.interview_windows || ""}
            onChange={(event) => update("interview_windows", event.target.value)}
            disabled={disabled}
            placeholder="例如：工作日 20:00 后"
          />
        </label>
        <label className="profile-config-grid__wide">
          <span>薪资回复策略</span>
          <input
            value={config.salary_reply_policy || ""}
            onChange={(event) => update("salary_reply_policy", event.target.value)}
            disabled={disabled}
            placeholder="缺失时薪资意图会阻断"
          />
        </label>
        <label className="profile-config-grid__wide">
          <span>简历 PDF 路径</span>
          <input
            value={config.resume_attachment_path || ""}
            onChange={(event) => update("resume_attachment_path", event.target.value)}
            disabled={disabled}
            placeholder="/path/to/resume.pdf"
          />
        </label>
      </div>

      <div className="profile-toggle-list">
        <label className="profile-toggle">
          <input
            type="checkbox"
            checked={Boolean(config.reply_auto_send_enabled)}
            onChange={(event) => update("reply_auto_send_enabled", event.target.checked)}
            disabled={disabled}
          />
          <span>允许 watcher 回复自动发送</span>
        </label>
        <label className="profile-toggle">
          <input
            type="checkbox"
            checked={Boolean(config.outreach_auto_send_enabled)}
            onChange={(event) => update("outreach_auto_send_enabled", event.target.checked)}
            disabled={disabled}
          />
          <span>允许 Boss 自动开聊</span>
        </label>
        <label className="profile-toggle">
          <input
            type="checkbox"
            checked={Boolean(config.proactive_resume_enabled)}
            onChange={(event) => update("proactive_resume_enabled", event.target.checked)}
            disabled={disabled}
          />
          <span>允许主动附加简历</span>
        </label>
      </div>

      {errorMessage ? <p className="profile-error">{errorMessage}</p> : null}
      {statusMessage ? <p className="profile-status">{statusMessage}</p> : null}

      <button
        type="button"
        className="inline-action inline-action--primary profile-save-button"
        onClick={onSave}
        disabled={disabled}
      >
        <FloppyDisk size={16} weight="fill" />
        {saving ? "保存中..." : "保存 profile gate"}
      </button>
    </section>
  );
}
