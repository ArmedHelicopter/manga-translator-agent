import { useTranslation } from 'react-i18next'
import { useAppStore } from '../store'
import {
  FolderOpen,
  Play,
  Layers,
  Users,
  BookOpen,
  Settings,
  HelpCircle,
  Globe,
  Menu,
  ChevronLeft,
  Database,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { path: '/projects', icon: FolderOpen, labelKey: 'nav.projects' },
  { path: '/translate', icon: Play, labelKey: 'nav.translate' },
  { path: '/batch', icon: Layers, labelKey: 'nav.batch' },
  { path: '/characters', icon: Users, labelKey: 'nav.characters' },
  { path: '/terms', icon: BookOpen, labelKey: 'nav.terms' },
  { path: '/providers', icon: Database, labelKey: 'providers.title' },
  { path: '/wiki', icon: Globe, labelKey: 'nav.wiki' },
  { path: '/settings', icon: Settings, labelKey: 'nav.settings' },
  { path: '/help', icon: HelpCircle, labelKey: 'nav.help' },
]

interface SidebarProps {
  collapsed: boolean
}

export default function Sidebar({ collapsed }: SidebarProps) {
  const { t } = useTranslation()
  const toggleSidebar = useAppStore((state) => state.toggleSidebar)

  return (
    <aside
      className={clsx(
        'fixed left-0 top-14 h-[calc(100vh-3.5rem)] bg-white border-r border-gray-200 transition-all duration-300 z-40',
        collapsed ? 'w-16' : 'w-64'
      )}
    >
      <nav className="flex flex-col h-full py-4">
        {navItems.map(({ path, icon: Icon, labelKey }) => (
          <NavItem
            key={path}
            path={path}
            icon={Icon}
            label={t(labelKey)}
            collapsed={collapsed}
          />
        ))}
      </nav>

      <button
        onClick={toggleSidebar}
        className="absolute bottom-4 right-4 p-2 rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors"
        title={collapsed ? 'Expand' : 'Collapse'}
      >
        {collapsed ? <Menu size={18} /> : <ChevronLeft size={18} />}
      </button>
    </aside>
  )
}

interface NavItemProps {
  path: string
  icon: typeof FolderOpen
  label: string
  collapsed: boolean
}

function NavItem({ path, icon: Icon, label, collapsed }: NavItemProps) {
  const isActive = window.location.pathname.startsWith(path)

  return (
    <a
      href={`#${path}`}
      className={clsx(
        'flex items-center gap-3 mx-2 px-3 py-2.5 rounded-lg transition-colors',
        isActive
          ? 'bg-primary-50 text-primary-700 border-l-4 border-primary-600'
          : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
      )}
    >
      <Icon size={20} className="flex-shrink-0" />
      {!collapsed && (
        <span className="font-medium truncate">{label}</span>
      )}
    </a>
  )
}