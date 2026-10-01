# G4 outcome-classifier fixtures (model-free)

Stream-json event sequences for `tests/test_outcome_classifier.py`. No personal account data, no
credentials. Session ids are fixed test ids. Free text is replaced by placeholders, except the
CLI's own auth-error text in `real_auth_expired`. In the three **REAL** files, every event `uuid`
was replaced with a synthetic sequential id (one-to-one, event order and all other fields
unchanged); an id that contained `401` still contains `401`.

| File | Provenance | Expected |
|---|---|---|
| `real_success_uuid401.jsonl` | **REAL** Claude Code 2.1.263 run (Candidate-2 spike `cred2/m.jsonl`), sanitized; two event `uuid`s contain `401` | `completed` (the old classifier said `auth_failure`) |
| `real_success_rate_limit_allowed.jsonl` | **REAL** (`cred2/t.jsonl`), sanitized; informational `rate_limit_event` `status=allowed` | `completed` |
| `real_auth_expired.jsonl` | **REAL** (`credspike/m1.jsonl`), sanitized; 2× `api_retry` 401 `authentication_failed`, API-error wrapper, result `is_error`/401/`api_error` | `auth_failure` |
| `g11_success_regression.jsonl` | **RECONSTRUCTED** shape of the successful G11 smoke (the real stream was deleted by the smoke's cleanup): marker answer, 5 Bash probes with their observed outputs, informational rate-limit event, `**DONE**`, success result; one `uuid` contains `401` (the reproduced trigger) | `completed` (the old classifier said `auth_failure`) |
| `synthetic_limit_rejected.jsonl` | **SYNTHETIC, provisional**. A real subscription-limit stream has never been observed. It uses only fields seen in real streams or defined in the 2.1.263 binary (`rate_limit_info.status=rejected`, wrapper `error=rate_limit`, result 429/`api_error`) | `limit_interrupted` |
