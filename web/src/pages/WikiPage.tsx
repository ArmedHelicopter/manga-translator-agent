import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAppStore } from '../store'
import { Download, RefreshCw, FolderOpen, Clock, FileJson, FileText } from 'lucide-react'

export default function WikiPage() {
  const { t } = useTranslation()
  const { projectId } = useParams()
  const { selectedProjectId } = useAppStore()
  const [syncing, setSyncing] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [lastExport, setLastExport] = useState<string | null>(null)
  const [syncDirection, setSyncDirection] = useState<'toWiki' | 'fromWiki'>('toWiki')

  const effectiveProjectId = projectId || selectedProjectId

  const handleSync = async () => {
    if (!effectiveProjectId) return
    try {
      setSyncing(true)
      // Simulated sync - would call backend API
      await new Promise((resolve) => setTimeout(resolve, 1000))
    } catch (error) {
      console.error('Failed to sync:', error)
    } finally {
      setSyncing(false)
    }
  }

  const handleExport = async (_format: 'json' | 'markdown') => {
    if (!effectiveProjectId) return
    try {
      setExporting(true)
      // Simulated export - would call backend API
      await new Promise((resolve) => setTimeout(resolve, 500))
      setLastExport(new Date().toLocaleString())
    } catch (error) {
      console.error('Failed to export:', error)
    } finally {
      setExporting(false)
    }
  }

  if (!effectiveProjectId) {
    return (
      <div className="text-center py-12">
        <FolderOpen size={48} className="text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">{t('projects.noProjects')}</p>
      </div>
    )
  }

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">{t('wiki.title')}</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Sync Section */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <RefreshCw size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">{t('wiki.sync')}</h2>
          </div>

          <div className="space-y-4">
            <div>
              <label className="label">{t('wiki.syncDirection.toWiki')}</label>
              <select
                value={syncDirection}
                onChange={(e) => setSyncDirection(e.target.value as 'toWiki' | 'fromWiki')}
                className="input"
              >
                <option value="toWiki">{t('wiki.syncDirection.toWiki')}</option>
                <option value="fromWiki">{t('wiki.syncDirection.fromWiki')}</option>
              </select>
            </div>

            <div className="p-4 bg-gray-50 rounded-lg">
              <p className="text-sm text-gray-600 mb-2">
                {syncDirection === 'toWiki'
                  ? 'Sync state to wiki. Changes in memory will be reflected in wiki files.'
                  : 'Sync wiki to state. Changes in wiki files will be reflected in memory.'}
              </p>
            </div>

            <button
              onClick={handleSync}
              disabled={syncing}
              className="btn-primary w-full flex items-center justify-center gap-2"
            >
              {syncing ? (
                <RefreshCw size={18} className="animate-spin" />
              ) : (
                <RefreshCw size={18} />
              )}
              {syncing ? t('app.loading') : t('wiki.sync')}
            </button>
          </div>
        </div>

        {/* Export Section */}
        <div className="card p-6">
          <div className="flex items-center gap-3 mb-4">
            <Download size={24} className="text-primary-500" />
            <h2 className="text-lg font-semibold text-gray-900">{t('wiki.export')}</h2>
          </div>

          <div className="space-y-4">
            <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
              <div className="flex items-center gap-3">
                <Clock size={18} className="text-gray-400" />
                <div>
                  <p className="text-sm text-gray-500">{t('wiki.lastExport')}</p>
                  <p className="font-medium text-gray-900">
                    {lastExport || t('wiki.never')}
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <p className="label">{t('wiki.exportFormat')}</p>
              <div className="grid grid-cols-2 gap-3">
                <button
                  onClick={() => handleExport('json')}
                  disabled={exporting}
                  className="btn-secondary flex items-center justify-center gap-2"
                >
                  <FileJson size={18} />
                  JSON
                </button>
                <button
                  onClick={() => handleExport('markdown')}
                  disabled={exporting}
                  className="btn-secondary flex items-center justify-center gap-2"
                >
                  <FileText size={18} />
                  Markdown
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Wiki Preview */}
      <div className="card p-6 mt-6">
        <h2 className="section-title">Wiki Structure</h2>
        <div className="bg-gray-50 rounded-lg p-4 font-mono text-sm">
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <FolderOpen size={16} className="text-gray-400" />
              <span className="text-gray-700">project/</span>
            </div>
            <div className="pl-6 space-y-2 text-gray-600">
              <div className="flex items-center gap-2">
                <FolderOpen size={14} />
                <span>characters/</span>
                <span className="text-gray-400 text-xs">character profiles</span>
              </div>
              <div className="flex items-center gap-2">
                <FolderOpen size={14} />
                <span>terms/</span>
                <span className="text-gray-400 text-xs">terminology database</span>
              </div>
              <div className="flex items-center gap-2">
                <FolderOpen size={14} />
                <span>scenes/</span>
                <span className="text-gray-400 text-xs">scene descriptions</span>
              </div>
              <div className="flex items-center gap-2">
                <FolderOpen size={14} />
                <span>worldbook/</span>
                <span className="text-gray-400 text-xs">world building info</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}