# KodiWise architecture: MCP server and in-app chat

## Components

| Component | Where | Role |
|---|---|---|
| `kodiwise-api` | Cloud Run, rent-prediction-ar | LightGBM estimates, ranges, explanations, area stats. The single source of every number. |
| `agent/core` | library | Tool logic shared by both surfaces: validation, tools, injection defence, config, telemetry, resources. |
| MCP server | `agent/mcp_server`, stdio, local | Tools plus read-only resources for desktop assistants. |
| `kodiwise-chat` | Cloud Run, `chat/` | Firebase-authenticated `/chat`; Gemini function calling over the same tools. |
| Firestore (kodiwise-9adab) | Firebase | Approved listings. The chat and MCP accounts have `datastore.viewer` only. |
| Firestore `kodiwise-counters` | rent-prediction-ar, africa-south1 | Chat usage counters (`chatUsage`, `chatGlobal`, TTL on `expireAt`). The only data the chat writes. |

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

## Least privilege (as deployed)

- `kodiwise-chat` service account: `roles/datastore.viewer` on kodiwise-9adab; `roles/datastore.user` on rent-prediction-ar **with an IAM Condition** limiting it to the database `projects/rent-prediction-ar/databases/kodiwise-counters`; secret accessor on the Gemini key only. Firestore IAM Conditions work per database, not per collection, which is why the counters have their own database.
- Verified live (impersonating the account): writes to `properties/`, `users/` and `chatUsage/` in kodiwise-9adab, and to `users/` and `properties/` in rent-prediction-ar `(default)`, are denied; writes to `chatUsage`/`chatGlobal` in `kodiwise-counters` succeed; approved listings can be read.
- `kodiwise-mcp-readonly` service account: `roles/datastore.viewer` on kodiwise-9adab. The MCP server impersonates it when `KODIWISE_MCP_IMPERSONATE` is set. Firestore has no read-only OAuth scope, so the role is what makes it read-only.
