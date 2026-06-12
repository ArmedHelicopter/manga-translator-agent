import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import {
  Server,
  Globe,
  RefreshCw,
  Info,
  Play,
  Square,
} from 'lucide-react'
import clsx from 'clsx'

const languages = [
  { code: 'en', name: 'English' },
  { code: 'zh', name: '中文' },
]

export default function SettingsPage() {
  const { t, i18n } = useTranslation()
  const {
    backendHost,
    backendPort,
    setBackendConfig,
    setOnboardingComplete,
  } = useAppStore()

  const [host, setHost] = useState(backendHost)
  const [port, setPort] = useState(backendPort)
  const [backendRunning, setBackendRunning] = useState(false)
  const [autoStart, setAutoStart] = useState(false)

  const handleSaveBackend = () => {
    setBackendConfig(host, port)
  }

  const handleResetTutorial = () => {
    setOnboardingComplete(false)
  }

  const handleLanguageChange = (lang: string) => {
    i18n.changeLanguage(lang)
    localStorage.setItem('language', lang)
  }

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('settings.title')}</h1>

      <div className="space-y-6">
        {/* General Settings */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Globe size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('settings.general.title')}
            </h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="label">{t('settings.general.language')}</label>
              <select
                value={i18n.language}
                onChange={(e) => handleLanguageChange(e.target.value)}
                className="input max-w-xs"
              >
                {languages.map((lang) => (
                  <option key={lang.code} value={lang.code}>
                    {lang.name}
                  </option>
                ))}
              </select>
            </div>

            <label className="flex items-center gap-3">
              <input
                type="checkbox"
                checked={autoStart}
                onChange={(e) => setAutoStart(e.target.checked)}
                className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span className="text-sm text-gray-700">
                {t('settings.general.autoStart')}
              </span>
            </label>
          </div>
        </div>

        {/* Backend Settings */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Server size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('settings.backend.title')}
            </h2>
          </div>

          <div className="space-y-4">
            <div className="flex items-center gap-4 mb-4">
              <span className="text-sm text-gray-500">{t('settings.backend.status')}:</span>
              <span
                className={clsx(
                  'px-3 py-1 rounded-full text-sm font-medium',
                  backendRunning
                    ? 'bg-green-100 text-green-600'
                    : 'bg-gray-100 text-gray-600'
                )}
              >
                {backendRunning ? t('settings.backend.running') : t('settings.backend.stopped')}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="label">{t('settings.backend.host')}</label>
                <input
                  type="text"
                  value={host}
                  onChange={(e) => setHost(e.target.value)}
                  className="input"
                />
              </div>
              <div>
                <label className="label">{t('settings.backend.port')}</label>
                <input
                  type="number"
                  value={port}
                  onChange={(e) => setPort(parseInt(e.target.value) || 8000)}
                  className="input"
                />
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button
                onClick={() => setBackendRunning(true)}
                disabled={backendRunning}
                className="btn-primary flex items-center gap-2"
              >
                <Play size={18} />
                {t('settings.backend.start')}
              </button>
              <button
                onClick={() => setBackendRunning(false)}
                disabled={!backendRunning}
                className="btn-secondary flex items-center gap-2"
              >
                <Square size={18} />
                {t('settings.backend.stop')}
              </button>
              <button onClick={handleSaveBackend} className="btn-secondary">
                {t('app.save')}
              </button>
            </div>
          </div>
        </div>

        {/* Reset Settings */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <RefreshCw size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('settings.reset.title')}
            </h2>
          </div>

          <div className="space-y-4">
            <div className="p-4 bg-gray-50 rounded-lg">
              <h3 className="font-medium text-gray-900 mb-1">
                {t('settings.reset.resetTutorial')}
              </h3>
              <p className="text-sm text-gray-500 mb-3">
                {t('settings.reset.resetTutorialDesc')}
              </p>
              <button onClick={handleResetTutorial} className="btn-secondary">
                {t('settings.reset.resetTutorial')}
              </button>
            </div>
          </div>
        </div>

        {/* About */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Info size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('settings.about.title')}
            </h2>
          </div>

          <div className="space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">{t('settings.about.version')}</span>
              <span className="font-medium">1.0.0</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">React</span>
              <span className="font-medium">18.x</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">Python</span>
              <span className="font-medium">3.10+</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}