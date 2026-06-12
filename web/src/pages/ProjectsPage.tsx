import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useAppStore, type Project } from '../store'
import { projectsApi } from '../api'
import { Plus, Trash2, FolderOpen, Users, BookOpen, Clock } from 'lucide-react'
import clsx from 'clsx'

export default function ProjectsPage() {
  const { t } = useTranslation()
  const { projects, setProjects, addProject, deleteProject, selectedProjectId, selectProject } =
    useAppStore()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadProjects()
  }, [])

  const loadProjects = async () => {
    try {
      setLoading(true)
      const response = await projectsApi.list()
      setProjects(response.projects)
    } catch (error) {
      console.error('Failed to load projects:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleCreate = async (data: { name: string; source_lang: string; target_lang: string }) => {
    try {
      const project = await projectsApi.create(data)
      addProject(project)
      setShowCreateModal(false)
    } catch (error) {
      console.error('Failed to create project:', error)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm(t('projects.deleteConfirm'))) return
    try {
      await projectsApi.delete(id)
      deleteProject(id)
    } catch (error) {
      console.error('Failed to delete project:', error)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('projects.title')}</h1>
        <button
          onClick={() => setShowCreateModal(true)}
          className="btn-primary flex items-center gap-2"
        >
          <Plus size={18} />
          {t('projects.create')}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : projects.length === 0 ? (
        <EmptyState onCreate={() => setShowCreateModal(true)} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <ProjectCard
              key={project.id}
              project={project}
              isSelected={selectedProjectId === project.id}
              onSelect={() => selectProject(project.id)}
              onDelete={() => handleDelete(project.id)}
            />
          ))}
        </div>
      )}

      {showCreateModal && (
        <CreateProjectModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreate}
        />
      )}
    </div>
  )
}

interface ProjectCardProps {
  project: Project
  isSelected: boolean
  onSelect: () => void
  onDelete: () => void
}

function ProjectCard({ project, isSelected, onSelect, onDelete }: ProjectCardProps) {
  return (
    <div
      onClick={onSelect}
      className={clsx(
        'card p-4 cursor-pointer transition-all hover:shadow-md',
        isSelected && 'ring-2 ring-primary-500'
      )}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-primary-100 rounded-lg flex items-center justify-center">
            <FolderOpen size={20} className="text-primary-600" />
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{project.name}</h3>
            <p className="text-sm text-gray-500">
              {project.source_lang} → {project.target_lang}
            </p>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onDelete()
          }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500 transition-colors"
        >
          <Trash2 size={16} />
        </button>
      </div>

      <div className="flex items-center gap-4 text-sm text-gray-500">
        <div className="flex items-center gap-1">
          <Users size={14} />
          <span>{project.character_count}</span>
        </div>
        <div className="flex items-center gap-1">
          <BookOpen size={14} />
          <span>{project.term_count}</span>
        </div>
        <div className="flex items-center gap-1">
          <Clock size={14} />
          <span>{new Date(project.updated_at).toLocaleDateString()}</span>
        </div>
      </div>
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center py-12">
      <FolderOpen size={48} className="text-gray-300 mx-auto mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">{t('projects.noProjects')}</h3>
      <p className="text-gray-500 mb-6">{t('projects.createFirst')}</p>
      <button onClick={onCreate} className="btn-primary">
        <Plus size={18} className="inline mr-2" />
        {t('projects.create')}
      </button>
    </div>
  )
}

interface CreateProjectModalProps {
  onClose: () => void
  onCreate: (data: { name: string; source_lang: string; target_lang: string }) => void
}

function CreateProjectModal({ onClose, onCreate }: CreateProjectModalProps) {
  const { t } = useTranslation()
  const [name, setName] = useState('')
  const [sourceLang, setSourceLang] = useState('ja')
  const [targetLang, setTargetLang] = useState('zh-CN')

  const languages = [
    { code: 'ja', name: 'Japanese' },
    { code: 'ko', name: 'Korean' },
    { code: 'zh-CN', name: 'Chinese (Simplified)' },
    { code: 'zh-TW', name: 'Chinese (Traditional)' },
    { code: 'en', name: 'English' },
  ]

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onCreate({ name: name.trim(), source_lang: sourceLang, target_lang: targetLang })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-xl p-6 w-full max-w-md mx-4">
        <h2 className="text-xl font-bold text-gray-900 mb-4">{t('projects.create')}</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="label">{t('projects.form.name')}</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('projects.form.namePlaceholder')}
              className="input"
              autoFocus
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('projects.form.sourceLang')}</label>
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
              <label className="label">{t('projects.form.targetLang')}</label>
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