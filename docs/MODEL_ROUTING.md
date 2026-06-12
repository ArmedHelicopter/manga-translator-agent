# Model Routing

Manga Translate Agent resolves providers and models per pipeline stage. This lets you use strong multimodal models where images matter, cheaper text models for translation/QA, and local models as a final fallback.

## Supported stages

Provider routes are configured under `[stages.*]`:

- `[stages.vision]` — page understanding/OCR and image-aware work.
- `[stages.translation]` — translated dialogue/text generation.
- `[stages.qa]` — proofreading and quality checks.

If `[stages.qa]` is omitted, QA inherits the translation route.

## Three-layer routing system

### 1. Stage route layer

Each stage chooses route providers:

```toml
[stages.translation]
primary = "openai"
fallback = "deepseek"
local = "ollama"
```

Routes are tried as primary → fallback → local by the provider cascade. `local` is also used when the pipeline is forced into local-only behavior.

### 2. Stage-level model override layer

Each stage can override the model used by each route:

```toml
[stages.translation]
primary = "openai"
model = "gpt-4.1-mini"

fallback = "deepseek"
fallback_model = "deepseek-chat"

local = "ollama"
local_model = "qwen2.5:14b"
```

These keys are stage-specific:

| Stage key | Applies to route |
| --- | --- |
| `model` | `primary` |
| `fallback_model` | `fallback` |
| `local_model` | `local` |

### 3. Provider defaults layer

Provider sections define reusable model defaults:

```toml
[providers.openai]
api_key = "${OPENAI_API_KEY}"
vision_model = "gpt-4.1-mini"
text_model = "gpt-4.1-mini"

[providers.deepseek]
api_key = "${DEEPSEEK_API_KEY}"
model = "deepseek-chat"
```

`vision_model` is used for `[stages.vision]`. `text_model` is used for `[stages.translation]` and `[stages.qa]`. If a stage-specific provider model is not present, `model` is used as a generic default.

## Exact model resolution priority

For each route, the loader resolves the model in this order:

```text
stage.{model|fallback_model|local_model}
  ↓
provider.{vision_model|text_model}
  ↓
provider.model
  ↓
built-in default from get_provider_model_default(provider, stage)
```

Examples:

```toml
[stages.vision]
primary = "openai"
model = "stage-vision"

[providers.openai]
vision_model = "provider-vision"
model = "provider-generic"
```

Vision uses `stage-vision` because `stages.vision.model` has highest priority.

```toml
[stages.translation]
primary = "openai"

[providers.openai]
text_model = "provider-text"
model = "provider-generic"
```

Translation uses `provider-text` because there is no stage-level `model`.

```toml
[stages.qa]
primary = "deepseek"

[providers.deepseek]
model = "deepseek-chat"
```

QA uses `deepseek-chat` because there is no `text_model`, so the provider generic `model` is used.

## CLI provider override behavior

The CLI `--provider` option replaces the primary provider for every stage, but it does **not** discard stage-level primary model overrides.

For example:

```toml
[stages.vision]
primary = "openai"
model = "gpt-4.1-mini"

[providers.mimo]
provider_type = "openai"
vision_model = "mimo-v2.5-pro"
text_model = "mimo-v2.5-pro"
```

Running with `--provider mimo` produces:

```text
vision.primary.provider = mimo
vision.primary.model    = gpt-4.1-mini
```

This is intentional: `--provider` swaps the provider, while stage-level `model` remains the strongest explicit model choice. Remove the stage `model` if you want the override provider's `vision_model` or `text_model` to apply.

Fallback and local routes are preserved when `--provider` is used.

## Cost optimization best practices

### Keep vision expensive, text cheap

Use multimodal models only for vision:

```toml
[stages.vision]
primary = "gemini"
model = "gemini-2.0-flash"
fallback = "openai"
fallback_model = "gpt-4.1-mini"

[stages.translation]
primary = "deepseek"
model = "deepseek-chat"

[stages.qa]
primary = "deepseek"
model = "deepseek-chat"
```

### Use provider defaults for simple projects

If one provider model is good for both text stages, define it once:

```toml
[stages.translation]
primary = "openai"

[stages.qa]
primary = "openai"

[providers.openai]
text_model = "gpt-4.1-mini"
```

### Use route-specific fallback models

Fallbacks can use cheaper or more robust models than primary routes:

```toml
[stages.translation]
primary = "openai"
model = "gpt-4.1"
fallback = "deepseek"
fallback_model = "deepseek-chat"
```

### Add local routes for resilience

Local routes avoid total failure when remote providers are unavailable:

```toml
[stages.translation]
primary = "openai"
fallback = "deepseek"
local = "ollama"
local_model = "qwen2.5:14b"

[providers.ollama]
base_url = "http://localhost:11434"
model = "qwen2.5:14b"
```

## Multi-provider mixing examples

### Balanced quality/cost

```toml
[stages.vision]
primary = "openai"
model = "gpt-4.1-mini"
fallback = "gemini"
fallback_model = "gemini-2.0-flash"

[stages.translation]
primary = "deepseek"
model = "deepseek-chat"
fallback = "openai"
fallback_model = "gpt-4.1-mini"

[stages.qa]
primary = "deepseek"
model = "deepseek-chat"
```

### OpenAI-compatible custom provider

```toml
[stages.vision]
primary = "compatible"

[stages.translation]
primary = "compatible"

[providers.compatible]
provider_type = "openai"
api_key = "${COMPATIBLE_API_KEY}"
base_url = "https://compatible.example/v1"
vision_model = "compatible-vision-model"
text_model = "compatible-text-model"
```

### Built-in Mimo profile

The built-in `mimo` profile has model defaults. A minimal config can be:

```toml
[stages.vision]
primary = "mimo"

[stages.translation]
primary = "mimo"

[providers.mimo]
```

The loader falls back to the built-in Mimo defaults if no provider model is configured.

## Troubleshooting

### `Stage 'vision' is missing a primary provider.`

Add a primary provider to the stage:

```toml
[stages.vision]
primary = "openai"
```

### `Stage 'translation' references unknown provider 'x'.`

Every stage provider name must have a matching `[providers.x]` section.

```toml
[stages.translation]
primary = "deepseek"

[providers.deepseek]
api_key = "${DEEPSEEK_API_KEY}"
model = "deepseek-chat"
```

### `Provider 'x' is missing 'vision_model' for stage 'vision'.`

The provider route resolved to an empty model. Add one of the supported model keys:

```toml
[stages.vision]
primary = "openai"
model = "gpt-4.1-mini"
```

or:

```toml
[providers.openai]
vision_model = "gpt-4.1-mini"
```

or:

```toml
[providers.openai]
model = "gpt-4.1-mini"
```

### CLI `--provider` uses the provider but not its model

Check whether the stage has a `model` key. Stage-level `model` overrides provider `vision_model`, `text_model`, and `model`, even under `--provider`.

To use the override provider's model, remove the stage-level `model`:

```toml
[stages.translation]
primary = "openai"
# model = "remove-or-comment-this"
```

### QA unexpectedly uses translation model

If `[stages.qa]` is omitted, QA inherits `[stages.translation]`. Add an explicit QA route if proofreading should use a different provider/model:

```toml
[stages.qa]
primary = "deepseek"
model = "deepseek-chat"
```

## Reference example

See [`../configs/providers.toml.example`](../configs/providers.toml.example) for a complete example with three usage modes and provider definitions.
