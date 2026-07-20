import Dropzone from '../components/Dropzone'
import BranchManager from '../components/BranchManager'
import GoalTracker from '../components/GoalTracker'
import LLMConfigPanel from '../components/LLMConfigPanel'
import DataTools from '../components/DataTools'

function Section({ title, children }) {
  return (
    <section className="p-3 border-b border-edge">
      <h2 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-gray-500">
        {title}
      </h2>
      {children}
    </section>
  )
}

// Zone 1: structural left control sidebar (PRD 4.1).
export default function Sidebar() {
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
      <Section title="Export & Backup">
        <DataTools />
      </Section>
    </div>
  )
}
