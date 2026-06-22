import {
  CheckCircle,
  Lightning,
  MagnifyingGlass,
  PaperPlaneTilt,
  WarningCircle,
} from "@phosphor-icons/react";

export function OutreachWorkspace({
  applyMode,
  setApplyMode,
  bossSearchForm,
  updateBossSearchForm,
  bossCityOptions,
  bossSalaryOptions,
  bossExperienceOptions,
  bossEducationOptions,
  bossIndustryOptions,
  bossScaleOptions,
  bossStageOptions,
  bossJobTypeOptions,
  bossExperienceSummary,
  selectedBossExperiences,
  toggleBossExperience,
  isBossSearching,
  bossSearchActionsDisabled,
  handleBossSearchPreview,
  bossAgentPlan,
  isBossAgentPlanning,
  bossAgentPlanError,
  handleBossAgentPlan,
  isBossAutoRunning,
  handleBossAutoGreet,
  bossAutoButtonLabel,
  selectedProfileId,
  bossAutomationRiskLocked,
  bossAutomationError,
  onClearBossAutomationRisk,
  bossAutomationProgress,
  bossAutomationIsGreeting,
  bossAutomationProgressCurrent,
  bossAutomationProgressTotal,
  bossAutomationResult,
  bossAutomationHasIssue,
  bossAutomationFailedItems,
  normalizedBossJobs,
  applyForm,
  setApplyForm,
  setSelectedTargetValue,
  chatTargets,
  selectedTargetValue,
  handleTargetSelection,
  selectedChatTarget,
}) {
  return (
    <section className="apply-panel apply-panel--inline">
      <div className="apply-panel__header" onClick={() => setApplyMode((m) => !m)}>
        <div className="apply-panel__title-row">
          <Lightning size={22} weight="bold" />
          <h2>Boss 自动开聊</h2>
        </div>
        <span className="apply-panel__toggle">{applyMode ? "收起 ▲" : "展开 ▼"}</span>
      </div>

      {applyMode && (
        <div className="apply-panel__body">
          <div className="profile-route-notice">
            <strong>{selectedProfileId ? "Profile gate 已选择" : "请选择 commercial profile"}</strong>
            <span>
              {selectedProfileId
                ? `当前自动开聊会携带 profile_id=${selectedProfileId}`
                : "未选择 profile 时，Agent 全自动会被本地 gate 阻断。"}
            </span>
          </div>

          <div className="apply-search__inputs">
            <input
              className="apply-input"
              placeholder="关键词"
              value={bossSearchForm.query}
              onChange={(event) => updateBossSearchForm("query", event.target.value)}
            />
            <select
              className="apply-input apply-input--city"
              value={bossSearchForm.city}
              onChange={(event) => updateBossSearchForm("city", event.target.value)}
            >
              {bossCityOptions.map((city) => (
                <option key={city} value={city}>{city}</option>
              ))}
            </select>
            <select
              className="apply-input apply-input--salary"
              value={bossSearchForm.salary}
              onChange={(event) => updateBossSearchForm("salary", event.target.value)}
            >
              {bossSalaryOptions.map((salary) => (
                <option key={salary || "none"} value={salary}>
                  {salary || "薪资不限"}
                </option>
              ))}
            </select>
            <details className="apply-multi-select apply-input--experience">
              <summary className="apply-multi-select__summary">
                <span>{bossExperienceSummary}</span>
              </summary>
              <div className="apply-multi-select__menu">
                <label className="apply-multi-select__option">
                  <input
                    type="checkbox"
                    checked={selectedBossExperiences.length === 0}
                    onChange={() => toggleBossExperience("")}
                  />
                  <span>经验不限</span>
                </label>
                {bossExperienceOptions.filter(Boolean).map((experience) => (
                  <label className="apply-multi-select__option" key={experience}>
                    <input
                      type="checkbox"
                      checked={selectedBossExperiences.includes(experience)}
                      onChange={() => toggleBossExperience(experience)}
                    />
                    <span>{experience}</span>
                  </label>
                ))}
              </div>
            </details>
            <select
              className="apply-input apply-input--education"
              value={bossSearchForm.education}
              onChange={(event) => updateBossSearchForm("education", event.target.value)}
            >
              {bossEducationOptions.map((education) => (
                <option key={education || "none"} value={education}>
                  {education || "学历不限"}
                </option>
              ))}
            </select>
            <select
              className="apply-input apply-input--industry"
              value={bossSearchForm.industry}
              onChange={(event) => updateBossSearchForm("industry", event.target.value)}
            >
              {bossIndustryOptions.map((industry) => (
                <option key={industry || "none"} value={industry}>
                  {industry || "行业不限"}
                </option>
              ))}
            </select>
            <select
              className="apply-input apply-input--scale"
              value={bossSearchForm.scale}
              onChange={(event) => updateBossSearchForm("scale", event.target.value)}
            >
              {bossScaleOptions.map((scale) => (
                <option key={scale || "none"} value={scale}>
                  {scale || "规模不限"}
                </option>
              ))}
            </select>
            <select
              className="apply-input apply-input--stage"
              value={bossSearchForm.stage}
              onChange={(event) => updateBossSearchForm("stage", event.target.value)}
            >
              {bossStageOptions.map((stage) => (
                <option key={stage || "none"} value={stage}>
                  {stage || "融资不限"}
                </option>
              ))}
            </select>
            <select
              className="apply-input apply-input--job-type"
              value={bossSearchForm.jobType}
              onChange={(event) => updateBossSearchForm("jobType", event.target.value)}
            >
              {bossJobTypeOptions.map((jobType) => (
                <option key={jobType || "none"} value={jobType}>
                  {jobType || "类型不限"}
                </option>
              ))}
            </select>
            <input
              className="apply-input apply-input--welfare"
              placeholder="福利关键词"
              value={bossSearchForm.welfare}
              onChange={(event) => updateBossSearchForm("welfare", event.target.value)}
            />
            <input
              className="apply-input apply-input--attachments"
              placeholder="附件路径，逗号或换行分隔"
              value={bossSearchForm.attachments}
              onChange={(event) => updateBossSearchForm("attachments", event.target.value)}
            />
            <select
              className="apply-input apply-input--count"
              value={bossSearchForm.count}
              onChange={(event) => updateBossSearchForm("count", event.target.value)}
            >
              {["1", "2", "3", "5", "10", "20", "50", "100", "150"].map((count) => (
                <option key={count} value={count}>{count} 个</option>
              ))}
            </select>
            <button
              type="button"
              className="apply-btn apply-btn--search"
              onClick={handleBossSearchPreview}
              disabled={isBossSearching || bossSearchActionsDisabled}
            >
              <MagnifyingGlass size={16} />
              {isBossSearching ? "搜索中..." : "预览"}
            </button>
            <button
              type="button"
              className="apply-btn apply-btn--search"
              onClick={handleBossAgentPlan}
              disabled={isBossAgentPlanning || bossSearchActionsDisabled || !selectedProfileId}
            >
              <Lightning size={16} weight="fill" />
              {isBossAgentPlanning ? "规划中..." : "生成 Agent 计划"}
            </button>
            <button
              type="button"
              className="apply-btn apply-btn--send apply-btn--compact"
              onClick={handleBossAutoGreet}
              disabled={isBossAutoRunning || bossSearchActionsDisabled || !selectedProfileId}
            >
              <PaperPlaneTilt size={16} weight="fill" />
              {bossAutoButtonLabel}
            </button>
          </div>

          {bossAutomationError ? (
            <div className="apply-result apply-result--error">
              <WarningCircle size={18} weight="fill" />
              <span>{bossAutomationError}</span>
              {bossAutomationRiskLocked ? (
                <button
                  type="button"
                  className="apply-result__action"
                  onClick={onClearBossAutomationRisk}
                >
                  已处理，解除本地锁
                </button>
              ) : null}
            </div>
          ) : null}

          {isBossAutoRunning ? (
            <div className="apply-result apply-result--pending">
              <Lightning size={18} weight="fill" />
              <div className="apply-result__content">
                <span>
                  {bossAutomationIsGreeting
                    ? `正在和第 ${bossAutomationProgressCurrent}${bossAutomationProgressTotal ? ` / ${bossAutomationProgressTotal}` : ""} 个候选开聊`
                    : bossAutomationProgress?.message || "正在搜索可开聊候选，还没有开始聊天。"}
                </span>
                {bossAutomationIsGreeting &&
                (bossAutomationProgress?.title || bossAutomationProgress?.company) ? (
                  <span className="apply-result__detail">
                    {[bossAutomationProgress.title, bossAutomationProgress.company]
                      .filter(Boolean)
                      .join(" @ ")}
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}

          {bossAgentPlanError ? (
            <div className="apply-result apply-result--error">
              <WarningCircle size={18} weight="fill" />
              <span>{bossAgentPlanError}</span>
            </div>
          ) : null}

          {bossAgentPlan ? (
            <div className="agent-plan-panel">
              <div className="agent-plan-panel__header">
                <strong>Agent 计划</strong>
                <span>
                  {bossAgentPlan.status} · {bossAgentPlan.total || 0} 个候选 ·{" "}
                  {bossAgentPlan.send_ready ? "可执行" : "需确认"}
                </span>
              </div>
              <div className="agent-plan-list">
                {(bossAgentPlan.actions || []).slice(0, 5).map((action, index) => {
                  const candidate = action.candidate || {};
                  const label =
                    [candidate.title, candidate.company].filter(Boolean).join(" @ ") ||
                    candidate.security_id ||
                    `候选 ${index + 1}`;
                  return (
                    <article className="agent-plan-card" key={`${candidate.security_id || label}-${index}`}>
                      <div className="agent-plan-card__topline">
                        <strong>{label}</strong>
                        <span>{action.decision}</span>
                      </div>
                      <p>
                        score {action.score} · risk {action.risk}
                      </p>
                      <div className="agent-plan-card__reasons">
                        {(action.reasons || []).map((reason) => (
                          <span key={reason}>{reason}</span>
                        ))}
                      </div>
                    </article>
                  );
                })}
              </div>
            </div>
          ) : null}

          {bossAutomationResult ? (
            <div
              className={`apply-result ${bossAutomationHasIssue ? "apply-result--error" : "apply-result--ok"}`}
            >
              {bossAutomationHasIssue ? (
                <WarningCircle size={18} weight="fill" />
              ) : (
                <CheckCircle size={18} weight="fill" />
              )}
              <div className="apply-result__content">
                <span>
                  已开聊 {bossAutomationResult.total_greeted || 0} 个， 失败{" "}
                  {bossAutomationResult.total_failed || 0} 个
                  {bossAutomationResult.stopped_reason
                    ? `，停止原因：${bossAutomationResult.stopped_reason}`
                    : ""}
                </span>
                {bossAutomationResult.stopped_error ? (
                  <span className="apply-result__detail">
                    {bossAutomationResult.stopped_error}
                  </span>
                ) : null}
                {bossAutomationFailedItems.length ? (
                  <ul className="apply-result__failure-list">
                    {bossAutomationFailedItems.slice(0, 4).map((item, index) => {
                      const label =
                        [item?.title, item?.company].filter(Boolean).join(" @ ") ||
                        item?.security_id ||
                        `候选 ${index + 1}`;
                      return (
                        <li key={`${item?.security_id || item?.job_id || label}-${index}`}>
                          {label}：{item?.error || "未知失败"}
                        </li>
                      );
                    })}
                    {bossAutomationFailedItems.length > 4 ? (
                      <li>还有 {bossAutomationFailedItems.length - 4} 个失败项</li>
                    ) : null}
                  </ul>
                ) : null}
              </div>
            </div>
          ) : null}

          {normalizedBossJobs.length ? (
            <div className="apply-job-list">
              {normalizedBossJobs.slice(0, 6).map((job, index) => (
                <button
                  type="button"
                  className="apply-job-item"
                  key={`${job.security_id || job.job_id}-${index}`}
                  onClick={() => {
                    if (job.security_id) {
                      setApplyForm({ security_id: job.security_id });
                      setSelectedTargetValue("");
                    }
                  }}
                >
                  <span className="apply-job-item__main">
                    <strong>{job.title}</strong>
                    <span>{job.company}</span>
                  </span>
                  <span className="apply-job-item__meta">
                    {[job.city, job.salary, job.experience].filter(Boolean).join(" · ")}
                  </span>
                </button>
              ))}
            </div>
          ) : null}

          <div className="apply-form">
            {chatTargets.length ? (
              <div className="apply-form__row">
                <div className="apply-field">
                  <label>对话发送目标</label>
                  <select
                    className="apply-input"
                    value={selectedTargetValue}
                    onChange={(event) => handleTargetSelection(event.target.value)}
                  >
                    <option value="">选择已回复的 Boss 对话目标</option>
                    {chatTargets.map((target, index) => (
                      <option
                        key={`${String(target.conversation_id || target.security_id || "")}-${index}`}
                        value={String(target.conversation_id || target.security_id || "")}
                      >
                        {`${target.company || "未知公司"} · ${target.recruiter_name || "未命名 HR"} · ${target.title || "未知职位"}`}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            ) : null}

            {selectedChatTarget ? (
              <div className="apply-result apply-result--ok">
                <CheckCircle size={18} weight="fill" />
                <span>
                  已选对话目标：{selectedChatTarget.company || "未知公司"} /{" "}
                  {selectedChatTarget.recruiter_name || "未命名 HR"} /{" "}
                  {selectedChatTarget.security_id || "无 security_id"}
                </span>
              </div>
            ) : null}

            <div className="apply-form__row">
              <div className="apply-field">
                <label>Security ID</label>
                <input
                  className="apply-input"
                  placeholder="已回复对话的 security_id"
                  value={applyForm.security_id}
                  onChange={(event) => {
                    setApplyForm({ security_id: event.target.value });
                    setSelectedTargetValue("");
                  }}
                />
              </div>
            </div>
            <div className="apply-result">
              <span>
                选好目标后，直接去上面的提问区输入“麻烦发一下简历”，再看 `发送到 Boss` /
                auto-send 的真实返回即可。
              </span>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
