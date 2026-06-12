import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAppStore, type ProviderConfig } from '../store'
import { providerApi } from '../api'
import { CheckCircle, AlertTriangle, RefreshCw, Trash2, Settings } from 'lucide-react'
import clsx from 'clsx'

// Provider 完整信息
interface ProviderInfo {
  id: string
  name: string
  description: string
  supportsVision: boolean
  supportsText: boolean
  defaultVisionModel: string
  defaultTextModel: string
  models: {
    vision?: string[]
    text?: string[]
  }
}

const PROVIDER_CATALOG: ProviderInfo[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    description: 'GPT-4o 系列，支持视觉和文本',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: 'gpt-4o',
    defaultTextModel: 'gpt-4o-mini',
    models: {
      vision: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo'],
      text: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-3.5-turbo'],
    },
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    description: 'Claude 3.5 系列，支持视觉和文本',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: 'claude-3-5-sonnet-20241022',
    defaultTextModel: 'claude-3-5-sonnet-20241022',
    models: {
      vision: ['claude-3-5-sonnet-20241022', 'claude-3-opus-20240229', 'claude-3-sonnet-20240229'],
      text: ['claude-3-5-sonnet-20241022', 'claude-3-5-haiku-20241022', 'claude-3-opus-20240229', 'claude-3-sonnet-20240229'],
    },
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    description: 'Gemini 1.5 系列，支持视觉和文本',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: 'gemini-1.5-pro',
    defaultTextModel: 'gemini-1.5-flash',
    models: {
      vision: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.5-pro-latest'],
      text: ['gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-pro', 'gemini-pro-vision'],
    },
  },
  {
    id: 'deepseek',
    name: 'DeepSeek',
    description: 'DeepSeek V3/R1 系列，性价比高',
    supportsVision: false,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'deepseek-chat',
    models: {
      text: ['deepseek-chat', 'deepseek-coder'],
    },
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    description: '统一网关，聚合多种模型',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: 'openai/gpt-4o',
    defaultTextModel: 'openai/gpt-4o-mini',
    models: {
      vision: ['openai/gpt-4o', 'anthropic/claude-3-opus', 'google/gemini-pro-1.5'],
      text: ['openai/gpt-4o-mini', 'anthropic/claude-3-haiku', 'google/gemini-flash-1.5'],
    },
  },
  {
    id: 'ollama',
    name: 'Ollama (Local)',
    description: '本地模型，支持 llama/QwQ 等',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: 'llama3.2-vision',
    defaultTextModel: 'llama3.2',
    models: {
      vision: ['llama3.2-vision', 'llava'],
      text: ['llama3.2', 'qwen2.5', 'mistral', 'codellama'],
    },
  },
  {
    id: 'vllm',
    name: 'vLLM (Local)',
    description: '本地 vLLM 服务器，OpenAI 兼容',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'Qwen/Qwen2.5-7B-Instruct',
    models: {
      vision: ['Qwen/Qwen2-VL', 'llava'],
      text: ['Qwen/Qwen2.5-7B-Instruct', 'meta-llama/Llama-3.1-8B-Instruct'],
    },
  },
  {
    id: 'lmstudio',
    name: 'LM Studio (Local)',
    description: '本地 LM Studio，OpenAI 兼容',
    supportsVision: true,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'local-model',
    models: {
      vision: ['llava', 'qwen2-vl'],
      text: ['local-model'],
    },
  },
  {
    id: 'llamacpp',
    name: 'llama.cpp (Local)',
    description: '纯 CPU 本地模型，轻量',
    supportsVision: false,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'llama',
    models: {
      text: ['llama', 'mistral-7b', 'qwen2.5-7b'],
    },
  },
  {
    id: 'groq',
    name: 'Groq',
    description: '超快推理速度',
    supportsVision: false,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'llama-3.1-70b-versatile',
    models: {
      text: ['llama-3.1-70b-versatile', 'llama-3.1-8b-instant', 'mixtral-8x7b-32768'],
    },
  },
  {
    id: 'cohere',
    name: 'Cohere',
    description: 'Command R 系列',
    supportsVision: false,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'command-r-plus',
    models: {
      text: ['command-r-plus', 'command-r', 'command'],
    },
  },
  {
    id: 'mistral',
    name: 'Mistral AI',
    description: 'Mistral Small/Large',
    supportsVision: false,
    supportsText: true,
    defaultVisionModel: '',
    defaultTextModel: 'mistral-small-latest',
    models: {
      text: ['mistral-small-latest', 'mistral-large-latest', 'mistral-7b-instruct'],
    },
  },
]

const STAGES = [
  { id: 'vision', labelKey: 'providers.stages.vision' as const, desc: '图像识别、角色检测' },
  { id: 'translation', labelKey: 'providers.stages.translation' as const, desc: '文本翻译' },
  { id: 'qa', labelKey: 'providers.stages.qa' as const, desc: '质量检查' },
]

const ROLES = [
  { id: 'primary', labelKey: 'onboarding.apiKey.providerTypes.primary' as const },
  { id: 'fallback', labelKey: 'onboarding.apiKey.providerTypes.fallback' as const },
  { id: 'local', labelKey: 'onboarding.apiKey.providerTypes.local' as const },
]

export default function ProvidersPage() {
  const { t } = useTranslation()
  const { projectId } = useParams()
  const { providerConfig, selectedProjectId, setProviderConfig } = useAppStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errors, setErrors] = useState<string[]>([])
  const [selectedProviderTab, setSelectedProviderTab] = useState<string | null>(null)

  const effectiveProjectId = projectId || selectedProjectId

  useEffect(() => {
    if (effectiveProjectId) {
      loadConfig()
    }
  }, [effectiveProjectId])

  const loadConfig = async () => {
    if (!effectiveProjectId) return
    try {
      setLoading(true)
      const config = await providerApi.get(effectiveProjectId)
      setProviderConfig(config)
      validateConfig(config)
    } catch (error) {
      console.error('Failed to load provider config:', error)
    } finally {
      setLoading(false)
    }
  }

  const validateConfig = (config: ProviderConfig) => {
    const newErrors: string[] = []

    for (const stage of STAGES) {
      const primary = config.stages[stage.id as keyof typeof config.stages]?.primary
      if (!primary) {
        newErrors.push(`${t(stage.labelKey)}: ${t('onboarding.apiKey.warnings.primaryRequired')}`)
      }
    }

    setErrors(newErrors)
  }

  const handleSave = async () => {
    if (!effectiveProjectId || !providerConfig) return
    try {
      setSaving(true)
      await providerApi.save(effectiveProjectId, providerConfig)
    } catch (error) {
      console.error('Failed to save provider config:', error)
    } finally {
      setSaving(false)
    }
  }

  // 更新阶段配置
  const updateStageConfig = (
    stageId: string,
    roleId: string,
    providerId: string,
    model: string
  ) => {
    if (!providerConfig) return

    const stages = { ...providerConfig.stages }
    const stageKey = stageId as keyof typeof stages

    if (!stages[stageKey]) {
      stages[stageKey] = { primary: '', fallback: '', local: '' }
    }

    stages[stageKey] = {
      ...stages[stageKey],
      [roleId]: providerId,
    }

    // 如果选择了 provider 同时更新模型
    if (providerId) {
      const providers = { ...providerConfig.providers }
      if (!providers[providerId]) {
        providers[providerId] = {}
      }

      const info = PROVIDER_CATALOG.find((p) => p.id === providerId)
      if (info) {
        const isVisionStage = stageId === 'vision'
        const modelKey = isVisionStage ? 'vision_model' : 'text_model'
        const defaultModel = isVisionStage ? info.defaultVisionModel : info.defaultTextModel

        // 如果没有设置过模型，使用默认值
        if (!providers[providerId][modelKey]) {
          providers[providerId] = {
            ...providers[providerId],
            [modelKey]: model || defaultModel,
          }
        }
      }

      setProviderConfig({ ...providerConfig, stages, providers })
    } else {
      setProviderConfig({ ...providerConfig, stages })
    }
  }

  // 更新 Provider 设置
  const updateProviderSetting = (providerId: string, key: string, value: string) => {
    if (!providerConfig) return

    const providers = {
      ...providerConfig.providers,
      [providerId]: {
        ...providerConfig.providers[providerId],
        [key]: value,
      },
    }

    setProviderConfig({ ...providerConfig, providers })
  }

  // 添加 Provider
  const addProvider = (providerId: string) => {
    if (!providerConfig) return

    const info = PROVIDER_CATALOG.find((p) => p.id === providerId)
    if (!info) return

    const providers = {
      ...providerConfig.providers,
      [providerId]: {
        api_key: '',
        base_url: '',
        ...(info.defaultVisionModel && { vision_model: info.defaultVisionModel }),
        ...(info.defaultTextModel && { text_model: info.defaultTextModel }),
      },
    }

    setProviderConfig({ ...providerConfig, providers })
    setSelectedProviderTab(providerId)
  }

  // 删除 Provider
  const removeProvider = (providerId: string) => {
    if (!providerConfig) return

    const providers = { ...providerConfig.providers }
    delete providers[providerId]

    // 从所有阶段移除对该 provider 的引用
    const stages = { ...providerConfig.stages }
    for (const stage of STAGES) {
      const stageKey = stage.id as keyof typeof stages
      if (stages[stageKey]) {
        for (const role of ROLES) {
          if (stages[stageKey][role.id as keyof typeof stages[typeof stageKey]] === providerId) {
            stages[stageKey] = {
              ...stages[stageKey],
              [role.id]: '',
            }
          }
        }
      }
    }

    setProviderConfig({ ...providerConfig, providers, stages })
    if (selectedProviderTab === providerId) {
      setSelectedProviderTab(null)
    }
  }

  const getConfiguredProviders = () => {
    if (!providerConfig) return []
    return Object.keys(providerConfig.providers)
  }

  const isProviderUsed = (providerId: string) => {
    if (!providerConfig) return false
    return Object.values(providerConfig.stages).some((stage) =>
      Object.values(stage).includes(providerId)
    )
  }

  if (!effectiveProjectId) {
    return (
      <div className="text-center py-12">
        <Settings size={48} className="text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">{t('projects.noProjects')}</p>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
      </div>
    )
  }

  const configuredProviders = getConfiguredProviders()

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('providers.title')}</h1>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary flex items-center gap-2"
        >
          {saving ? (
            <RefreshCw size={18} className="animate-spin" />
          ) : (
            <CheckCircle size={18} />
          )}
          {t('app.save')}
        </button>
      </div>

      {/* Warnings */}
      {errors.length > 0 && (
        <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-xl">
          <div className="flex items-start gap-3">
            <AlertTriangle className="text-amber-500 flex-shrink-0 mt-0.5" size={20} />
            <div className="space-y-1">
              {errors.map((error, i) => (
                <p key={i} className="text-sm text-amber-800">
                  {error}
                </p>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Provider Selection Tabs */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">{t('providers.configuredProviders')}</h2>
          <span className="text-sm text-gray-500">({configuredProviders.length})</span>
        </div>
        <div className="flex flex-wrap gap-2">
          {configuredProviders.map((providerId) => {
            const info = PROVIDER_CATALOG.find((p) => p.id === providerId)
            const inUse = isProviderUsed(providerId)
            return (
              <button
                key={providerId}
                onClick={() => setSelectedProviderTab(providerId)}
                className={clsx(
                  'px-4 py-2 rounded-lg border transition-all flex items-center gap-2',
                  selectedProviderTab === providerId
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-gray-200 bg-white text-gray-700 hover:border-primary-300'
                )}
              >
                <span className="font-medium">{info?.name || providerId}</span>
                {inUse && (
                  <span className="w-2 h-2 rounded-full bg-green-500" title="正在使用" />
                )}
                <Trash2
                  size={14}
                  className="text-gray-400 hover:text-red-500 ml-1"
                  onClick={(e) => {
                    e.stopPropagation()
                    removeProvider(providerId)
                  }}
                />
              </button>
            )
          })}
        </div>
      </div>

      {/* Provider Catalog - Horizontal Scroll */}
      <div className="mb-8">
        <div className="flex items-center gap-2 mb-4">
          <h2 className="text-lg font-semibold text-gray-900">{t('providers.addProvider')}</h2>
        </div>
        <div className="relative">
          <div className="flex gap-3 overflow-x-auto pb-4 scrollbar-hide">
            {PROVIDER_CATALOG.map((provider) => {
              const isAdded = configuredProviders.includes(provider.id)
              return (
                <div
                  key={provider.id}
                  className={clsx(
                    'flex-shrink-0 w-64 p-4 rounded-xl border transition-all',
                    isAdded
                      ? 'border-green-200 bg-green-50 opacity-60'
                      : 'border-gray-200 bg-white hover:border-primary-300 hover:shadow-md'
                  )}
                >
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-semibold text-gray-900">{provider.name}</h3>
                      <p className="text-xs text-gray-500 mt-0.5">{provider.description}</p>
                    </div>
                    {provider.supportsVision && (
                      <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded">
                        视觉
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {provider.models.text && provider.models.text.length > 0 && (
                      <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded">
                        {provider.models.text.length} 个文本模型
                      </span>
                    )}
                    {provider.models.vision && provider.models.vision.length > 0 && (
                      <span className="text-xs px-2 py-0.5 bg-blue-50 text-blue-600 rounded">
                        {provider.models.vision.length} 个视觉模型
                      </span>
                    )}
                  </div>
                  {!isAdded && (
                    <button
                      onClick={() => addProvider(provider.id)}
                      className="mt-3 w-full py-1.5 text-sm bg-primary-50 text-primary-600 rounded-lg hover:bg-primary-100 transition-colors"
                    >
                      + 添加
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Stage Configuration */}
      <div className="space-y-6">
        <h2 className="text-lg font-semibold text-gray-900">{t('providers.stageConfig')}</h2>

        {STAGES.map((stage) => {
          const stageConfig = providerConfig?.stages[stage.id as keyof typeof providerConfig.stages] || {}

          return (
            <div key={stage.id} className="card p-6">
              <div className="mb-4">
                <h3 className="text-lg font-semibold text-gray-900">{t(stage.labelKey)}</h3>
                <p className="text-sm text-gray-500 mt-1">{stage.desc}</p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {ROLES.map((role) => (
                  <div key={role.id} className="space-y-3">
                    <label className="label flex items-center gap-2">
                      {t(role.labelKey)}
                      {role.id === 'primary' && (
                        <span className="text-xs px-1.5 py-0.5 bg-primary-100 text-primary-700 rounded">
                          推荐
                        </span>
                      )}
                      {role.id === 'local' && (
                        <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                          免费
                        </span>
                      )}
                    </label>

                    <div className="space-y-2">
                      {/* Provider Slider */}
                      <div className="relative">
                        <select
                          value={stageConfig[role.id as keyof typeof stageConfig] || ''}
                          onChange={(e) => updateStageConfig(stage.id, role.id, e.target.value, '')}
                          className="input w-full pr-10"
                        >
                          <option value="">-- 选择 Provider --</option>
                          {configuredProviders.map((providerId) => {
                            const info = PROVIDER_CATALOG.find((p) => p.id === providerId)
                            const isVisionStage = stage.id === 'vision'
                            const supportsStage =
                              (isVisionStage && info?.supportsVision) ||
                              (!isVisionStage && info?.supportsText)

                            if (!supportsStage) return null

                            return (
                              <option key={providerId} value={providerId}>
                                {info?.name || providerId}
                              </option>
                            )
                          })}
                        </select>
                      </div>

                      {/* Model Selection */}
                      {stageConfig[role.id as keyof typeof stageConfig] && (
                        <div className="mt-2">
                          <label className="text-xs text-gray-500 mb-1 block">模型</label>
                          <select
                            value={
                              providerConfig?.providers[stageConfig[role.id as keyof typeof stageConfig]]?.[
                                stage.id === 'vision' ? 'vision_model' : 'text_model'
                              ] || ''
                            }
                            onChange={(e) => {
                              const providerId = stageConfig[role.id as keyof typeof stageConfig]
                              updateProviderSetting(
                                providerId,
                                stage.id === 'vision' ? 'vision_model' : 'text_model',
                                e.target.value
                              )
                            }}
                            className="input w-full text-sm"
                          >
                            <option value="">-- 选择模型 --</option>
                            {(() => {
                              const providerId = stageConfig[role.id as keyof typeof stageConfig]
                              const info = PROVIDER_CATALOG.find((p) => p.id === providerId)
                              const models =
                                stage.id === 'vision'
                                  ? info?.models.vision || []
                                  : info?.models.text || []
                              return models.map((model) => (
                                <option key={model} value={model}>
                                  {model}
                                </option>
                              ))
                            })()}
                          </select>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {/* Provider Detail Settings */}
      {selectedProviderTab && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            {PROVIDER_CATALOG.find((p) => p.id === selectedProviderTab)?.name} 配置
          </h2>
          <div className="card p-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* API Key */}
              <div>
                <label className="label">{t('providers.settings.apiKey')}</label>
                <input
                  type="password"
                  value={providerConfig?.providers[selectedProviderTab]?.api_key || ''}
                  onChange={(e) =>
                    updateProviderSetting(selectedProviderTab, 'api_key', e.target.value)
                  }
                  placeholder="${OPENAI_API_KEY}"
                  className="input"
                />
                <p className="text-xs text-gray-500 mt-1">
                  支持环境变量格式: $&#123;ENV_VAR_NAME&#125;
                </p>
              </div>

              {/* Base URL */}
              <div>
                <label className="label">{t('providers.settings.baseUrl')}</label>
                <input
                  type="text"
                  value={providerConfig?.providers[selectedProviderTab]?.base_url || ''}
                  onChange={(e) =>
                    updateProviderSetting(selectedProviderTab, 'base_url', e.target.value)
                  }
                  placeholder="https://api.openai.com/v1"
                  className="input"
                />
              </div>

              {/* Vision Model */}
              {PROVIDER_CATALOG.find((p) => p.id === selectedProviderTab)?.supportsVision && (
                <div>
                  <label className="label">{t('providers.settings.visionModel')}</label>
                  <input
                    type="text"
                    value={providerConfig?.providers[selectedProviderTab]?.vision_model || ''}
                    onChange={(e) =>
                      updateProviderSetting(selectedProviderTab, 'vision_model', e.target.value)
                    }
                    placeholder="gpt-4o"
                    className="input"
                  />
                </div>
              )}

              {/* Text Model */}
              {PROVIDER_CATALOG.find((p) => p.id === selectedProviderTab)?.supportsText && (
                <div>
                  <label className="label">{t('providers.settings.textModel')}</label>
                  <input
                    type="text"
                    value={providerConfig?.providers[selectedProviderTab]?.text_model || ''}
                    onChange={(e) =>
                      updateProviderSetting(selectedProviderTab, 'text_model', e.target.value)
                    }
                    placeholder="gpt-4o-mini"
                    className="input"
                  />
                </div>
              )}

              {/* Advanced Settings */}
              <div>
                <label className="label">Max Tokens</label>
                <input
                  type="number"
                  value={providerConfig?.providers[selectedProviderTab]?.max_tokens || ''}
                  onChange={(e) =>
                    updateProviderSetting(selectedProviderTab, 'max_tokens', e.target.value)
                  }
                  placeholder="4096"
                  className="input"
                />
              </div>

              <div>
                <label className="label">Temperature</label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={providerConfig?.providers[selectedProviderTab]?.temperature || ''}
                  onChange={(e) =>
                    updateProviderSetting(selectedProviderTab, 'temperature', e.target.value)
                  }
                  placeholder="0.7"
                  className="input"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}