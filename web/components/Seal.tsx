/** The Hakiki mark: a court seal ring around a section sign, with a nick where the court's note is pinned. */
export function Seal({ className = '' }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={className} aria-hidden fill="none" stroke="currentColor">
      <circle cx="20" cy="20" r="17.5" strokeWidth="1.6" strokeDasharray="96 3 100" />
      <circle cx="20" cy="20" r="14" strokeWidth="0.8" strokeDasharray="1.2 1.6" />
      <text x="20" y="27.5" textAnchor="middle" fontSize="21" fill="currentColor" stroke="none" className="statute">
        §
      </text>
    </svg>
  )
}
