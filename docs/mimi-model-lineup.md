# Mimi model lineup

Which model answers each Mimi tier, per region, and where to change it.
Last verified **2026-09-11** against the live gateways (global backend v4.80.3, China `dev` ffdece37, MimiWork v0.6.13).

Legend: **off** = hidden reasoning disabled (fast), **on** = model reasons before answering (slower, smarter).

## 1. What a user gets

| Tier | Price | Leg | EU (strict GDPR) | US (default) | China (质见中国) |
|---|---|---|---|---|---|
| **Mimi Puppy** | free daily | text, any difficulty | DeepSeek V4 Flash · Scaleway Paris · off | DeepSeek V4 Flash · DigitalOcean · off | DeepSeek Flash · DeepSeek API · off |
| | | images | Qwen 3.5 397B · Scaleway | Qwen 3.5 397B · DigitalOcean | Qwen3 VL Flash · DashScope |
| **Mimi Hound** | free daily | easy, medium | DeepSeek V4 Flash · Scaleway · on | DeepSeek V4 Flash · DigitalOcean · on | DeepSeek Flash · DeepSeek API · on |
| | | hard | same as easy | GPT-5.6 Luna · OpenAI | same as easy |
| | | images | Mistral Small 3.2 24B · Scaleway | Qwen 3.5 397B · DigitalOcean | Qwen3 VL Plus · DashScope |
| **Mimi Wolf** | credits | easy | DeepSeek V4 Flash · Scaleway · on | DeepSeek V4 Flash · DigitalOcean · on | DeepSeek Flash · DeepSeek API · on |
| | | medium | same as easy | GPT-5.6 Luna · OpenAI | same as easy |
| | | hard | GLM-5.2 · Scaleway | Qwen 3.8 Max · DigitalOcean | DeepSeek V4 Pro · DeepSeek API |
| | | images | Mistral Small 3.2 24B · Scaleway | Qwen 3.5 397B · DigitalOcean | Qwen3 VL Plus · DashScope |
| **Mimi Werewolf** | credits | everything | Claude Sonnet 4.5 · Bedrock EU | GPT-5.6 Terra · OpenAI | Qwen 3.8 Max · DashScope |
| **Fallback** | | when the primary fails | DeepSeek V4 Flash · Scaleway · off | GPT-5.6 Luna · OpenAI (every US slot) | DeepSeek Flash · DeepSeek API |

Notes
- Difficulty (easy / medium / hard) is classified per request by the gateway; a client can force a leg with `mimi_route` (`fast`, `hard`, `vision`). Images always take the image leg.
- Hound never escalates in EU; in US and China it escalates on the hard leg only.
- China has no EU/US choice: the deployment has no DigitalOcean key, so it always resolves the EU-named slots below.
- Puppy and Hound share one free allowance: 1000 credits-equivalent per user per day (`MIMIWORK_FREE_DAILY_CREDITS`).

## 2. Slot table (what the admin API and the overlay actually hold)

Global slots are admin overrides in the database (`PUT /api/admin/models/<slot>` with `{"model_id", "provider"}`), unless marked *baked* (code default, no override row). China values come from `MODEL_SLOTS_CN` in `backend/app/services/model_config_service.py` on the `dev` branch.

| Slot | Serves | Global model id | Global provider | China model id | China provider |
|---|---|---|---|---|---|
| `mimiwork.free` | EU Puppy text | `deepseek-v4-flash-0731:none` | scaleway | `deepseek-flash:none` | deepseek |
| `mimiwork.free_fallback` | EU free fallback | `deepseek-v4-flash-0731:none` | scaleway | `deepseek-flash` | deepseek |
| `mimiwork.eu_vision_plus` | EU Puppy images | `qwen3.5-397b-a17b` | scaleway | `qwen3-vl-flash` | qwen |
| `mimiwork.fusion_fast` | EU Hound all; EU Wolf easy, medium | `deepseek-v4-flash-0731` | scaleway | `deepseek-flash` | deepseek |
| `mimiwork.fusion_advanced` | EU Wolf hard | `glm-5.2` | scaleway | `deepseek-v4-pro` | deepseek |
| `mimiwork.fusion_vision` | EU Hound, Wolf images | `mistral-small-3.2-24b-instruct-2506` | scaleway | `qwen3-vl-plus` | qwen |
| `mimiwork.eu_werewolf` | EU Werewolf | `eu.anthropic.claude-sonnet-4-5-20250929-v1:0` | bedrock-anthropic | `qwen3.8-max` | qwen |
| `mimiwork.us_free` | US Puppy text | `deepseek-v4-flash-0731:none` *(baked)* | do-inference | mirror, inert | deepseek |
| `mimiwork.us_flash` | US Hound easy, medium; US Wolf easy | `deepseek-v4-flash-0731` | do-inference | mirror, inert | deepseek |
| `mimiwork.us_medium` | US Hound hard; US Wolf medium | `gpt-5.6-luna` | openai | mirror, inert | deepseek |
| `mimiwork.us_hard` | US Wolf hard | `qwen3.8-max` | do-inference | mirror, inert | deepseek |
| `mimiwork.us_vision` | US images (all tiers but Werewolf) | `qwen3.5-397b-a17b` | do-inference | mirror, inert | qwen |
| `mimiwork.us_fallback` | fallback for every `us_*` slot | `gpt-5.6-luna` *(baked)* | openai | mirror, inert | deepseek |
| `mimiwork.us_werewolf` | US Werewolf | `gpt-5.6-terra` | openai | mirror, inert | qwen |

## 3. Fallback rules

Defined in `_FALLBACK_SLOTS` in `backend/app/routers/llm_gateway.py`. A fallback runs when the primary's breaker is open or the call itself errors; the fallback's own model and rate are what gets billed.

| Primary slot | Falls back to | Region promise |
|---|---|---|
| `mimiwork.free` | `mimiwork.free_fallback` (Scaleway) | EU stays in Paris |
| `mimiwork.fusion_fast` | `mimiwork.free` (Scaleway) | EU stays in Paris |
| `mimiwork.us_free`, `us_flash`, `us_medium`, `us_hard`, `us_vision` | `mimiwork.us_fallback` (GPT-5.6 Luna) | US stays on OpenAI |
| China: the EU rows above apply, with DeepSeek overlaid | `deepseek-flash` | China stays on DeepSeek |
| `fusion_advanced`, `fusion_vision`, `eu_vision_plus`, both `werewolf` slots | none | error surfaces to the user |

Verified 2026-09-11: with `us_medium` pointed at a model OpenAI does not serve, a Hound hard request still answered in 1.7 s and the ledger billed `gpt-5.6-luna`.

## 4. Reasoning control per provider

The effort suffix on a slot's model id (`:none`, `:low`, …) becomes `reasoning_effort` upstream, with one translation.

| Provider | `:none` | `:low` | No suffix |
|---|---|---|---|
| Scaleway (DeepSeek V4 Flash) | reasoning off, reliable | mostly short, not reliable | reasons, 1 to 30 s before the first word |
| DigitalOcean (DeepSeek V4 Flash) | reasoning off, reliable | **ignored** | reasons |
| DeepSeek API | sent as `thinking.type=disabled`, reliable | ignored | reasons |
| OpenAI (Luna, Terra) | no hidden reasoning either way | | |
| DashScope (Qwen 3.8 Max) | untested | untested | reasons at length, 30 s first word seen |

## 5. Measured on 2026-09-11 (single calls, real image, tool schema attached)

| Cell | First visible word | Notes |
|---|---|---|
| Puppy EU / US / China | 1.1 s / 1.1 to 2.0 s / 2 to 7 s | zero reasoning on every run |
| Hound easy EU / US / China | 5.8 s / 5 to 11 s / 3 to 4 s | 200 to 2,100 chars of reasoning |
| Hound hard US (Luna) | 2.0 to 3.5 s | tools work |
| Wolf hard EU (GLM-5.2) | 50 s once | Scaleway GLM-5.2 was slow that day |
| Wolf hard China (DeepSeek Pro) | 9 to 16 s | |
| Werewolf China (Qwen 3.8 Max) | 31 to 33 s | heavy reasoning |
| Images, all 12 cells | 0.4 to 3.3 s | all pass |
| 30 concurrent users, Puppy or Hound, EU or US | median 6 s, p95 11 to 16 s | measured before the Puppy/Hound split; no 429s |

## 6. How to change things

- **Global slot**: `PUT https://starfish-app-73rfk.ondigitalocean.app/api/admin/models/<slot>` with the owner JWT, body `{"model_id": "...", "provider": "...", "note": "..."}`. Takes effect at once; `DELETE` resets to the baked default. The admin refuses providers the gateway cannot relay (Bedrock without the bridge, for example).
- **China slot**: edit `MODEL_SLOTS_CN` on `dev`, push; `.github/workflows/deploy-cn-dev.yml` redeploys the box in about 2 minutes. Any new model id needs a price in `backend/app/utils/annotator_cost.py` or the gateway answers 503 "no configured credit rate".
- **Tier or fallback tables** (`TIER_SLOTS`, `_FALLBACK_SLOTS`): code in `llm_gateway.py`, pinned by `backend/tests/test_gateway_regions.py`. Global deploy = build `lanceyuu/backend3:<tag>` for linux/amd64, push, `doctl apps create-deployment e2d9622f-6142-4af6-bc08-b9a936ff7001`.
- **Verify** through the client's path: `stream: true`, `Authorization: Bearer qt_…`, `mimi_region` and `mimi_route` in the body; read `/api/llm/v1/metrics` and the credit ledger, which name the model actually billed.

## 7. Open items

| Item | Status |
|---|---|
| GLM 5.3 / 5.3 Flash for China | DashScope lists them under `ZHIPU/`, but the product is not activated on the QualiTaTi Alibaba account ("product is not activated"). Activate in Model Studio, then price and slot them. |
| DigitalOcean limits | Ticket open (2FA requirement met 2026-09-11). Until raised, `Platform overloaded` 429s and the daily token cap remain possible; the Luna fallback now catches them. |
| Werewolf China | Qwen 3.8 Max reasons for 30 s; consider an effort suffix once DashScope's support for it is tested. |
| `deepseek-flash` | DeepSeek's rolling alias; the API never reports which version served. |
| MimiWork app | v0.6.13 released; main carries the Ollama picker fix, unreleased. |
