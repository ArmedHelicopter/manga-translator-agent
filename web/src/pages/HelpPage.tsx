import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import {
  HelpCircle,
  Book,
  Keyboard,
  FileText,
  RefreshCw,
  ExternalLink,
  ChevronRight,
} from 'lucide-react'

export default function HelpPage() {
  const { t } = useTranslation()
  const { setOnboardingComplete } = useAppStore()

  const handleShowTutorial = () => {
    setOnboardingComplete(false)
  }

  const faqs = [
    {
      q: 'How do I get started?',
      a: 'First, configure your API keys in the Provider settings. Then create a project and start translating.',
    },
    {
      q: 'What providers are supported?',
      a: 'OpenAI, Anthropic, Google Gemini, DeepSeek, Ollama, LM Studio, vLLM, OpenRouter, and llama.cpp.',
    },
    {
      q: 'How does the translation work?',
      a: 'The pipeline goes through multiple stages: OCR, Vision Enrichment, Speaker Attribution, Character Attribution, Translation, QA, and Rendering.',
    },
    {
      q: 'What is the difference between Manga and Novel mode?',
      a: 'Manga mode uses full pipeline with OCR and visual analysis. Novel mode uses simplified text-based translation.',
    },
    {
      q: 'How do I configure fallback providers?',
      a: 'In Provider settings, you can set primary, fallback, and local providers for each stage. If primary fails, fallback is used.',
    },
  ]

  const shortcuts = [
    { keys: ['Ctrl', 'N'], action: 'New project' },
    { keys: ['Ctrl', 'O'], action: 'Open folder' },
    { keys: ['Ctrl', 'S'], action: 'Save settings' },
    { keys: ['Ctrl', ','], action: 'Open settings' },
    { keys: ['Esc'], action: 'Close modal' },
  ]

  return (
    <div className="max-w-3xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('help.title')}</h1>

      <div className="space-y-6">
        {/* Quick Start */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Book size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('help.quickStart')}
            </h2>
          </div>

          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-primary-100 text-primary-600 flex items-center justify-center text-sm font-medium flex-shrink-0">
                1
              </div>
              <div>
                <p className="font-medium text-gray-900">Configure API Providers</p>
                <p className="text-sm text-gray-500">
                  Go to Providers page and add your API keys
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-primary-100 text-primary-600 flex items-center justify-center text-sm font-medium flex-shrink-0">
                2
              </div>
              <div>
                <p className="font-medium text-gray-900">Create a Project</p>
                <p className="text-sm text-gray-500">
                  Set source and target languages for your translation
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-primary-100 text-primary-600 flex items-center justify-center text-sm font-medium flex-shrink-0">
                3
              </div>
              <div>
                <p className="font-medium text-gray-900">Add Characters & Terms</p>
                <p className="text-sm text-gray-500">
                  Build your memory database for consistent translations
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="w-6 h-6 rounded-full bg-primary-100 text-primary-600 flex items-center justify-center text-sm font-medium flex-shrink-0">
                4
              </div>
              <div>
                <p className="font-medium text-gray-900">Start Translating</p>
                <p className="text-sm text-gray-500">
                  Select input folder and click Start Translation
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* FAQ */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <HelpCircle size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">{t('help.faq')}</h2>
          </div>

          <div className="space-y-4">
            {faqs.map((faq, i) => (
              <div key={i} className="border-b border-gray-100 last:border-0 pb-4 last:pb-0">
                <p className="font-medium text-gray-900 mb-1">{faq.q}</p>
                <p className="text-sm text-gray-500">{faq.a}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Keyboard Shortcuts */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Keyboard size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">
              {t('help.keyboard')}
            </h2>
          </div>

          <div className="space-y-2">
            {shortcuts.map((shortcut, i) => (
              <div key={i} className="flex items-center justify-between py-2">
                <span className="text-sm text-gray-600">{shortcut.action}</span>
                <div className="flex items-center gap-1">
                  {shortcut.keys.map((key, j) => (
                    <kbd
                      key={j}
                      className="px-2 py-1 bg-gray-100 rounded text-xs font-mono text-gray-700"
                    >
                      {key}
                    </kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Links */}
        <div className="card p-6">
          <div className="space-y-3">
            <a
              href="#"
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <FileText size={18} className="text-gray-400" />
                <span className="font-medium text-gray-700">
                  {t('help.changelog')}
                </span>
              </div>
              <ChevronRight size={18} className="text-gray-400" />
            </a>
            <a
              href="#"
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <ExternalLink size={18} className="text-gray-400" />
                <span className="font-medium text-gray-700">Documentation</span>
              </div>
              <ChevronRight size={18} className="text-gray-400" />
            </a>
            <button
              onClick={handleShowTutorial}
              className="w-full flex items-center justify-between p-3 bg-primary-50 rounded-lg hover:bg-primary-100 transition-colors"
            >
              <div className="flex items-center gap-3">
                <RefreshCw size={18} className="text-primary-500" />
                <span className="font-medium text-primary-700">
                  {t('help.showTutorial')}
                </span>
              </div>
              <ChevronRight size={18} className="text-primary-400" />
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}