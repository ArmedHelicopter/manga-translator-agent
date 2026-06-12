import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'
import { useAppStore, type Character } from '../store'
import { charactersApi } from '../api'
import { Plus, Users, Edit2, Save, X } from 'lucide-react'
import clsx from 'clsx'

export default function CharactersPage() {
  const { t } = useTranslation()
  const { projectId } = useParams()
  const {
    characters,
    selectedCharacterId,
    selectedProjectId,
    setCharacters,
    addCharacter,
    updateCharacter,
    selectCharacter,
  } = useAppStore()
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const effectiveProjectId = projectId || selectedProjectId

  useEffect(() => {
    if (effectiveProjectId) {
      loadCharacters()
    }
  }, [effectiveProjectId])

  const loadCharacters = async () => {
    if (!effectiveProjectId) return
    try {
      setLoading(true)
      const response = await charactersApi.list(effectiveProjectId)
      setCharacters(response.characters)
    } catch (error) {
      console.error('Failed to load characters:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async (characterId: string, data: Record<string, unknown>) => {
    if (!effectiveProjectId) return
    try {
      const saved = await charactersApi.save(effectiveProjectId, characterId, data)
      if (editingId === characterId) {
        updateCharacter(characterId, saved)
      } else {
        addCharacter(saved)
      }
      setShowForm(false)
      setEditingId(null)
    } catch (error) {
      console.error('Failed to save character:', error)
    }
  }

  const handleNew = () => {
    setEditingId(null)
    setShowForm(true)
  }

  const handleEdit = (characterId: string) => {
    setEditingId(characterId)
    setShowForm(true)
  }

  const archetypes = [
    { value: 'protagonist', label: t('characters.archetypes.protagonist') },
    { value: 'antagonist', label: t('characters.archetypes.antagonist') },
    { value: 'supporting', label: t('characters.archetypes.supporting') },
    { value: 'minor', label: t('characters.archetypes.minor') },
  ]

  if (!effectiveProjectId) {
    return (
      <div className="text-center py-12">
        <Users size={48} className="text-gray-300 mx-auto mb-4" />
        <p className="text-gray-500">{t('projects.noProjects')}</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{t('characters.title')}</h1>
        <button onClick={handleNew} className="btn-primary flex items-center gap-2">
          <Plus size={18} />
          {t('characters.create')}
        </button>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : characters.length === 0 ? (
        <EmptyState onCreate={handleNew} />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {characters.map((character) => (
            <CharacterCard
              key={character.character_id}
              character={character}
              isSelected={selectedCharacterId === character.character_id}
              onSelect={() => selectCharacter(character.character_id)}
              onEdit={() => handleEdit(character.character_id)}
            />
          ))}
        </div>
      )}

      {showForm && (
        <CharacterFormModal
          characterId={editingId || `char_${Date.now()}`}
          initialData={
            editingId
              ? characters.find((c) => c.character_id === editingId)
              : undefined
          }
          onSave={handleSave}
          onClose={() => {
            setShowForm(false)
            setEditingId(null)
          }}
          archetypes={archetypes}
        />
      )}
    </div>
  )
}

interface CharacterCardProps {
  character: Character
  isSelected: boolean
  onSelect: () => void
  onEdit: () => void
}

function CharacterCard({ character, isSelected, onSelect, onEdit }: CharacterCardProps) {
  const { t } = useTranslation()

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
          <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
            <span className="text-blue-600 font-medium">
              {(character.name_jp || character.character_id).charAt(0).toUpperCase()}
            </span>
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">
              {character.name_jp || character.character_id}
            </h3>
            <p className="text-sm text-gray-500">{character.name_zh}</p>
          </div>
        </div>
        <button
          onClick={(e) => {
            e.stopPropagation()
            onEdit()
          }}
          className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-primary-500"
        >
          <Edit2 size={16} />
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className="px-2 py-1 bg-gray-100 rounded text-xs text-gray-600">
          {t(`characters.archetypes.${character.archetype}`) || character.archetype}
        </span>
        <span className="text-xs text-gray-400">
          {character.speech_pattern_count} patterns
        </span>
      </div>
    </div>
  )
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation()

  return (
    <div className="text-center py-12">
      <Users size={48} className="text-gray-300 mx-auto mb-4" />
      <h3 className="text-lg font-medium text-gray-900 mb-2">{t('characters.noCharacters')}</h3>
      <p className="text-gray-500 mb-6">{t('characters.addFirst')}</p>
      <button onClick={onCreate} className="btn-primary">
        <Plus size={18} className="inline mr-2" />
        {t('characters.create')}
      </button>
    </div>
  )
}

interface CharacterFormModalProps {
  characterId: string
  initialData?: Character
  onSave: (id: string, data: Record<string, unknown>) => void
  onClose: () => void
  archetypes: { value: string; label: string }[]
}

function CharacterFormModal({
  characterId,
  initialData,
  onSave,
  onClose,
  archetypes,
}: CharacterFormModalProps) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    character_id: initialData?.character_id || characterId,
    name_jp: initialData?.name_jp || '',
    name_zh: initialData?.name_zh || '',
    archetype: initialData?.archetype || 'supporting',
    catchphrases: '',
    speech_patterns: '',
    tone_spectrum: '',
    translation_notes: '',
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(form.character_id, {
      ...form,
      catchphrases: form.catchphrases.split('\n').filter(Boolean),
      speech_patterns: Object.fromEntries(
        form.speech_patterns.split('\n').map((line) => {
          const [key, ...value] = line.split('=')
          return [key.trim(), value.join('=').trim()]
        })
      ),
      tone_spectrum: Object.fromEntries(
        form.tone_spectrum.split('\n').map((line) => {
          const [key, ...value] = line.split('=')
          return [key.trim(), value.join('=').trim()]
        })
      ),
      translation_notes: Object.fromEntries(
        form.translation_notes.split('\n').map((line) => {
          const [key, ...value] = line.split('=')
          return [key.trim(), value.join('=').trim()]
        })
      ),
    })
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 overflow-y-auto">
      <div className="bg-white rounded-xl p-6 w-full max-w-2xl mx-4 my-8">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-bold text-gray-900">
            {initialData ? t('app.edit') : t('characters.create')}
          </h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('characters.form.id')}</label>
              <input
                type="text"
                value={form.character_id}
                onChange={(e) => setForm({ ...form, character_id: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="label">{t('characters.form.archetype')}</label>
              <select
                value={form.archetype}
                onChange={(e) => setForm({ ...form, archetype: e.target.value })}
                className="input"
              >
                {archetypes.map((a) => (
                  <option key={a.value} value={a.value}>
                    {a.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">{t('characters.form.nameJp')}</label>
              <input
                type="text"
                value={form.name_jp}
                onChange={(e) => setForm({ ...form, name_jp: e.target.value })}
                className="input"
              />
            </div>
            <div>
              <label className="label">{t('characters.form.nameZh')}</label>
              <input
                type="text"
                value={form.name_zh}
                onChange={(e) => setForm({ ...form, name_zh: e.target.value })}
                className="input"
              />
            </div>
          </div>

          <div>
            <label className="label">{t('characters.form.catchphrases')}</label>
            <textarea
              value={form.catchphrases}
              onChange={(e) => setForm({ ...form, catchphrases: e.target.value })}
              className="input min-h-20"
              placeholder="One per line"
            />
          </div>

          <div>
            <label className="label">{t('characters.form.speechPatterns')}</label>
            <textarea
              value={form.speech_patterns}
              onChange={(e) => setForm({ ...form, speech_patterns: e.target.value })}
              className="input min-h-20"
              placeholder="key=value, one per line"
            />
          </div>

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