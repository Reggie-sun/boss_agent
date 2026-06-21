import {
  ArrowClockwise,
  CheckCircle,
  Clock,
  Lightning,
  MagnifyingGlass,
  PaperPlaneTilt,
  PlayCircle,
  WarningCircle,
} from "@phosphor-icons/react";

export function ReplyWorkspace({
  question,
  setQuestion,
  questionLength,
  selectedChatTarget,
  applyForm,
  chatTargets,
  selectedTargetValue,
  handleTargetSelection,
  chatTargetsLoading,
  loadChatTargets,
  isLoading,
  handleAsk,
  result,
  bridgeState,
  sendResumeWithDraft,
  setSendResumeWithDraft,
  handleSendToBoss,
  isSendingToBoss,
}) {
  return (
    <>
      <header className="workspace-header">
        <div>
          <span className="eyebrow">Agent 问题输入</span>
          <h2>让 Agent 调用知识库回答</h2>
        </div>
        <div className="meta-pill">
          <Clock size={18} />
          适合 HR / 技术 / 项目 / 行为面试追问
        </div>
      </header>

      <section className="question-panel question-panel--input">
        <div className="target-picker">
          <div className="target-picker__summary">
            <strong>Boss 发送目标</strong>
            <span>
              {selectedChatTarget
                ? `${selectedChatTarget.company || "未知公司"} / ${selectedChatTarget.recruiter_name || "未命名 HR"}`
                : applyForm.security_id.trim()
                  ? "已手动填写 security_id"
                  : "未选择，发简历请求不会真实发送"}
            </span>
          </div>
          <div className="target-picker__controls">
            {chatTargets.length ? (
              <select
                className="target-picker__select"
                value={selectedTargetValue}
                onChange={(event) => handleTargetSelection(event.target.value)}
              >
                <option value="">选择真实 Boss 对话目标</option>
                {chatTargets.map((target, index) => (
                  <option
                    key={`${String(target.conversation_id || target.security_id || "")}-${index}`}
                    value={String(target.conversation_id || target.security_id || "")}
                  >
                    {`${target.company || "未知公司"} · ${target.recruiter_name || "未命名 HR"} · ${target.title || "未知职位"}`}
                  </option>
                ))}
              </select>
            ) : (
              <span className="target-picker__empty">
                {chatTargetsLoading ? "正在读取目标..." : "暂无可选目标"}
              </span>
            )}
            <button
              type="button"
              className="inline-action"
              onClick={loadChatTargets}
              disabled={chatTargetsLoading}
            >
              <ArrowClockwise size={16} />
              {chatTargetsLoading ? "刷新中" : "刷新目标"}
            </button>
          </div>
        </div>
        <div className="input-headline">
          <h3>你的问题</h3>
          <span>{questionLength} 字</span>
        </div>
        <textarea
          className="prompt-editor"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="例如：请介绍一下企业级 RAG 项目的核心架构，以及你负责的模块。"
        />
        <div className="input-actions">
          <button
            type="button"
            className="inline-action"
            onClick={() => setQuestion("")}
          >
            <ArrowClockwise size={16} />
            清空
          </button>
          <button
            type="button"
            className="inline-action inline-action--primary"
            onClick={handleAsk}
            disabled={isLoading || !question.trim()}
          >
            {isLoading ? (
              <Lightning size={16} weight="fill" />
            ) : (
              <PlayCircle size={16} weight="fill" />
            )}
            {isLoading ? "Agent 回答中..." : "让 Agent 回答"}
          </button>
        </div>
      </section>

      <section className="answer-region">
        <div className="answer-region__header">
          <div>
            <h3>Agent 回答结果</h3>
            <p>
              <span
                className={`answer-region__verified-dot ${result.ok ? "is-success" : ""}`}
              />
              {result.ok
                ? `已收到 Agent 最终回答${result.latencyMs ? ` · ${result.latencyMs}ms` : ""}`
                : isLoading
                  ? "正在等待 Agent 完成编排"
                  : "等待你发起问题"}
            </p>
            {result.delivery?.status === "sent" ? (
              <p>
                {result.delivery.resume_sent
                  ? "已通过 Boss 真实发送附件简历 PDF。"
                  : result.delivery.send_attachment_resume
                    ? "附件简历 PDF 没有成功发出。"
                    : "已通过 Boss 真实发送这条 Agent 草稿消息。"}
              </p>
            ) : result.delivery?.status === "sending" ? (
              <p>
                已识别为发简历请求，正在通过 Boss 真实发送
                {result.delivery.send_attachment_resume ? "附件简历 PDF" : "这条 Agent 草稿"}。
              </p>
            ) : result.delivery?.status === "browser_channel_unavailable" ? (
              <p>
                发送到 Boss 失败：
                {result.delivery.error_message || "当前 CDP / Bridge 不可用。"}
              </p>
            ) : result.delivery?.status === "disabled" ? (
              <p>已识别为发简历请求，但本地未开启自动发送。</p>
            ) : result.delivery?.status === "missing_security_id" ? (
              <p>发送到 Boss 失败：当前没有可用的 `security_id`。</p>
            ) : result.delivery?.status === "resume_failed" ||
              result.delivery?.status === "message_failed" ? (
              <p>
                {result.delivery.status === "resume_failed"
                  ? `附件简历 PDF 发送失败：${result.delivery.error_message || "未知错误"}。`
                  : `发送到 Boss 失败：${result.delivery.error_message || "未知错误"}。`}
              </p>
            ) : null}
          </div>
          <div className="answer-region__status">
            {result.errorMessage ? (
              <WarningCircle size={18} weight="fill" />
            ) : (
              <CheckCircle size={18} weight="fill" />
            )}
            <span>{result.askedAt || "尚未提问"}</span>
          </div>
        </div>

        <div className="editor-shell editor-shell--answer">
          {isLoading ? (
            <div className="answer-state answer-state--loading">
              <div className="answer-loader" />
              <div>
                <strong>Agent 正在整理回答</strong>
                <p>这一步会提交到本地 Agent bridge `/api/agent/ask`，再整理最终 answer / citations。</p>
              </div>
            </div>
          ) : result.errorMessage ? (
            <div className="answer-state answer-state--error">
              <WarningCircle size={22} weight="fill" />
              <div>
                <strong>调用失败</strong>
                <p>{result.errorMessage}</p>
              </div>
            </div>
          ) : result.answer ? (
            <article className="answer-markdown">
              {result.answer.split(/\n{2,}/).map((paragraph, index) => (
                <p key={`${index}-${paragraph.slice(0, 18)}`}>{paragraph}</p>
              ))}
            </article>
          ) : (
            <div className="answer-state">
              <MagnifyingGlass size={22} />
              <div>
                <strong>还没有回答结果</strong>
                <p>先输入一个问题，然后点击“让 Agent 回答”。</p>
              </div>
            </div>
          )}
        </div>

        {result.answer ? (
          <div className="answer-actions">
            <div className="answer-actions__meta">
              <strong>发送到 Boss</strong>
              <span>
                {result.draftId
                  ? "这一步会复用 `boss agent send`，由后端通过 CDP 真实发送。"
                  : "当前回答还没有可发送的 draft_id。"}
              </span>
              {!bridgeState.browserChannel.available &&
              bridgeState.browserChannel.errorMessage ? (
                <span>
                  当前浏览器发送通道不可用：
                  {bridgeState.browserChannel.errorMessage}
                </span>
              ) : null}
            </div>
            <div className="answer-actions__controls">
              <label className="send-toggle">
                <input
                  type="checkbox"
                  checked={sendResumeWithDraft}
                  onChange={(event) => setSendResumeWithDraft(event.target.checked)}
                />
                <span>发送附件简历 PDF</span>
              </label>
              <button
                type="button"
                className="inline-action inline-action--primary"
                onClick={handleSendToBoss}
                disabled={isSendingToBoss || !result.draftId}
              >
                <PaperPlaneTilt size={16} weight="fill" />
                {isSendingToBoss ? "发送中..." : "发送到 Boss"}
              </button>
            </div>
          </div>
        ) : null}
      </section>
    </>
  );
}
