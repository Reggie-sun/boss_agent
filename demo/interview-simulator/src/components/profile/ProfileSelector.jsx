import { ArrowClockwise, CheckCircle, User } from "@phosphor-icons/react";

export function ProfileSelector({
  profiles,
  selectedProfileId,
  loading,
  errorMessage,
  onRefresh,
  onSelectProfile,
}) {
  return (
    <section className="profile-selector">
      <div className="profile-section-head">
        <div>
          <span>Commercial Profile</span>
          <strong>{profiles.length ? `${profiles.length} 个 profile` : "尚未创建"}</strong>
        </div>
        <button
          type="button"
          className="icon-action"
          onClick={onRefresh}
          disabled={loading}
          title="刷新 profile"
        >
          <ArrowClockwise size={16} />
        </button>
      </div>

      {errorMessage ? (
        <p className="profile-error">{errorMessage}</p>
      ) : null}

      <div className="profile-list">
        {profiles.length ? (
          profiles.map((profile) => {
            const profileId = String(profile.profile_id || "");
            const selected = profileId === selectedProfileId;
            return (
              <button
                key={profileId}
                type="button"
                className={`profile-list-item ${selected ? "is-selected" : ""}`}
                onClick={() => onSelectProfile(profileId)}
              >
                <span className="profile-list-item__icon">
                  {selected ? <CheckCircle size={17} weight="fill" /> : <User size={17} />}
                </span>
                <span className="profile-list-item__body">
                  <strong>{profile.display_name || profile.name || "未命名 profile"}</strong>
                  <em>{profile.target_title || profile.knowledge_base_id || profileId}</em>
                </span>
              </button>
            );
          })
        ) : (
          <p className="profile-empty">
            {loading ? "正在读取 profile..." : "创建一个商业 profile 后再绑定问答和开聊。"}
          </p>
        )}
      </div>
    </section>
  );
}
