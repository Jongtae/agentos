# Native tool calling acceptance

Scope: reliable current-weather requests over the OpenRouter tool_calls protocol, including location-only follow-ups. General web search remains best-effort and is not a substitute for the weather tool.

Required checks:
1. Every compatible-model request sends tool definitions; results return as role=tool with matching tool_call_id.
2. Explicit weather and location follow-up requests select weather or ask_location, not general web search. Missing location triggers clarification without an invented location.
3. Successful weather answers show resolved location, exact API temperature, unit, observation/model timestamp and source. The application renders verified weather values, preventing an LLM denial from replacing retrieved facts.
4. Failed/unavailable tools cannot produce a succeeded job; users see the error. Retries are bounded.
5. Every tool request and result is persisted by job ID and call ID. A subsequent request cannot overwrite earlier evidence.
6. Automated protocol, policy, failure, persistence checks pass; live OpenRouter + Open-Meteo explicit and follow-up checks pass in the installed build.

Limits: model forecasts are not sensor observations; free provider availability is external. No claim of universal web-search quality, arbitrary browsing, or all-model reliability.

## Verification result

Homebrew 0.1.7: all 3 live cases passed against real OpenRouter and Open-Meteo. See WEATHER_ACCEPTANCE_RESULT.json for call IDs, native arguments, returned API values and final responses. Automated tests: 32 passed, including tool protocol, missing location, no-call rejection and failed-job trace persistence. Installed HTTP setup, note persistence and restart checks also passed. This is a bounded acceptance run, not a guarantee of external provider uptime.
