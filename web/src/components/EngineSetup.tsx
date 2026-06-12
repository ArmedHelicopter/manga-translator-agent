import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Download, CheckCircle, XCircle, Loader2, Package } from 'lucide-react'
import { engineApi, installEngineStream, type EngineStatus } from '../api'

interface EngineSetupProps {
  /** Rendered once the engine is ready. */
  children: React.ReactNode
}

/**
 * Gates its children behind the heavy translation-engine dependencies.
 * On first use (deps missing) it offers a one-click online install with a
 * live log; once ready, it renders the children unchanged.
 */
export default function EngineSetup({ children }: EngineSetupProps) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<EngineStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [installing, setInstalling] = useState(false)
  const [log, setLog] = useState<string[]>([])
  const [failed, setFailed] = useState(false)
  const logEndRef = useRef<HTMLDivElement>(null)
  const closeRef = useRef<(() => void) | null>(null)

  const refreshStatus = async () => {
    try {
      setLoading(true)
      const s = await engineApi.status()
      setStatus(s)
    } catch {
      setStatus(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshStatus()
    return () => {
      if (closeRef.current) closeRef.current()
    }
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [log])

  const handleInstall = () => {
    setInstalling(true)
    setFailed(false)
    setLog([])
    closeRef.current = installEngineStream({
      onLog: (line) => setLog((prev) => [...prev, line]),
      onDone: () => {
        setInstalling(false)
        refreshStatus()
      },
      onError: () => {
        setInstalling(false)
        setFailed(true)
      },
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="w-6 h-6 text-primary-500 animate-spin" />
      </div>
    )
  }

  // Engine ready (or status unavailable but we don't want to block) -> passthrough.
  if (status?.ready) {
    return <>{children}</>
  }

  return (
    <div className="max-w-2xl mx-auto py-8">
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-8">
        <div className="flex items-center gap-3 mb-2">
          <div className="w-11 h-11 rounded-xl bg-primary-50 flex items-center justify-center">
            <Package className="w-6 h-6 text-primary-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">
              {t('engine.setupTitle')}
            </h2>
            <p className="text-sm text-gray-500">{t('engine.setupSubtitle')}</p>
          </div>
        </div>

        <p className="text-sm text-gray-600 mt-4 mb-5">
          {t('engine.setupDescription')}
        </p>

        {/* Dependency checklist */}
        <ul className="space-y-2 mb-6">
          {status?.dependencies.map((dep) => (
            <li
              key={dep.requirement}
              className="flex items-center justify-between text-sm rounded-lg border border-gray-100 px-3 py-2"
            >
              <span className="text-gray-700">{dep.label}</span>
              {dep.installed ? (
                <span className="flex items-center gap-1 text-green-600">
                  <CheckCircle className="w-4 h-4" /> {t('engine.installed')}
                </span>
              ) : (
                <span className="text-gray-400">{t('engine.notInstalled')}</span>
              )}
            </li>
          ))}
        </ul>

        {/* Action */}
        {!installing && (
          <button
            onClick={handleInstall}
            className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 text-white font-medium rounded-xl px-4 py-3 transition-colors"
          >
            <Download className="w-5 h-5" />
            {failed ? t('engine.retry') : t('engine.installNow')}
          </button>
        )}

        {installing && (
          <div className="flex items-center justify-center gap-2 text-primary-600 font-medium py-3">
            <Loader2 className="w-5 h-5 animate-spin" />
            {t('engine.installing')}
          </div>
        )}

        {failed && (
          <div className="flex items-center gap-2 text-red-600 text-sm mt-3">
            <XCircle className="w-4 h-4" />
            {t('engine.installFailed')}
          </div>
        )}

        {/* Live log */}
        {log.length > 0 && (
          <div className="mt-5">
            <div className="text-xs text-gray-400 mb-1">{t('engine.installLog')}</div>
            <div className="bg-gray-900 text-gray-100 text-xs font-mono rounded-lg p-3 max-h-64 overflow-y-auto">
              {log.map((line, i) => (
                <div key={i} className="whitespace-pre-wrap break-all">
                  {line}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
