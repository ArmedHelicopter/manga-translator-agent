import { Routes, Route, Navigate } from 'react-router-dom'
import { useAppStore } from './store'
import Layout from './components/Layout'
import Onboarding from './components/Onboarding'
import ProjectsPage from './pages/ProjectsPage'
import TranslatePage from './pages/TranslatePage'
import BatchPage from './pages/BatchPage'
import CharactersPage from './pages/CharactersPage'
import TermsPage from './pages/TermsPage'
import ProvidersPage from './pages/ProvidersPage'
import WikiPage from './pages/WikiPage'
import SettingsPage from './pages/SettingsPage'
import HelpPage from './pages/HelpPage'

function App() {
  const hasCompletedOnboarding = useAppStore((state) => state.hasCompletedOnboarding)

  if (!hasCompletedOnboarding) {
    return <Onboarding />
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/projects" replace />} />
        <Route path="/projects" element={<ProjectsPage />} />
        <Route path="/translate" element={<TranslatePage />} />
        <Route path="/translate/:projectId" element={<TranslatePage />} />
        <Route path="/batch" element={<BatchPage />} />
        <Route path="/characters" element={<CharactersPage />} />
        <Route path="/characters/:projectId" element={<CharactersPage />} />
        <Route path="/terms" element={<TermsPage />} />
        <Route path="/terms/:projectId" element={<TermsPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/providers/:projectId" element={<ProvidersPage />} />
        <Route path="/wiki" element={<WikiPage />} />
        <Route path="/wiki/:projectId" element={<WikiPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/help" element={<HelpPage />} />
      </Routes>
    </Layout>
  )
}

export default App