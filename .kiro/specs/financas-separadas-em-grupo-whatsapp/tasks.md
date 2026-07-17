# Implementation Plan

- [x] 1. Expand the Evolution webhook normalizer identity contract
  - Update `NormalizedWebhookMessage` in `app/services/webhook_normalizer.py` with `chat_jid`, `participant_jid`, `user_phone`, `reply_to`, and `is_group`.
  - Keep `phone` as a compatibility alias for the financial user phone during this change.
  - Add constants for group JID suffix `@g.us` and individual JID suffixes `@s.whatsapp.net` and `@c.us`.
  - Add `is_group_jid(value)` helper.
  - Update `normalize_whatsapp_phone(value)` so individual JIDs normalize to plain phone numbers and group JIDs are not converted into financial user phones.
  - Extract `chat_jid` from `data.key.remoteJid`, `key.remoteJid`, `data.remoteJid`, or `remoteJid`.
  - Detect `is_group` from `chat_jid.endswith("@g.us")`.
  - Extract `participant_jid` for group messages from `data.key.participant`, `key.participant`, `data.participant`, `participant`, `data.sender`, or `sender`.
  - Derive `user_phone` from `participant_jid` for group messages and from `chat_jid` for individual messages.
  - Set `reply_to` to `chat_jid`.
  - Return ignored results for missing chat JID, missing participant, missing user phone, unsupported events, own messages, and missing content.
  - Preserve existing text, image, audio, event, and `from_me` parsing behavior.
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 6.1, 6.2, 7.1, 7.2, 7.3_

- [x] 2. Add normalizer unit coverage for group identity and media
  - Update existing normalizer tests to assert `user_phone`, `chat_jid`, `reply_to`, and `is_group`.
  - Add a group text test using `data.key.participant`.
  - Add parameterized tests for participant extraction from `key.participant`, `data.participant`, `participant`, `data.sender`, and `sender`.
  - Add tests that `5541999999999@s.whatsapp.net` and `5541999999999@c.us` normalize to `5541999999999`.
  - Add a test that group JIDs are detected as groups.
  - Add a test that a group message without participant is ignored with `missing_participant`.
  - Add tests that image and audio group payloads preserve the participant `user_phone` and group `reply_to`.
  - Keep existing tests for unsupported events, own messages, missing content, and text extraction passing.
  - _Requirements: 2.1, 2.2, 2.3, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 6.1, 6.2, 8.7, 8.8_

- [x] 3. Preserve group JIDs in outbound Evolution sends
  - Update `_normalize_phone` in `app/services/evolution.py` to return values ending in `@g.us` unchanged.
  - Keep current behavior that strips `@s.whatsapp.net` and `@c.us` from individual JIDs.
  - Leave the public `send_text(phone, message)` signature unchanged.
  - Treat the `phone` argument in `send_text` as the WhatsApp destination, which may be an individual number or a group JID.
  - Ensure failure logging does not expose `EVOLUTION_API_KEY`.
  - _Requirements: 4.2, 4.3, 4.4, 4.5_

- [x] 4. Add Evolution service tests for group destinations
  - Add a unit test that `_normalize_phone("1203630xxxx@g.us")` returns the original group JID.
  - Add or keep unit tests that individual JIDs with `@s.whatsapp.net` and `@c.us` are stripped.
  - Add a `send_text` test that verifies group `reply_to` is sent unchanged in the Evolution `number` payload.
  - Keep existing tests for endpoint path, headers, payload, HTTP errors, and missing config passing.
  - _Requirements: 4.2, 4.3, 4.4, 8.9_

- [x] 5. Implement webhook authorization and identity routing
  - Load `ALLOWED_GROUP_JID` in `app/main.py`.
  - Add `should_process_message(normalized)` or equivalent helper that ignores private chats, missing allowed group config, unauthorized groups, missing user phone, and missing reply destination.
  - Validate `EVOLUTION_WEBHOOK_SECRET` before message processing as the current webhook already does.
  - Normalize the payload before any agent branch.
  - Use `user_phone = normalized.user_phone` for all calls to `FinanceAgent`.
  - Use `reply_to = normalized.reply_to` for all calls to `whatsapp.send_text`.
  - Return `{"status": "ignored", "reason": <reason>}` for authorization or normalization ignores.
  - Keep `fromMe=true` ignored before agent processing and outbound sending.
  - Add structural logging for event, ignored status, reason, group status, masked chat identity, and participant presence.
  - Avoid logging raw message text, full media URLs, raw payloads, webhook secrets, or API keys.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.4, 2.5, 3.7, 3.8, 4.1, 4.2, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 6. Route text, image, audio, and error responses with separated identities
  - Update the text branch to call `agent.process(phone=user_phone, message=normalized.text)`.
  - Update the image branch to call `agent.process_image(phone=user_phone, image_url=normalized.image_url, caption=normalized.image_caption or "")`.
  - Update the audio branch to transcribe `normalized.audio_url` and then call `agent.process(phone=user_phone, message=transcribed_text)`.
  - Send the audio transcription failure message to `reply_to`.
  - Send final agent responses to `reply_to`.
  - Send the existing instability fallback message to `reply_to` when it is available.
  - Ensure no branch sends group responses to `user_phone` or passes group JIDs to the agent.
  - _Requirements: 2.4, 2.5, 4.1, 4.2, 4.5, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 7. Add FastAPI webhook tests for group authorization and routing
  - Add a test that private text messages are ignored and do not call the agent or outbound send.
  - Add a test that messages from a non-authorized group are ignored and do not call the agent or outbound send.
  - Add a test that authorized group text calls `agent.process` with the participant phone.
  - Add a test that authorized group text sends the response to the group JID.
  - Add a test that `fromMe=true` in the authorized group is ignored.
  - Add a test that missing `ALLOWED_GROUP_JID` fails closed by ignoring group messages.
  - Add a test that two different participants in the same group produce distinct `agent.process` phone arguments.
  - Keep existing webhook secret tests passing.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.4, 2.5, 2.6, 4.1, 4.2, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 8. Add webhook tests for group image and audio behavior
  - Add an authorized group image test that calls `agent.process_image` with participant phone, image URL, and caption.
  - Assert the image response is sent to the group JID.
  - Add an authorized group audio test that mocks `process_audio`, calls `agent.process` with participant phone and transcribed text, and sends the response to the group JID.
  - Add an audio transcription failure test that sends the friendly error message to the group JID and does not call `agent.process`.
  - Ensure media tests verify `user_phone` and `reply_to` behavior matches text messages.
  - _Requirements: 2.4, 4.1, 4.2, 7.2, 7.3, 7.4, 7.5, 8.8_

- [x] 9. Confirm participant-scoped financial history remains isolated
  - Add or update tests that demonstrate two participant phone values do not share transaction/query scope.
  - Prefer using existing database helpers or agent tests rather than changing production schema.
  - Verify onboarding is keyed by participant `user_phone`, not group JID.
  - Verify `users.phone` and `transactions.phone` never receive a value ending in `@g.us` through the group webhook flow.
  - Avoid database migrations because the current schema already supports participant-scoped identities.
  - _Requirements: 2.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 10. Update environment and README documentation
  - Add `ALLOWED_GROUP_JID=1203630xxxx@g.us` to `.env.example`.
  - Update README environment configuration to include `ALLOWED_GROUP_JID`.
  - Document that private messages are ignored by default for this feature.
  - Document that only the configured group is processed.
  - Document that `remoteJid`/`chat_jid` is used as `reply_to` and participant JID is used as the financial user identity.
  - Document that Evolution group sending preserves `@g.us` in the outbound destination.
  - Update manual validation steps for authorized group, unauthorized group, private chat, text, image, audio, and two participant isolation.
  - _Requirements: 1.1, 1.2, 1.3, 4.3, 8.9_

- [x] 11. Run automated validation and final checks
  - Run the full test suite with `pytest`.
  - Fix regressions caused by the expanded normalizer contract or changed webhook routing.
  - Confirm the app still imports and starts with FastAPI, Evolution API, LangGraph, and SQLAlchemy unchanged.
  - Confirm no LangGraph node, prompt, model, or database helper was refactored unnecessarily.
  - Confirm `FinanceAgent` still receives participant phone values and never group JIDs in group tests.
  - Confirm `EvolutionService` receives group JIDs for group replies.
  - Confirm documentation and `.env.example` mention `ALLOWED_GROUP_JID`.
  - _Requirements: 1.1, 1.2, 1.3, 2.4, 2.5, 3.8, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_
