import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppStore, type BatchJob } from '../store'
import { batchApi } from '../api'
import { Plus, Play, Pause, Trash2, RotateCcw, CheckCircle, XCircle, Clock } from 'lucide-react'
import clsx from 'clsx'

export default function BatchPage() {
  const { t } = useTranslation()
  const { batchJobs, setBatchJobs, addBatchJob, updateBatchJob, deleteBatchJob } = useAppStore()
  const [showCreateModal, setShowCreateModal] = useState(false)

  useEffect(() => {
    loadJobs()
  }, [])

  const loadJobs = async () => {
    try {
      const response = await batchApi.list()
      setBatchJobs(response.jobs as BatchJob[])
    } catch (error) {
      console.error('Failed to load batch jobs:', error)
    }
  }

  const handleStart = async (jobId: string) => {
    try {
      await batchApi.start(jobId)
      updateBatchJob(jobId, { status: 'running' })
    } catch (error) {
      console.error('Failed to start job:', error)
    }
  }

  const handlePause = async (jobId: string) => {
    try {
      await batchApi.pause(jobId)
      updateBatchJob(jobId, { status: 'paused' })
    } catch (error) {
      console.error('Failed to pause job:', error)
    }
  }

  const handleResume = async (jobId: string) => {
    try {
      await batchApi.resume(jobId)
      updateBatchJob(jobId, { status: 'running' })
    } catch (error) {
      console.error('Failed to resume job:', error)
    }
  }

  const handleDelete = async (jobId: string) => {
    try {
      await batchApi.delete(jobId)
      deleteBatchJob(jobId)
    } catch (error) {
      console.error('Failed to delete job:', error)
    }
  }

  const statusColors = {
    pending: 'bg-gray-100 text-gray-600',
    running: 'bg-blue-100 text-blue-600',
    completed: 'bg-green-100 text-green-600',
    failed: 'bg-red-100 text-red-600',
    paused: 'bg-yellow-100 text-yellow-600',
  }

  const statusIcons = {
    pending: Clock,
    running: Play,
    completed: CheckCircle,
    failed: XCircle,
    paused: Pause,
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('batch.title')}</h1>
        <div className="flex gap-3">
          <button className="btn-secondary flex items-center gap-2">
            <Play size={18} />
            {t('batch.controls.startAll')}
          </button>
          <button className="btn-secondary flex items-center gap-2">
            <Pause size={18} />
            {t('batch.controls.pauseAll')}
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="btn-primary flex items-center gap-2"
          >
            <Plus size={18} />
            {t('batch.create')}
          </button>
        </div>
      </div>

      {batchJobs.length === 0 ? (
        <EmptyState onCreate={() => setShowCreateModal(true)} />
      ) : (
        <div className="space-y-4">
          {batchJobs.map((job) => {
            const StatusIcon = statusIcons[job.status]
            return (
              <div key={job.id} className="card p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div
                      className={clsx(
                        'w-10 h-10 rounded-lg flex items-center justify-center',
                        statusColors[job.status]
                      )}
                    >
                      <StatusIcon size={20} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">{job.name}</h3>
                      <p className="text-sm text-gray-500">{job.input_path}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4">
                    {/* Progress Bar */}
                    <div className="w-32">
                      <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-primary-500 transition-all"
                          style={{ width: `${job.progress}%` }}
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1">{job.progress}%</p>
                    </div>

                    {/* Status Badge */}
                    <span
                      className={clsx(
                        'px-3 py-1 rounded-full text-sm font-medium',
                        statusColors[job.status]
                      )}
                    >
                      {t(`batch.status.${job.status}`)}
                    </span>

                    {/* Actions */}
                    <div className="flex items-center gap-2">
                      {job.status === 'pending' && (
                        <button
                          onClick={() => handleStart(job.id)}
                          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-primary-600"
                        >
                          <Play size={18} />
                        </button>
                      )}
                      {job.status === 'running' && (
                        <button
                          onClick={() => handlePause(job.id)}
                          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-yellow-600"
                        >
                          <Pause size={18} />
                        </button>
                      )}
                      {job.status === 'paused' && (
                        <button
                          onClick={() => handleResume(job.id)}
                          className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 hover:text-primary-600"
                        >
                          <RotateCcw size={18} />
                        </button>
                      )}
                      <button
                        onClick={() => handleDelete(job.id)}
                        className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500"
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  </div>
                </div>

                {job.error && (
                  <div className="mt-3 p-3 bg-red-50 rounded-lg text-sm text-red-700">
                    {job.error}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {showCreateModal && (
        <CreateBatchJobModal onClose={() => setShowCreateModal(false)} onCreate={addBatchJob} />
      )}
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center py-12">
      <Play size={48} className="text-gray-300 mx-auto mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">{t('batch.noJobs')}</h3>
      <p className="text-gray-500 mb-6">{t('batch.createFirst')}</p>
      <button onClick={onCreate} className="btn-primary">
        <Plus size={18} className="inline mr-2" />
        {t('batch.create')}
      </button>
    </div>
  )
}

interface CreateBatchJobModalProps {
  onClose: () => void
  onCreate: (job: BatchJob) => void
}

function CreateBatchJobModal({ onClose, onCreate }: CreateBatchJobModalProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [inputPath, setInputPath] = useState('')
  const [outputPath, setOutputPath] = useState('')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !inputPath.trim()) return

    onCreate({
      id: `job_${Date.now()}`,
      name: name.trim(),
      input_path: inputPath.trim(),
      output_path: outputPath.trim(),
      status: 'pending',
      progress: 0,
      created_at: new Date().toISOString(),
    })
    onClose()
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-lg mx-4">
        <h2 className="text-xl font-bold text-gray-900 mb-4">{t('batch.create')}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">{t('batch.job.name')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="input"
              autoFocus
            />
          </div>
          <div>
            <label className="label">{t('batch.job.inputPath')}</label>
            <input
              type="text"
              value={inputPath}
              onChange={(e) => setInputPath(e.target.value)}
              className="input"
            />
          </div>
          <div>
            <label className="label">{t('batch.job.outputPath')}</label>
            <input
              type="text"
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
              className="input"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4">
            <button type="button" onClick={onClose} className="btn-secondary">
              {t('app.cancel')}
            </button>
            <button type="submit" className="btn-primary">
              {t('app.create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}