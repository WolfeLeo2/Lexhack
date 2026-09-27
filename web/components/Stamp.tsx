import { cap, courtActed } from '@/lib/format'

/** Status is always words, never a colour-coded yes/no. The ink only says whether a court has acted. */
export function StatusStamp({ status }: { status: string }) {
  const acted = courtActed(status)
  return (
    <div
      className={`stamp inline-block rounded-[3px] border-2 px-3.5 py-2 ${acted ? 'border-seal text-seal' : 'border-ink-2/50 text-ink-2'}`}
      role="status"
    >
      <span className="block text-xs leading-none opacity-80">Status today</span>
      <span className="statute mt-1 block text-xl leading-tight font-medium">{cap(status)}</span>
    </div>
  )
}
