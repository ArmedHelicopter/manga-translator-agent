# Manga Translate Agent Web API 说明书

本文档描述 Manga Translate Agent (mga) Web UI 的后端 API 接口。

## 基础信息

| 项目 | 值 |
|------|------|
| 后端地址 | `http://127.0.0.1:8000` |
| 前端代理 | `http://localhost:3000` (开发环境自动代理 `/api/*` 到后端) |
| 认证方式 | 无 (本地使用) |
| 数据格式 | JSON |
| 编码 | UTF-8 |

---

## API 端点总览

### 项目管理 (Projects)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/projects` | 获取所有项目列表 |
| POST | `/api/projects` | 创建新项目 |
| GET | `/api/projects/{project_id}` | 获取指定项目详情 |

### 角色管理 (Characters)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/projects/{project_id}/characters` | 获取项目所有角色 |
| GET | `/api/projects/{project_id}/characters/{character_id}` | 获取指定角色详情 |
| PUT | `/api/projects/{project_id}/characters/{character_id}` | 创建/更新角色档案 |

### 术语管理 (Terms)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/projects/{project_id}/terms` | 获取项目所有术语 |
| GET | `/api/projects/{project_id}/terms/{term_id}` | 获取指定术语详情 |
| POST | `/api/projects/{project_id}/terms/{term_id}` | 保存术语 |

### Provider 配置

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/projects/{project_id}/provider-config` | 获取 Provider 配置 |
| POST | `/api/projects/{project_id}/provider-config` | 保存 Provider 配置 |

### 翻译报告 (Translation Reports)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/projects/{project_id}/translation-reports` | 获取翻译报告列表 |
| GET | `/api/projects/{project_id}/translation-report` | 获取指定报告内容 |
| GET | `/api/projects/{project_id}/review-items` | 获取 QA 审核项 |
| POST | `/api/projects/{project_id}/review-decisions` | 提交审核决策 |

### 翻译执行 (Translation)

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/translate/start` | 开始翻译任务 |
| POST | `/api/translate/stop` | 停止翻译任务 |
| GET | `/api/translate/status` | 获取翻译状态 |
| GET | `/api/translate/progress/stream` | SSE 实时进度流 |

### 批量任务 (Batch Jobs)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/batch/jobs` | 获取所有批量任务 |
| POST | `/api/batch/jobs` | 创建批量任务 |
| POST | `/api/batch/jobs/{job_id}/start` | 启动批量任务 |
| POST | `/api/batch/jobs/{job_id}/pause` | 暂停批量任务 |
| POST | `/api/batch/jobs/{job_id}/resume` | 恢复批量任务 |
| DELETE | `/api/batch/jobs/{job_id}` | 删除批量任务 |
| GET | `/api/batch/jobs/{job_id}/status` | 获取任务状态 |

### 系统控制 (System)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/health` | 健康检查 |
| POST | `/api/backend/start` | 启动后端服务 |
| POST | `/api/backend/stop` | 停止后端服务 |

---

## 详细接口定义

### 1. 项目管理

#### GET /api/projects

获取所有项目列表。

**响应示例:**
```json
{
  "projects": [
    {
      "id": "my-manga",
      "name": "我的漫画",
      "path": "C:/path/to/my-manga",
      "source_lang": "ja",
      "target_lang": "zh-CN",
      "created_at": "2026-06-12T08:00:00Z",
      "updated_at": "2026-06-12T10:00:00Z",
      "character_count": 5,
      "term_count": 23,
      "scene_count": 12
    }
  ]
}
```

---

#### POST /api/projects

创建新项目。

**请求体:**
```json
{
  "name": "我的漫画项目",
  "source_lang": "ja",
  "target_lang": "zh-CN"
}
```

| 字段 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| name | string | ✅ | - | 项目名称 |
| source_lang | string | ❌ | "ja" | 源语言代码 |
| target_lang | string | ❌ | "zh-CN" | 目标语言代码 |

**响应:** 返回创建的项目摘要 (同 GET /api/projects/{project_id})

---

#### GET /api/projects/{project_id}

获取指定项目的详细信息。

**路径参数:**
| 参数 | 类型 | 描述 |
|------|------|------|
| project_id | string | 项目 ID (小写字母、数字、连字符) |

**响应:** 返回项目摘要对象

---

### 2. 角色管理

#### GET /api/projects/{project_id}/characters

获取项目中所有角色的摘要列表。

**响应示例:**
```json
{
  "characters": [
    {
      "character_id": "sakura",
      "name_jp": "桜",
      "name_zh": "樱花",
      "archetype": "热情的女主角",
      "speech_pattern_count": 3,
      "catchphrase_count": 2,
      "tone_count": 5,
      "translation_note_count": 1
    }
  ]
}
```

---

#### GET /api/projects/{project_id}/characters/{character_id}

获取指定角色的完整档案。

**响应示例:**
```json
{
  "character_id": "sakura",
  "name_jp": "桜",
  "name_zh": "樱花",
  "archetype": "热情的女主角",
  "speech_patterns": {
    " casual": "～よ、～だろ",
    " formal": "～です、～ます"
  },
  "catchphrases": ["绝对会赢给你看！", "不要小看我！"],
  "tone_spectrum": {
    " excited": "大声、快速、感叹号多",
    " sad": "小声、缓慢、叹气"
  },
  "translation_notes": {
    " honorific": "保留敬称，但根据情境调整"
  }
}
```

---

#### PUT /api/projects/{project_id}/characters/{character_id}

创建或更新角色档案。

**请求体:**
```json
{
  "name_jp": "桜",
  "name_zh": "樱花",
  "archetype": "热情的女主角",
  "speech_patterns": {
    " casual": "～よ、～だろ",
    " formal": "～です、～ます"
  },
  "catchphrases": ["绝对会赢给你看！", "不要小看我！"],
  "tone_spectrum": {
    " excited": "大声、快速、感叹号多"
  },
  "translation_notes": {
    " honorific": "保留敬称"
  }
}
```

| 字段 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| name_jp | string | ❌ | "" | 日文名 |
| name_zh | string | ❌ | "" | 中文名 |
| archetype | string | ❌ | "" | 角色原型/类型 |
| speech_patterns | object | ❌ | {} | 说话模式 (key=情境, value=模式) |
| catchphrases | string[] | ❌ | [] | 口头禅 |
| tone_spectrum | object | ❌ | {} | 语气谱 (key=情绪, value=描述) |
| translation_notes | object | ❌ | {} | 翻译笔记 |

---

### 3. 术语管理

#### GET /api/projects/{project_id}/terms

获取项目中所有术语的摘要列表。

**响应示例:**
```json
{
  "terms": [
    {
      "term_id": "ninja_scroll",
      "term_jp": "忍術巻物",
      "term_zh": "忍者卷轴",
      "cultural_weight": "artifact",
      "strategy": "adapt",
      "pending_human_review": false,
      "frequency": 15,
      "candidate_count": 3
    }
  ]
}
```

---

#### GET /api/projects/{project_id}/terms/{term_id}

获取指定术语的详细信息。

**响应示例:**
```json
{
  "term_id": "ninja_scroll",
  "term_jp": "忍術巻物",
  "term_zh": "忍者卷轴",
  "candidate_translations": ["忍者卷轴", "忍术卷轴", "秘传卷轴"],
  "context": "故事中的重要道具，用于记录忍术",
  "cultural_weight": "artifact",
  "strategy": "adapt",
  "accepted_reason": "最符合中文读者的理解习惯",
  "rejected_reasons": {
    "秘传卷轴": "过于强调秘密性，原文未强调"
  },
  "applicability_scope": "所有涉及该道具的场景",
  "pending_human_review": false,
  "frequency": 15
}
```

---

#### POST /api/projects/{project_id}/terms/{term_id}

保存或更新术语定义。

**请求体:**
```json
{
  "term_jp": "忍術巻物",
  "term_zh": "忍者卷轴",
  "candidate_translations": ["忍者卷轴", "忍术卷轴", "秘传卷轴"],
  "context": "故事中的重要道具",
  "cultural_weight": "artifact",
  "strategy": "adapt",
  "accepted_reason": "最符合中文读者的理解习惯",
  "rejected_reasons": {},
  "applicability_scope": "所有涉及该道具的场景",
  "pending_human_review": false,
  "frequency": 15
}
```

---

### 4. Provider 配置

#### GET /api/projects/{project_id}/provider-config

获取当前项目的 Provider 配置。

**响应示例:**
```json
{
  "path": "configs/providers.toml",
  "provider_options": ["openai", "anthropic", "gemini", "deepseek", "openrouter", "ollama", "vllm", "lmstudio", "llamacpp"],
  "stages": {
    "vision": {"primary": "openai", "fallback": "anthropic", "local": "ollama"},
    "translation": {"primary": "openai", "fallback": "deepseek", "local": "ollama"},
    "qa": {"primary": "anthropic", "fallback": "", "local": ""}
  },
  "providers": {
    "openai": {
      "api_key": "***",
      "text_model": "gpt-4o-mini"
    }
  }
}
```

**注意:** 敏感信息 (api_key 等) 会自动脱敏为 `***`

---

#### POST /api/projects/{project_id}/provider-config

保存 Provider 配置。

**请求体:**
```json
{
  "stages": {
    "vision": {"primary": "openai", "fallback": "anthropic", "local": "ollama"},
    "translation": {"primary": "openai", "fallback": "deepseek", "local": "ollama"},
    "qa": {"primary": "anthropic", "fallback": "", "local": ""}
  },
  "providers": {
    "openai": {
      "api_key": "${OPENAI_API_KEY}",
      "text_model": "gpt-4o-mini"
    },
    "anthropic": {
      "api_key": "${ANTHROPIC_API_KEY}"
    }
  }
}
```

**Provider 配置规则:**
- 敏感字段 (api_key, apiKey, token, secret, password) 必须使用环境变量占位符格式: `${ENV_VAR_NAME}`
- 可用 Provider: openai, anthropic, gemini, deepseek, openrouter, ollama, vllm, lmstudio, llamacpp

---

### 5. 翻译报告

#### GET /api/projects/{project_id}/translation-reports

获取项目中所有翻译报告的摘要列表。

**响应示例:**
```json
{
  "reports": [
    {
      "path": "output/chapter01/translation-report.json",
      "entry_count": 45,
      "preview_entries": [...],
      "review_items": [...],
      "entries_needing_human_review": 3,
      "avg_confidence": 0.85,
      "updated_at": "2026-06-12T10:00:00Z"
    }
  ]
}
```

---

#### GET /api/projects/{project_id}/translation-report

获取翻译报告的完整内容。

**查询参数:**
| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| path | string | ✅ | 报告相对于项目根目录的路径 |

---

#### GET /api/projects/{project_id}/review-items

获取 QA 审核项列表。

**查询参数:**
| 参数 | 类型 | 必需 | 描述 |
|------|------|------|------|
| path | string | ✅ | 报告路径 |

---

#### POST /api/projects/{project_id}/review-decisions

提交对 QA 审核项的决策。

**请求体:**
```json
{
  "report_path": "output/chapter01/translation-report.json",
  "item_id": "qa:page01:bubble03:0",
  "status": "accept",
  "rationale": "翻译准确，无需修改",
  "page_id": "page01",
  "bubble_id": "bubble03",
  "kind": "qa",
  "target": "translated_text",
  "action": "review_qa_finding",
  "message": "术语一致性检查",
  "confidence": 0.9
}
```

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| report_path | string | ✅ | 报告路径 |
| item_id | string | ✅ | 审核项 ID |
| status | string | ✅ | 决策: "accept" 或 "reject" |
| rationale | string | ❌ | 决策理由 |
| page_id | string | ❌ | 页 ID |
| bubble_id | string | ❌ | 对话框 ID |
| kind | string | ❌ | 类型: "qa" 或 "repair" |
| target | string | ❌ | 目标字段 |
| action | string | ❌ | 操作类型 |
| message | string | ❌ | 消息 |
| confidence | float | ❌ | 置信度 (0-1) |

---

### 6. 翻译执行

#### POST /api/translate/start

开始翻译任务。

**请求体:**
```json
{
  "project_id": "my-manga",
  "input_path": "input/chapter01",
  "mode": "manga",
  "format": "images",
  "parallel_mode": "auto",
  "concurrency": 4
}
```

| 字段 | 类型 | 必需 | 默认值 | 描述 |
|------|------|------|--------|------|
| project_id | string | ✅ | - | 项目 ID |
| input_path | string | ✅ | - | 输入路径 |
| mode | string | ❌ | "manga" | 翻译模式 |
| format | string | ❌ | "images" | 输入格式 |
| parallel_mode | string | ❌ | null | 并行模式: "auto", "page", "bubble" |
| concurrency | int | ❌ | null | 并发数 |

**响应:**
```json
{
  "status": "started",
  "message": "Translation started"
}
```

**错误:**
- `409 Conflict`: 当前已有翻译任务在运行

---

#### POST /api/translate/stop

停止当前翻译任务。

**响应:**
```json
{
  "status": "stopped"
}
```

---

#### GET /api/translate/status

获取当前翻译状态。

**响应:**
```json
{
  "status": "running",
  "stage": "translation",
  "progress": 65.0,
  "elapsed": 45.5,
  "error": null
}
```

| 字段 | 类型 | 描述 |
|------|------|------|
| status | string | 状态: "idle", "running", "paused", "completed", "failed" |
| stage | string | 当前阶段 |
| progress | float | 进度 (0-100) |
| elapsed | float | 已用时间 (秒) |
| error | string | 错误信息 |

---

#### GET /api/translate/progress/stream

SSE 实时进度流。

**响应类型:** `text/event-stream`

**事件类型:**
- `progress`: 进度更新
- `heartbeat`: 心跳保活 (每 30 秒)

**progress 事件数据:**
```json
{
  "stage": "translation",
  "progress": 65.0,
  "elapsed": 45.5,
  "status": "running"
}
```

---

### 7. 批量任务

#### GET /api/batch/jobs

获取所有批量任务。

**响应示例:**
```json
{
  "jobs": [
    {
      "id": "job_1_1718170000.0",
      "name": "批量翻译第1卷",
      "input_path": "input/vol01",
      "output_path": "output/vol01",
      "status": "completed",
      "progress": 100.0,
      "error": null,
      "created_at": "2026-06-12T08:00:00Z",
      "completed_at": "2026-06-12T10:00:00Z"
    }
  ]
}
```

---

#### POST /api/batch/jobs

创建批量任务。

**请求体:**
```json
{
  "name": "批量翻译第1卷",
  "input_path": "input/vol01",
  "output_path": "output/vol01",
  "config": {
    "parallel_mode": "auto",
    "concurrency": 4
  }
}
```

---

#### POST /api/batch/jobs/{job_id}/start

启动批量任务。

---

#### POST /api/batch/jobs/{job_id}/pause

暂停批量任务。

---

#### POST /api/batch/jobs/{job_id}/resume

恢复批量任务。

---

#### DELETE /api/batch/jobs/{job_id}

删除批量任务。

---

#### GET /api/batch/jobs/{job_id}/status

获取批量任务状态。

**响应:**
```json
{
  "id": "job_1_1718170000.0",
  "status": "running",
  "progress": 45.5,
  "error": null,
  "completed_at": null
}
```

---

### 8. 系统控制

#### GET /api/health

健康检查。

**响应:**
```json
{
  "status": "healthy",
  "timestamp": "2026-06-12T10:00:00Z"
}
```

---

#### POST /api/backend/start

启动后端服务 (当前为无操作占位符)。

---

#### POST /api/backend/stop

停止后端服务 (当前为无操作占位符，请求关闭服务器)。

---

## 错误响应

所有错误响应都遵循 FastAPI 标准格式：

```json
{
  "detail": "错误描述信息"
}
```

**常见 HTTP 状态码:**
| 状态码 | 含义 |
|--------|------|
| 200 | 成功 |
| 201 | 创建成功 |
| 404 | 资源不存在 |
| 409 | 冲突 (如项目已存在或翻译任务已在运行) |
| 422 | 请求验证失败 |
| 500 | 服务器内部错误 |

---

## 可用 Provider 列表

| Provider | 支持视觉 | 特点 |
|----------|----------|------|
| openai | ✅ | GPT-4o 系列，默认首选 |
| anthropic | ✅ | Claude 系列，Claude 模型 |
| gemini | ✅ | Google Gemini 模型 |
| deepseek | ❌ | 文本翻译，便宜 |
| openrouter | ✅ | 统一网关 |
| ollama | ✅ | 本地模型，REST API |
| vllm | ✅ | OpenAI 兼容本地 |
| lmstudio | ✅ | OpenAI 兼容本地 |
| llamacpp | ❌ | llama-server 本地 |

---

## 使用示例

### cURL 示例

```bash
# 获取项目列表
curl http://127.0.0.1:8000/api/projects

# 创建项目
curl -X POST http://127.0.0.1:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "测试项目", "source_lang": "ja", "target_lang": "zh-CN"}'

# 获取 Provider 配置
curl http://127.0.0.1:8000/api/projects/test/provider-config

# 保存 Provider 配置
curl -X POST http://127.0.0.1:8000/api/projects/test/provider-config \
  -H "Content-Type: application/json" \
  -d '{
    "stages": {
      "vision": {"primary": "openai"},
      "translation": {"primary": "openai"},
      "qa": {"primary": "anthropic"}
    },
    "providers": {
      "openai": {"api_key": "${OPENAI_API_KEY}"}
    }
  }'
```

### JavaScript fetch 示例

```javascript
// 获取项目列表
const res = await fetch('/api/projects');
const data = await res.json();
console.log(data.projects);

// 创建角色档案
await fetch('/api/projects/my-project/characters/sakura', {
  method: 'PUT',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    name_jp: '桜',
    name_zh: '樱花',
    archetype: '热情的女主角',
    catchphrases: ['绝对会赢给你看！'],
    speech_patterns: {'casual': '～よ、～だろ'}
  })
});

// 订阅翻译进度
const eventSource = new EventSource('/api/translate/progress/stream');
eventSource.addEventListener('progress', (e) => {
  const data = JSON.parse(e.data);
  console.log(`进度: ${data.progress}% - ${data.stage}`);
});
```

---

## 配置存储位置

| 配置项 | 文件路径 |
|--------|----------|
| 项目元数据 | `{project_dir}/project_meta.toml` |
| Provider 配置 | `{project_dir}/configs/providers.toml` |
| 角色档案 | `{project_dir}/memory/state/characters/` |
| 术语数据库 | `{project_dir}/memory/state/terms/` |

---

*文档版本: 1.0.0*
*最后更新: 2026-06-12*
