import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import { CheckCircle, ChevronRight, ChevronLeft, Globe, Key, Database, FolderOpen } from 'lucide-react'
import clsx from 'clsx'

const steps = [
  { id: 'language', icon: Globe },
  { id: 'welcome', icon: CheckCircle },
  { id: 'apiKey', icon: Key },
  { id: 'project', icon: FolderOpen },
  { id: 'complete', icon: CheckCircle },
]

export default function Onboarding() {
  const { i18n } = useTranslation()
  const setOnboardingComplete = useAppStore((state) => state.setOnboardingComplete)
  const [currentStep, setCurrentStep] = useState(0)
  const [selectedLanguage, setSelectedLanguage] = useState(i18n.language)

  const languages = [
    { code: 'en', name: 'English', flag: '🇺🇸' },
    { code: 'zh', name: '中文', flag: '🇨🇳' },
  ]

  const handleLanguageChange = (lang: string) => {
    setSelectedLanguage(lang)
    i18n.changeLanguage(lang)
    localStorage.setItem('language', lang)
  }

  const handleComplete = () => {
    setOnboardingComplete(true)
  }

  const renderStep = () => {
    switch (currentStep) {
      case 0:
        return (
          <LanguageStep
            languages={languages}
            selected={selectedLanguage}
            onChange={handleLanguageChange}
            onNext={() => setCurrentStep(1)}
          />
        )
      case 1:
        return <WelcomeStep onNext={() => setCurrentStep(2)} />
      case 2:
        return <ApiKeyStep onNext={() => setCurrentStep(3)} onBack={() => setCurrentStep(1)} />
      case 3:
        return <ProjectStep onNext={() => setCurrentStep(4)} onBack={() => setCurrentStep(2)} />
      case 4:
        return <CompleteStep onComplete={handleComplete} />
      default:
        return null
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 via-white to-accent-50 flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        {/* Progress Steps */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {steps.map((step, index) => (
            <div key={step.id} className="flex items-center">
              <div
                className={clsx(
                  'w-10 h-10 rounded-full flex items-center justify-center transition-all',
                  index < currentStep
                    ? 'bg-primary-600 text-white'
                    : index === currentStep
                    ? 'bg-primary-600 text-white ring-4 ring-primary-100'
                    : 'bg-gray-200 text-gray-400'
                )}
              >
                <step.icon size={18} />
              </div>
              {index < steps.length - 1 && (
                <div
                  className={clsx(
                    'w-12 h-0.5 mx-2',
                    index < currentStep ? 'bg-primary-600' : 'bg-gray-200'
                  )}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step Content */}
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
          {renderStep()}
        </div>
      </div>
    </div>
  )
}

function WelcomeStep({ onNext }: { onNext: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center">
      <div className="w-20 h-20 bg-gradient-to-br from-primary-500 to-accent-500 rounded-2xl flex items-center justify-center mx-auto mb-6">
        <span className="text-white font-bold text-3xl">M</span>
      </div>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">
        {t('onboarding.welcome.title')}
      </h1>
      <p className="text-gray-500 mb-6">{t('onboarding.welcome.subtitle')}</p>
      <p className="text-sm text-gray-400 mb-8">{t('onboarding.welcome.description')}</p>
      <button onClick={onNext} className="btn-primary px-8 py-3">
        {t('app.next')}
        <ChevronRight size={18} className="inline ml-2" />
      </button>
    </div>
  )
}

interface LanguageStepProps {
  languages: { code: string; name: string; flag: string }[]
  selected: string
  onChange: (lang: string) => void
  onNext: () => void
}

function LanguageStep({ languages, selected, onChange, onNext }: LanguageStepProps) {
  const { t } = useTranslation()

  return (
    <div>
      <div className="text-center mb-8">
        <Globe size={48} className="text-primary-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t('onboarding.language.title')}</h2>
        <p className="text-gray-500">{t('onboarding.language.subtitle')}</p>
      </div>

      <div className="grid grid-cols-2 gap-4 mb-8">
        {languages.map((lang) => (
          <button
            key={lang.code}
            onClick={() => onChange(lang.code)}
            className={clsx(
              'p-4 rounded-xl border-2 transition-all text-left',
              selected === lang.code
                ? 'border-primary-500 bg-primary-50'
                : 'border-gray-200 hover:border-gray-300'
            )}
          >
            <span className="text-2xl mr-3">{lang.flag}</span>
            <span className="font-medium text-gray-900">{lang.name}</span>
          </button>
        ))}
      </div>

      <div className="flex justify-end">
        <button onClick={onNext} className="btn-primary px-8 py-3">
          {t('app.next')}
          <ChevronRight size={18} className="inline ml-2" />
        </button>
      </div>
    </div>
  )
}

function ApiKeyStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { t } = useTranslation()

  const providers = [
    { id: 'openai', name: 'OpenAI', models: ['gpt-4o', 'gpt-4o-mini'] },
    { id: 'anthropic', name: 'Anthropic', models: ['claude-3-5-sonnet', 'claude-3-haiku'] },
    { id: 'gemini', name: 'Google Gemini', models: ['gemini-2.5-pro', 'gemini-2.5-flash'] },
    { id: 'deepseek', name: 'DeepSeek', models: ['deepseek-chat'] },
  ]

  return (
    <div>
      <div className="text-center mb-8">
        <Key size={48} className="text-primary-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t('onboarding.apiKey.title')}</h2>
        <p className="text-gray-500">{t('onboarding.apiKey.subtitle')}</p>
      </div>

      <div className="space-y-4 mb-6">
        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
          <p className="text-sm text-blue-800">{t('onboarding.apiKey.description')}</p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {providers.map((provider) => (
            <div
              key={provider.id}
              className="p-3 border border-gray-200 rounded-lg hover:border-primary-300 cursor-pointer transition-colors"
            >
              <p className="font-medium text-gray-900">{provider.name}</p>
              <p className="text-xs text-gray-400 mt-1">
                {provider.models.slice(0, 2).join(', ')}
              </p>
            </div>
          ))}
        </div>

        <div className="p-4 bg-amber-50 rounded-lg border border-amber-200">
          <p className="text-sm text-amber-800">{t('onboarding.apiKey.envPlaceholder')}</p>
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="btn-ghost px-6 py-3">
          <ChevronLeft size={18} className="inline mr-2" />
          {t('app.back')}
        </button>
        <button onClick={onNext} className="btn-primary px-8 py-3">
          {t('app.next')}
          <ChevronRight size={18} className="inline ml-2" />
        </button>
      </div>
    </div>
  )
}

function ProjectStep({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const { t } = useTranslation()
  const [projectName, setProjectName] = useState('')
  const [sourceLang, setSourceLang] = useState('ja')
  const [targetLang, setTargetLang] = useState('zh-CN')

  const languages = [
    { code: 'ja', name: 'Japanese' },
    { code: 'ko', name: 'Korean' },
    { code: 'zh-CN', name: 'Chinese (Simplified)' },
    { code: 'zh-TW', name: 'Chinese (Traditional)' },
    { code: 'en', name: 'English' },
  ]

  return (
    <div>
      <div className="text-center mb-8">
        <Database size={48} className="text-primary-500 mx-auto mb-4" />
        <h2 className="text-xl font-bold text-gray-900 mb-2">{t('onboarding.project.title')}</h2>
        <p className="text-gray-500">{t('onboarding.project.subtitle')}</p>
      </div>

      <div className="space-y-4 mb-6">
        <div>
          <label className="label">{t('onboarding.project.projectName')}</label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder={t('projects.form.namePlaceholder')}
            className="input"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">{t('onboarding.project.sourceLang')}</label>
            <select
              value={sourceLang}
              onChange={(e) => setSourceLang(e.target.value)}
              className="input"
            >
              {languages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">{t('onboarding.project.targetLang')}</label>
            <select
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              className="input"
            >
              {languages.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.name}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      <div className="flex justify-between">
        <button onClick={onBack} className="btn-ghost px-6 py-3">
          <ChevronLeft size={18} className="inline mr-2" />
          {t('app.back')}
        </button>
        <button onClick={onNext} className="btn-primary px-8 py-3">
          {t('app.next')}
          <ChevronRight size={18} className="inline ml-2" />
        </button>
      </div>
    </div>
  )
}

function CompleteStep({ onComplete }: { onComplete: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center">
      <div className="w-20 h-20 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-6">
        <CheckCircle size={48} className="text-green-500" />
      </div>
      <h2 className="text-2xl font-bold text-gray-900 mb-2">{t('onboarding.complete.title')}</h2>
      <p className="text-gray-500 mb-8">{t('onboarding.complete.description')}</p>

      <div className="flex flex-col sm:flex-row gap-3 justify-center">
        <button onClick={onComplete} className="btn-primary px-8 py-3">
          {t('onboarding.complete.startTranslating')}
        </button>
        <a href="#/settings" className="btn-secondary px-8 py-3">
          {t('onboarding.complete.configureMore')}
        </a>
      </div>
    </div>
  )
}