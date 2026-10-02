# Decisions

One line per decision taken while building the RAG service, the voice agent and the CRM additions,
with the reason. Newest at the bottom of each section.

## Setup

- Java 21 is at `/opt/homebrew/opt/openjdk@21` but not on the default PATH; every Maven run sets `JAVA_HOME` to it rather than changing the machine's Java setup.
- `backend/src/main/resources/application.yml` was entirely commented out and `application.properties` is gitignored, so a fresh clone could not start or test the CRM; the YAML is restored as committed, env-driven config (same keys/defaults as `application.properties.example`), and a local `application.properties` still overrides it.
- Baseline before any change: backend `mvn test` 46/46 passing (with the restored config).

## Phase 1 — voice engine

- `last try/` does not exist in the repository; nothing to delete. README and `deploy/azure/deploy.sh` now point at `/voice-agent`.
- The bank agent has no tool-calling loop, outbound dialer, call registry, retry outbox or metrics module; they were written new in `/voice-agent` (labelled NEW in `voice-agent/docs/ENGINE_INVENTORY.md`), keeping the bank's code style.
- The bank's language helpers lived in `app/domain/`; they moved to `app/lang/` so `app/domain/` holds only the domain seam. Imports were the only change.
- Gujarati was added to language detection, Sarvam STT/TTS language codes and spoken-form tables; en/hi/mr behaviour and every tuned speech setting are unchanged.
- Banking words (account, loan, EMI, …) were removed from the Devanagari transliteration table and are now left to the TTS, so no banking vocabulary remains in `app/`.
- The banking-vocabulary scan allowlists exactly one module, `app/domain/real_estate/sensitive.py`, because refusing Aadhaar/PAN/OTP/financing questions requires naming them.
- The engine's single-letter-prefix reading quirk (`P52…` → "पीपाँच…") is existing bank behaviour and was not retuned.
- The tool loop runs at most `MAX_TOOL_HOPS=3` model calls with tools, then one without, so a model that keeps calling tools still answers.
- Whole earlier turns (including tool calls and results) are replayed to the model (`HISTORY_TURNS=4`) instead of the bank's last 6 text messages, so a slot list fetched one turn earlier is still available when the caller picks one.
- Domain HTTP routes are registered from the composition root (`app/wiring.py`), the only engine module that names the domain.
