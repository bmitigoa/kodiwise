# KodiWise architecture: MCP server and in-app chat

## Components

| Component | Where | Role |
|---|---|---|
| `kodiwise-api` | Cloud Run, rent-prediction-ar | LightGBM estimates, ranges, explanations, area stats. The single source of every number. |
| `agent/core` | library | Tool logic shared by both surfaces: validation, tools, injection defence, config, telemetry, resources. |
| MCP server | `agent/mcp_server`, stdio, local | Tools plus read-only resources for desktop assistants. |
| `kodiwise-chat` | Cloud Run, `chat/` | Firebase-authenticated `/chat`; Gemini function calling over the same tools. |
| Firestore (kodiwise-9adab) | Firebase | Approved listings (read). Usage counters (see Open items). |

## Data flow (chat)

app -> `/chat` (Firebase ID token) -> history cleaning (PII removed, instruction-like text neutralised) -> scope guard (no Gemini call if off-topic) -> user counter -> Gemini tool loop (max 4 tool calls, compact results) -> number guard + KES normalisation (templated answer on mismatch) -> reply + cards.

## Trust boundaries

- Untrusted: user messages, client-supplied model turns, listing titles and text, area names typed by users, model output.
- Trusted: API results, config, the system prompt.
- Untrusted text is neutralised, wrapped as `untrusted_text`, never used as tool arguments without validation, and never a source of figures.

## Security model

- No tool writes. The only writer is `chat/limits.py` (usage counters); a test scans the code for any other write, file write or process call.
- Secrets: Gemini key in Secret Manager only; nothing in code or logs.
- Fail closed: counters unavailable -> friendly busy reply, no Gemini call.
- Logs and traces carry no message text, names, emails, phones or tokens; users appear as an 8-character hash.

## Limits

See the generated table in README.md ("Limits and thresholds"), produced from `agent/core/config.py`; a test keeps them identical.

## Token use

Fixed prompt plus tool declarations: about 1,400 -> 1,020 tokens per request. Typical tool results sent to the model are 55-60% smaller (full results still drive cards and the number check).

## Open items

IAM: Firestore IAM Conditions only target the database (`projects/.../databases/...`), not collections or documents, so the planned collection-level restriction is not possible. The chosen alternative is to keep counters in a Firestore database in rent-prediction-ar (`CHAT_COUNTERS_PROJECT`) and give the chat service account only read access (`roles/datastore.viewer`) on kodiwise-9adab. This needs a Firestore database in rent-prediction-ar and IAM changes, which are applied only after approval.
