import { useShellStore, type StageTab, type StageTabKind } from '@/store'
import { WelcomeView } from '@/components/WelcomeView'

const NEW_TAB_KINDS: { kind: StageTabKind; label: string }[] = [
  { kind: 'editor', label: '+ Editor' },
  { kind: 'browser', label: '+ Browser' },
  { kind: 'slides', label: '+ Slides' }
]

function StagePlaceholder({ tab }: { tab: StageTab }): React.JSX.Element {
  const phase: Partial<Record<StageTabKind, string>> = {
    editor: 'Monaco editor integration lands in Phase 3.',
    browser: 'Integrated Chromium tabs land in Phase 2.',
    slides: 'Reveal.js slide runtime lands in Phase 4.',
    'mission-control': 'Agent orchestration lands in Phase 6.'
  }
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-slate-500">
      <div className="text-lg font-medium">{tab.title}</div>
      <div className="text-sm">{phase[tab.kind]}</div>
    </div>
  )
}

export function StageTabs(): React.JSX.Element {
  const { tabs, activeTabId, activateTab, closeTab, openTab } = useShellStore()
  const active = tabs.find((t) => t.id === activeTabId) ?? tabs[0]

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-1 border-b border-slate-200 bg-slate-100 px-2 pt-1 dark:border-slate-800 dark:bg-[#0e1420]">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            onClick={() => activateTab(tab.id)}
            className={`group flex cursor-pointer items-center gap-2 rounded-t-md px-3 py-1.5 text-sm ${
              tab.id === active.id
                ? 'bg-slate-50 font-medium dark:bg-[#0b0f14]'
                : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
            }`}
          >
            <span>{tab.title}</span>
            <button
              onClick={(event) => {
                event.stopPropagation()
                closeTab(tab.id)
              }}
              className="rounded px-1 text-slate-400 opacity-0 hover:bg-slate-200 group-hover:opacity-100 dark:hover:bg-slate-700"
              aria-label={`Close ${tab.title}`}
            >
              ×
            </button>
          </div>
        ))}
        <div className="ml-auto flex gap-1 pb-1">
          {NEW_TAB_KINDS.map(({ kind, label }) => (
            <button
              key={kind}
              onClick={() => openTab(kind)}
              className="rounded px-2 py-1 text-xs text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {active.kind === 'welcome' ? <WelcomeView /> : <StagePlaceholder tab={active} />}
      </div>
    </div>
  )
}
