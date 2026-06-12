import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAppStore, type Term } from '../store'
import { termsApi } from '../api'
import { Plus, BookOpen, Edit2, Save, X, AlertCircle } from 'lucide-react'

export default function TermsPage() {
  const { t } = useTranslation()
  const { projectId } = useParams()
  const { terms, selectedProjectId, setTerms, addTerm, updateTerm } = useAppStore()
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const effectiveProjectId = projectId || selectedProjectId

  useEffect(() => {
    if (effectiveProjectId) {
      loadTerms()
    }
  }, [effectiveProjectId])

  const loadTerms = async () => {
    if (!effectiveProjectId) return
    try {
      setLoading(true)
      const response = await termsApi.list(effectiveProjectId)
      setTerms(response.terms)
    } catch (error) {
      console.error('Failed to load terms:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (termId: string, data: Record<string, unknown>) => {
    if (!effectiveProjectId) return
    try {
      const saved = await termsApi.save(effectiveProjectId, termId, data)
      if (editingId === termId) {
        updateTerm(termId, saved)
      } else {
        addTerm(saved)
      }
      setShowForm(false)
      setEditingId(null)
    } catch (error) {
      console.error('Failed to save term:', error)
    }
  }

  const handleNew = () => {
    setEditingId(null)
    setShowForm(true)
  }

  const handleEdit = (termId: string) => {
    setEditingId(termId)
    setShowForm(true)
  }

  const categories = [
    { value: 'character', label: t('terms.categories.character') },
    { value: 'location', label: t('terms.categories.location') },
    { value: 'ability', label: t('terms.categories.ability') },
    { value: 'item', label: t('terms.categories.item') },
    { value: 'organization', label: t('terms.categories.organization') },
    { value: 'cultural', label: t('terms.categories.cultural') },
    { value: 'other', label: t('terms.categories.other') },
  ]

  const strategies = [
    { value: 'literal', label: t('terms.strategies.literal') },
    { value: 'adapt', label: t('terms.strategies.adapt') },
    { value: 'coined', label: t('terms.strategies.coined') },
    { value: 'transliterate', label: t('terms.strategies.transliterate') },
    { value: 'preserve', label: t('terms.strategies.preserve') },
  ]

  if (!effectiveProjectId) {
    return (
      <div className="text-center py-12">
        <BookOpen size={48} className="text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">{t('projects.noProjects')}</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('terms.title')}</h1>
        <button onClick={handleNew} className="btn-primary flex items-center gap-2">
          <Plus size={18} />
          {t('terms.create')}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : terms.length === 0 ? (
        <EmptyState onCreate={handleNew} />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                  {t('terms.form.source')}
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                  {t('terms.form.target')}
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                  {t('terms.form.category')}
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                  {t('terms.form.strategy')}
                </th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">
                  {t('terms.form.frequency')}
                </th>
                <th className="px-4 py-3 text-right text-sm font-medium text-gray-500">
                  {t('batch.job.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {terms.map((term) => (
                <tr key={term.term_id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {term.pending_human_review && (
                        <AlertCircle size={14} className="text-amber-500" />
                      )}
                      <span className="font-medium text-gray-900">{term.term_jp}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-gray-600">{term.term_zh}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 bg-gray-100 rounded text-xs">
                      {t(`terms.categories.${term.cultural_weight}`) || term.cultural_weight}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 bg-blue-50 text-blue-600 rounded text-xs">
                      {t(`terms.strategies.${term.strategy}`) || term.strategy}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{term.frequency}</td>
                  <td className="px-4 py-3 text-right">
                    <button
                      onClick={() => handleEdit(term.term_id)}
                      className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-primary-500"
                    >
                      <Edit2 size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <TermFormModal
          termId={editingId || `term_${Date.now()}`}
          initialData={editingId ? terms.find((t) => t.term_id === editingId) : undefined}
          onSave={handleSave}
          onClose={() => {
            setShowForm(false)
            setEditingId(null)
          }}
          categories={categories}
          strategies={strategies}
        />
      )}
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center py-12">
      <BookOpen size={48} className="text-gray-300 mx-auto mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">{t('terms.noTerms')}</h3>
      <p className="text-gray-500 mb-6">{t('terms.addFirst')}</p>
      <button onClick={onCreate} className="btn-primary">
        <Plus size={18} className="inline mr-2" />
        {t('terms.create')}
      </button>
    </div>
  )
}

interface TermFormModalProps {
  termId: string
  initialData?: Term
  onSave: (id: string, data: Record<string, unknown>) => void
  onClose: () => void
  categories: { value: string; label: string }[]
  strategies: { value: string; label: string }[]
}

function TermFormModal({
  termId,
  initialData,
  onSave,
  onClose,
  categories,
  strategies,
}: TermFormModalProps) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    term_id: initialData?.term_id || termId,
    term_jp: initialData?.term_jp || '',
    term_zh: initialData?.term_zh || '',
    cultural_weight: initialData?.cultural_weight || 'other',
    strategy: initialData?.strategy || 'literal',
    context: '',
    pending_human_review: initialData?.pending_human_review || false,
    frequency: initialData?.frequency || 0,
    candidate_translations: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(form.term_id, {
      ...form,
      candidate_translations: form.candidate_translations.split('\n').filter(Boolean),
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-lg mx-4">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">
            {initialData ? t('app.edit') : t('terms.create')}
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('terms.form.source')}</label>
              <input
                type="text"
                value={form.term_jp}
                onChange={(e) => setForm({ ...form, term_jp: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="label">{t('terms.form.target')}</label>
              <input
                type="text"
                value={form.term_zh}
                onChange={(e) => setForm({ ...form, term_zh: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('terms.form.category')}</label>
              <select
                value={form.cultural_weight}
                onChange={(e) => setForm({ ...form, cultural_weight: e.target.value })}
                className="input"
              >
                {categories.map((c) => (
                  <option key={c.value} value={c.value}>
                    {c.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">{t('terms.form.strategy')}</label>
              <select
                value={form.strategy}
                onChange={(e) => setForm({ ...form, strategy: e.target.value })}
                className="input"
              >
                {strategies.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="label">{t('terms.form.context')}</label>
            <textarea
              value={form.context}
              onChange={(e) => setForm({ ...form, context: e.target.value })}
              className="input min-h-20"
            />
          </div>

          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={form.pending_human_review}
              onChange={(e) => setForm({ ...form, pending_human_review: e.target.checked })}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <span className="text-sm text-gray-700">{t('terms.form.pendingReview')}</span>
          </label>

          <div className="flex justify-end gap-3 pt-4">
            <button type="button" onClick={onClose} className="btn-secondary">
              {t('app.cancel')}
            </button>
            <button type="submit" className="btn-primary flex items-center gap-2">
              <Save size={18} />
              {t('app.save')}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}