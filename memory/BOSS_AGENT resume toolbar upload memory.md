# BOSS_AGENT resume toolbar upload memory

在 `/home/reggie/vscode_folder/BOSS_AGENT` 调试真实 Boss 附件简历发送时，必须区分两条 UI 链路：有“附件简历请求卡片”时优先点聊天记录里的 `同意`，无卡片时才走聊天工具栏 `.chat-editor` 的 `发简历` 主动发送链路。主动链路不能再 fallback 到 `.btn-send:not(.disabled)`，因为它是聊天文本发送按钮，空输入会 disabled；应打开 `发简历` 弹层，选择 `上传附件简历` / `上传简历` / `附件简历`，只使用 `ka="user-resume-upload-file"` 或 accept 包含 pdf 的 input，并只在可见“简历/附件/RESUME/EXPORT”弹层内点确认/发送，最后用聊天记录 PDF 文件名增加确认。

本轮相关改动面：`src/boss_agent_cli/api/client.py::send_resume_attachment(...)` 和 `tests/test_api_client_methods.py`。回归检查至少覆盖三条：`resume-request-agree` 请求卡片优先且不上传文件；无卡片时 `resume-toolbar-upload` 不点击 `.btn-send`；`Page.evaluate: Execution context was destroyed` 后仍能恢复并进入工具栏 fallback。当前环境当时 `9222` 只有 `about:blank`，所以真实 Boss E2E 未完成；后续真实 QA 前先确认 CDP profile 有可用 Boss 聊天页且目标会话唯一。
