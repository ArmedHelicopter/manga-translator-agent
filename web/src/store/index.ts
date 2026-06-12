import { create } from 'zustand'
import { persist } from 'zustand/middleware'

// Types
export interface Project {
  id: string
  name: string
  path: string
  source_lang: string
  target_lang: string
  created_at: string
  updated_at: string
  character_count: number
  term_count: number
  scene_count: number
}

export interface ProviderConfig {
  stages: {
    vision: { primary: string; fallback: string; local: string }
    translation: { primary: string; fallback: string; local: string }
    qa: { primary: string; fallback: string; local: string }
  }
  providers: Record<string, ProviderSettings>
  provider_options: string[]
}

export interface ProviderSettings {
  api_key?: string
  base_url?: string
  model?: string
  vision_model?: string
  text_model?: string
  max_tokens?: number
  temperature?: number
  [key: string]: unknown
}

export interface Character {
  character_id: string
  name_jp: string
  name_zh: string
  archetype: string
  speech_pattern_count: number
  catchphrase_count: number
  tone_count: number
  translation_note_count: number
}

export interface CharacterDetail extends Character {
  speech_patterns: Record<string, string>
  catchphrases: string[]
  tone_spectrum: Record<string, string>
  translation_notes: Record<string, string>
}

export interface Term {
  term_id: string
  term_jp: string
  term_zh: string
  cultural_weight: string
  strategy: string
  pending_human_review: boolean
  frequency: number
  candidate_count: number
}

export interface TranslationReport {
  path: string
  entry_count: number
  entries_needing_human_review: number
  avg_confidence: number
  updated_at: string
}

export interface BatchJob {
  id: string
  name: string
  input_path: string
  output_path: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused'
  progress: number
  error?: string
  created_at: string
  completed_at?: string
}

export interface TranslationProgress {
  stage: string
  progress: number
  elapsed: number
  remaining?: number
  status: 'pending' | 'running' | 'completed' | 'failed'
}

// Store types
interface AppState {
  // Onboarding
  hasCompletedOnboarding: boolean
  setOnboardingComplete: (complete: boolean) => void

  // Backend
  backendHost: string
  backendPort: number
  setBackendConfig: (host: string, port: number) => void

  // Projects
  projects: Project[]
  selectedProjectId: string | null
  setProjects: (projects: Project[]) => void
  addProject: (project: Project) => void
  updateProject: (id: string, updates: Partial<Project>) => void
  deleteProject: (id: string) => void
  selectProject: (id: string | null) => void

  // Characters
  characters: Character[]
  selectedCharacterId: string | null
  setCharacters: (characters: Character[]) => void
  addCharacter: (character: Character) => void
  updateCharacter: (id: string, updates: Partial<Character>) => void
  deleteCharacter: (id: string) => void
  selectCharacter: (id: string | null) => void

  // Terms
  terms: Term[]
  setTerms: (terms: Term[]) => void
  addTerm: (term: Term) => void
  updateTerm: (id: string, updates: Partial<Term>) => void
  deleteTerm: (id: string) => void

  // Provider Config
  providerConfig: ProviderConfig | null
  setProviderConfig: (config: ProviderConfig) => void

  // Batch Jobs
  batchJobs: BatchJob[]
  setBatchJobs: (jobs: BatchJob[]) => void
  addBatchJob: (job: BatchJob) => void
  updateBatchJob: (id: string, updates: Partial<BatchJob>) => void
  deleteBatchJob: (id: string) => void

  // Translation Progress
  translationProgress: TranslationProgress | null
  isTranslating: boolean
  setTranslationProgress: (progress: TranslationProgress | null) => void
  setIsTranslating: (translating: boolean) => void

  // UI State
  sidebarCollapsed: boolean
  toggleSidebar: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      // Onboarding
      hasCompletedOnboarding: false,
      setOnboardingComplete: (complete) => set({ hasCompletedOnboarding: complete }),

      // Backend
      backendHost: '127.0.0.1',
      backendPort: 8000,
      setBackendConfig: (host, port) => set({ backendHost: host, backendPort: port }),

      // Projects
      projects: [],
      selectedProjectId: null,
      setProjects: (projects) => set({ projects }),
      addProject: (project) => set((state) => ({ projects: [...state.projects, project] })),
      updateProject: (id, updates) =>
        set((state) => ({
          projects: state.projects.map((p) => (p.id === id ? { ...p, ...updates } : p)),
        })),
      deleteProject: (id) =>
        set((state) => ({
          projects: state.projects.filter((p) => p.id !== id),
          selectedProjectId: state.selectedProjectId === id ? null : state.selectedProjectId,
        })),
      selectProject: (id) => set({ selectedProjectId: id }),

      // Characters
      characters: [],
      selectedCharacterId: null,
      setCharacters: (characters) => set({ characters }),
      addCharacter: (character) => set((state) => ({ characters: [...state.characters, character] })),
      updateCharacter: (id, updates) =>
        set((state) => ({
          characters: state.characters.map((c) =>
            c.character_id === id ? { ...c, ...updates } : c
          ),
        })),
      deleteCharacter: (id) =>
        set((state) => ({
          characters: state.characters.filter((c) => c.character_id !== id),
          selectedCharacterId: state.selectedCharacterId === id ? null : state.selectedCharacterId,
        })),
      selectCharacter: (id) => set({ selectedCharacterId: id }),

      // Terms
      terms: [],
      setTerms: (terms) => set({ terms }),
      addTerm: (term) => set((state) => ({ terms: [...state.terms, term] })),
      updateTerm: (id, updates) =>
        set((state) => ({
          terms: state.terms.map((t) => (t.term_id === id ? { ...t, ...updates } : t)),
        })),
      deleteTerm: (id) => set((state) => ({ terms: state.terms.filter((t) => t.term_id !== id) })),

      // Provider Config
      providerConfig: null,
      setProviderConfig: (config) => set({ providerConfig: config }),

      // Batch Jobs
      batchJobs: [],
      setBatchJobs: (jobs) => set({ batchJobs: jobs }),
      addBatchJob: (job) => set((state) => ({ batchJobs: [...state.batchJobs, job] })),
      updateBatchJob: (id, updates) =>
        set((state) => ({
          batchJobs: state.batchJobs.map((j) => (j.id === id ? { ...j, ...updates } : j)),
        })),
      deleteBatchJob: (id) => set((state) => ({ batchJobs: state.batchJobs.filter((j) => j.id !== id) })),

      // Translation Progress
      translationProgress: null,
      isTranslating: false,
      setTranslationProgress: (progress) => set({ translationProgress: progress }),
      setIsTranslating: (translating) => set({ isTranslating: translating }),

      // UI State
      sidebarCollapsed: false,
      toggleSidebar: () => set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
    }),
    {
      name: 'manga-translate-agent-storage',
      partialize: (state) => ({
        hasCompletedOnboarding: state.hasCompletedOnboarding,
        backendHost: state.backendHost,
        backendPort: state.backendPort,
        sidebarCollapsed: state.sidebarCollapsed,
      }),
    }
  )
)