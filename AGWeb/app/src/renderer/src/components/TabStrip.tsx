import { useShellStore } from '@/store'
import { CloseIcon, GlobeIcon } from '@/components/icons'

export function TabStrip(): React.JSX.Element {
  const { tabs, activeTabId, activateTab, closeTab, newTab } = useShellStore()

  return (
    <div className="flex items-end gap-1 bg-slate-100 px-3 pt-2 dark:bg-[#0b0f14]">
      {tabs.map((tab) => (
        <div
          key={tab.id}
          onClick={() => activateTab(tab.id)}
          className={`group flex max-w-56 cursor-pointer items-center gap-2 rounded-t-lg border border-b-0 px-3.5 py-2 text-[13px] ${
            tab.id === activeTabId
              ? 'border-slate-200 bg-white dark:border-slate-800 dark:bg-[#0e1420]'
              : 'border-transparent text-slate-500 hover:text-slate-700 dark:hover:text-slate-300'
          }`}
        >
          <GlobeIcon size={13} className="shrink-0 text-sky-500" />
          <span className="truncate">{tab.title}</span>
          <button
            onClick={(event) => {
              event.stopPropagation()
              closeTab(tab.id)
            }}
            className="shrink-0 rounded p-0.5 text-slate-400 opacity-0 hover:bg-slate-200 group-hover:opacity-100 dark:hover:bg-slate-700"
            aria-label={`Close ${tab.title}`}
          >
            <CloseIcon size={11} />
          </button>
        </div>
      ))}
      <button
        onClick={() => newTab()}
        className="mb-1 flex h-7 w-7 items-center justify-center rounded-md text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800"
        aria-label="New tab"
      >
        +
      </button>
    </div>
  )
}
