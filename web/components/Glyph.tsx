import { HugeiconsIcon, type IconSvgElement } from '@hugeicons/react'

export type IconData = IconSvgElement

/** Every icon in the UI goes through here, so the stroke weight is set once. Size it with height and width classes. */
export function Glyph({ icon, className, strokeWidth = 1.5 }: { icon: IconData; className?: string; strokeWidth?: number }) {
  return <HugeiconsIcon icon={icon} strokeWidth={strokeWidth} className={className} aria-hidden />
}
