source visual truth path: `/home/reggie/.codex/generated_images/019ec549-1fb7-7c11-b117-68623f079e92/ig_0efe164037eb9069016a2e6a8cdbd8819a80ef1b9216d9231e.png`
runtime target: local Vite app bridged to Enterprise RAG via `/api/rag/ask`
verification date: `2026-06-14`

**Flow Under Test**
- Input a question in the center panel.
- Let the local agent bridge forward the request to `POST /api/v1/chat/ask`.
- Render `answer`, `citations`, and `reasoning_summary` back into the three-zone `Evidence Desk` layout.

**Verification**
- API verification: passed
  - `GET http://127.0.0.1:4173/api/rag/health` returned `configured: true` and `ready: true`.
  - `POST http://127.0.0.1:4173/api/rag/ask` returned `ok: true` with answer payload from Enterprise RAG.
- Runtime verification: passed
  - `GET http://127.0.0.1:18020/api/v1/health` returned healthy status from the new compose-backed API instance.
- Chrome MCP smoke: blocked
  - The available Chrome MCP session on this machine could not navigate from `about:blank` to the localhost URL.
  - Fallback visual/runtime smoke used the running Vite app plus direct HTTP checks against the same bridge endpoints.

**Findings**
- No current P0 / P1 issues were found in the prompt-to-RAG path.
- The prototype now matches the updated product goal better than the earlier scripted interview flow.

**Notes**
- This QA pass supersedes the older static interview-script validation.
- If `.env` changes again, restart Vite before trusting bridge health, because the local proxy reads env at server startup.

final result: passed
