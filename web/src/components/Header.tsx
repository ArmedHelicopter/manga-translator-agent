import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import { Globe, HelpCircle, Server } from 'lucide-react'
import clsx from 'clsx'

const languages = [
  { code: 'en', name: 'English' },
  { code: 'zh', name: '中文' },
]

export default function Header() {
  const { t, i18n } = useTranslation()
  const { backendHost, backendPort } = useAppStore()

  const changeLanguage = (lang: string) => {
    i18n.changeLanguage(lang)
    localStorage.setItem('language', lang)
  }

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 sticky top-0 z-50">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-gradient-to-br from-primary-500 to-accent-500 rounded-lg flex items-center justify-center">
          <span className="text-white font-bold text-sm">M</span>
        </div>
        <h1 className="text-lg font-semibold text-gray-900">
          {t('app.title')}
        </h1>
      </div>

      <div className="flex items-center gap-4">
        {/* Backend Status */}
        <div className="flex items-center gap-2 text-sm">
          <Server size={16} className="text-gray-400" />
          <span className="text-gray-500">
            {backendHost}:{backendPort}
          </span>
        </div>

        {/* Language Switcher */}
        <div className="relative group">
          <button className="flex items-center gap-2 px-3 py-1.5 rounded-lg hover:bg-gray-100 transition-colors">
            <Globe size={18} className="text-gray-500" />
            <span className="text-sm font-medium text-gray-700">
              {languages.find((l) => l.code === i18n.language)?.name || 'English'}
            </span>
          </button>
          <div className="absolute right-0 mt-1 w-32 bg-white rounded-lg shadow-lg border border-gray-200 opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all">
            {languages.map((lang) => (
              <button
                key={lang.code}
                onClick={() => changeLanguage(lang.code)}
                className={clsx(
                  'w-full px-4 py-2 text-left text-sm hover:bg-gray-50 first:rounded-t-lg last:rounded-b-lg',
                  i18n.language === lang.code && 'bg-primary-50 text-primary-700'
                )}
              >
                {lang.name}
              </button>
            ))}
          </div>
        </div>

        {/* Help */}
        <a
          href="#/help"
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          title={t('nav.help')}
        >
          <HelpCircle size={20} className="text-gray-500" />
        </a>
      </div>
    </header>
  )
}