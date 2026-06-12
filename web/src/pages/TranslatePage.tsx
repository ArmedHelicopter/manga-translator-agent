import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../store'
import { translateApi, createProgressStream } from '../api'
import { FolderOpen, Play, Square, Image, FileText } from 'lucide-react'
import clsx from 'clsx'
import EngineSetup from '../components/EngineSetup'

export default function TranslatePage() {
  const { t } = useTranslation()
  const { projectId } = useParams()
  const { selectedProjectId, isTranslating, setIsTranslating } = useAppStore()

  const [inputPath, setInputPath] = useState('')
  const [mode, setMode] = useState<'manga' | 'novel'>('manga')
  const [format] = useState('images')
  const [progress, setProgress] = useState<{
    stage: string
    progress: number
    elapsed: number
    status: string
  } | null>(null)

  const effectiveProjectId = projectId || selectedProjectId

  useEffect(() => {
    let cleanup: (() => void) | undefined

    if (isTranslating) {
      cleanup = createProgressStream((data: unknown) => {
        const p = data as { stage?: string; progress?: number; elapsed?: number; status?: string }
        setProgress({
          stage: p.stage || 'unknown',
          progress: p.progress || 0,
          elapsed: p.elapsed || 0,
          status: p.status || 'running',
        })
      })
    }

    return () => {
      if (cleanup) cleanup()
    }
  }, [isTranslating])

  const handleStartTranslate = async () => {
    if (!inputPath.trim()) return
    if (!effectiveProjectId) return

    try {
      setIsTranslating(true)
      await translateApi.start(effectiveProjectId, inputPath, { mode, format })
    } catch (error) {
      console.error('Failed to start translation:', error)
      setIsTranslating(false)
    }
  }

  const handleStopTranslate = async () => {
    try {
      await translateApi.stop()
      setIsTranslating(false)
      setProgress(null)
    } catch (error) {
      console.error('Failed to stop translation:', error)
    }
  }

  const stages = [
    { key: 'format', label: t('translate.stages.format') },
    { key: 'ocr', label: t('translate.stages.ocr') },
    { key: 'vision', label: t('translate.stages.vision') },
    { key: 'speaker', label: t('translate.stages.speaker') },
    { key: 'character', label: t('translate.stages.character') },
    { key: 'translation', label: t('translate.stages.translation') },
    { key: 'qa', label: t('translate.stages.qa') },
    { key: 'render', label: t('translate.stages.render') },
    { key: 'output', label: t('translate.stages.output') },
  ]

  return (
    <EngineSetup>
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('translate.title')}</h1>

      {/* Input Selection */}
      <div className="card p-6 mb-6">
        <h2 className="section-title">{t('translate.selectInput')}</h2>

        <div className="space-y-4">
          {/* Mode Selection */}
          <div className="flex gap-4">
            <button
              onClick={() => setMode('manga')}
              className={clsx(
                'flex-1 p-4 rounded-xl border-2 transition-all flex items-center gap-3',
                mode === 'manga'
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300'
              )}
            >
              <Image size={24} className={mode === 'manga' ? 'text-primary-500' : 'text-gray-400'} />
              <div className="text-left">
                <p className="font-medium text-gray-900">{t('translate.mode.manga')}</p>
                <p className="text-sm text-gray-500">Images, PDF, CBZ, EPUB</p>
              </div>
            </button>
            <button
              onClick={() => setMode('novel')}
              className={clsx(
                'flex-1 p-4 rounded-xl border-2 transition-all flex items-center gap-3',
                mode === 'novel'
                  ? 'border-primary-500 bg-primary-50'
                  : 'border-gray-200 hover:border-gray-300'
              )}
            >
              <FileText
                size={24}
                className={mode === 'novel' ? 'text-primary-500' : 'text-gray-400'}
              />
              <div className="text-left">
                <p className="font-medium text-gray-900">{t('translate.mode.novel')}</p>
                <p className="text-sm text-gray-500">EPUB, TXT, MOBI</p>
              </div>
            </button>
          </div>

          {/* Folder Path Input */}
          <div>
            <label className="label">{t('translate.folderPath')}</label>
            <div className="flex gap-3">
              <div className="flex-1 relative">
                <FolderOpen
                  size={18}
                  className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
                />
                <input
                  type="text"
                  value={inputPath}
                  onChange={(e) => setInputPath(e.target.value)}
                  placeholder={t('translate.selectFolder')}
                  className="input pl-10"
                />
              </div>
              <button className="btn-secondary">{t('translate.browse')}</button>
            </div>
          </div>

          {/* Start Button */}
          <div className="flex justify-end">
            {isTranslating ? (
              <button
                onClick={handleStopTranslate}
                className="px-6 py-3 bg-red-500 text-white rounded-lg font-medium hover:bg-red-600 transition-colors flex items-center gap-2"
              >
                <Square size={18} />
                {t('translate.stopTranslate')}
              </button>
            ) : (
              <button
                onClick={handleStartTranslate}
                disabled={!inputPath.trim() || !effectiveProjectId}
                className="btn-primary flex items-center gap-2"
              >
                <Play size={18} />
                {t('translate.startTranslate')}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Progress Display */}
      {isTranslating && (
        <div className="card p-6">
          <h2 className="section-title">{t('translate.progress.title')}</h2>

          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span>{progress?.stage || 'Initializing...'}</span>
              <span>{progress?.progress || 0}%</span>
            </div>
            <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-primary-500 to-accent-500 transition-all duration-300"
                style={{ width: `${progress?.progress || 0}%` }}
              />
            </div>
          </div>

          {/* Stage Timeline */}
          <div className="relative">
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
            <div className="space-y-4">
              {stages.map((stage, index) => {
                const stageProgress = progress?.stage === stage.key ? progress.progress : 0
                const isCompleted = index < stages.findIndex((s) => s.key === progress?.stage)
                const isCurrent = progress?.stage === stage.key

                return (
                  <div key={stage.key} className="relative flex items-center gap-4 pl-8">
                    <div
                      className={clsx(
                        'absolute left-2 w-4 h-4 rounded-full border-2 bg-white',
                        isCompleted && 'bg-primary-500 border-primary-500',
                        isCurrent && 'border-primary-500 ring-4 ring-primary-100',
                        !isCompleted && !isCurrent && 'border-gray-300'
                      )}
                    />
                    <div className="flex-1 py-2">
                      <p
                        className={clsx(
                          'font-medium',
                          isCompleted && 'text-primary-600',
                          isCurrent && 'text-gray-900',
                          !isCompleted && !isCurrent && 'text-gray-400'
                        )}
                      >
                        {stage.label}
                      </p>
                      {isCurrent && (
                        <div className="mt-1 h-1 bg-gray-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-primary-500"
                            style={{ width: `${stageProgress}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Elapsed Time */}
          <div className="mt-6 pt-4 border-t border-gray-100 flex justify-between text-sm text-gray-500">
            <span>{t('translate.progress.elapsed')}: {Math.floor((progress?.elapsed || 0) / 60)}m {(progress?.elapsed || 0) % 60}s</span>
          </div>
        </div>
      )}
    </div>
    </EngineSetup>
  )
}