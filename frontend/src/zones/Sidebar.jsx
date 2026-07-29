import { useStore } from '../store/useStore'
import Dropzone from '../components/Dropzone'
import BranchManager from '../components/BranchManager'
import GoalTracker from '../components/GoalTracker'
import LLMConfigPanel from '../components/LLMConfigPanel'
import SettingsPanel from '../components/SettingsPanel'
import DataTools from '../components/DataTools'

function Section({ title, meta, children }) {
  return (
    <section className="p-3 border-b border-edge">
      <h2 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500">
        {title}
      </h2>
      {/* Sits under the heading rather than beside it so it reads as a label
          for the section, not as part of the title. */}
      {meta && (
        <p className="text-[10px] normal-case tracking-normal text-gray-600">
          {meta}
        </p>
      )}
      <div className="mt-2">{children}</div>
    </section>
  )
}

// Zone 1: structural left control sidebar (PRD 4.1).
export default function Sidebar() {
  const version = useStore((s) => s.appVersion)

  return (
    <div>
      <Section title="Data Ingest">
        <Dropzone />
      </Section>
      <Section title="Plans & Branches">
        <BranchManager />
      </Section>
      <Section title="Goals">
        <GoalTracker />
      </Section>
      <Section title="LLM Provider">
        <LLMConfigPanel />
      </Section>
      <Section
        title="Settings"
        meta={version ? `App v.${version}` : null}
      >
        <SettingsPanel />
      </Section>
      <Section title="Export & Backup">
        <DataTools />
      </Section>
    </div>
  )
}
