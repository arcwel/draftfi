import { useStore } from '../store/useStore'

// Shown after DraftFi replaced a retired model on the user's behalf.
//
// This is deliberately a notice, not a prompt: the switch has already happened
// and everything already works, so there is nothing to confirm and nothing to
// block on. It sits in the header next to the update pill, and dismissing it is
// the only interaction.
export default function ModelNoticeBanner() {
  const notice = useStore((s) => s.llm.notice)
  const dismiss = useStore((s) => s.dismissModelNotice)

  if (!notice) return null

  return (
    <div
      className="flex items-center gap-2 rounded-md border border-amber-700 bg-amber-950/50 px-2.5 py-1 text-[11px] text-amber-200"
      title={
        notice.reason
          ? `${notice.reason} DraftFi switched to ${notice.new_model} so categorization keeps working. Change it any time in the LLM Provider panel.`
          : `DraftFi switched to ${notice.new_model} so categorization keeps working.`
      }
    >
      <span aria-hidden>⟳</span>
      <span>
        Model updated:{' '}
        <span className="font-medium text-amber-100">
          {notice.previous_model}
        </span>{' '}
        was retired → now using{' '}
        <span className="font-medium text-amber-100">{notice.new_model}</span>
      </span>
      <button
        onClick={dismiss}
        title="Dismiss"
        className="text-amber-400/70 hover:text-white"
      >
        ✕
      </button>
    </div>
  )
}
