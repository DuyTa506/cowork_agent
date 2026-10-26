import type { ReactNode } from 'react'

/** Inline line illustrations for empty and error states (96 px, brand colours via CSS classes in ui-feedback.css). */
export type IllustrationName = 'documents' | 'search' | 'chat' | 'check' | 'error'

const PAGE = 'M32 14h24l14 14v46a3 3 0 0 1-3 3H32a3 3 0 0 1-3-3V17a3 3 0 0 1 3-3z'
const FOLD = 'M56 14v11a3 3 0 0 0 3 3h11'

const ART: Record<IllustrationName, ReactNode> = {
  documents: (
    <>
      <circle cx="48" cy="50" r="38" className="art-fill" />
      <rect x="22" y="22" width="40" height="52" rx="4" className="art-paper" transform="rotate(-9 42 48)" />
      <path d={PAGE} className="art-paper" />
      <path d={FOLD} className="art-line" />
      <path d="M38 44h24M38 52h24M38 60h14" className="art-dim" />
      <path d="M72 14v10M67 19h10" className="art-accent" />
      <circle cx="18" cy="70" r="2.5" className="art-accent" />
    </>
  ),
  search: (
    <>
      <circle cx="48" cy="50" r="38" className="art-fill" />
      <path d="M26 14h24l14 14v22" className="art-paper" />
      <path d="M26 14a3 3 0 0 0-3 3v56a3 3 0 0 0 3 3h14" className="art-paper" />
      <path d="M50 14v11a3 3 0 0 0 3 3h11" className="art-line" />
      <path d="M32 40h18M32 48h12M32 56h8" className="art-dim" />
      <circle cx="58" cy="58" r="14" className="art-paper" />
      <circle cx="58" cy="58" r="14" className="art-line" />
      <path d="M68.5 68.5 80 80" className="art-line" strokeWidth="3" />
      <path d="M52 56a7 7 0 0 1 7-6" className="art-accent" />
    </>
  ),
  chat: (
    <>
      <circle cx="48" cy="50" r="38" className="art-fill" />
      <path d="M20 26a6 6 0 0 1 6-6h34a6 6 0 0 1 6 6v22a6 6 0 0 1-6 6H40l-10 9v-9h-4a6 6 0 0 1-6-6z" className="art-paper" />
      <path d="M28 33h30M28 41h20" className="art-dim" />
      <path d="M42 62h22a6 6 0 0 1 6 6v6a6 6 0 0 1-6 6h-3v7l-9-7H42a6 6 0 0 1-6-6v-6a6 6 0 0 1 6-6z" transform="translate(6 -8)" className="art-paper" />
      <path d="M54 66h14M54 72h8" transform="translate(0 0)" className="art-accent" />
    </>
  ),
  check: (
    <>
      <circle cx="48" cy="50" r="38" className="art-fill" />
      <path d={PAGE} className="art-paper" />
      <path d={FOLD} className="art-line" />
      <path d="M38 40h20M38 47h14" className="art-dim" />
      <circle cx="58" cy="62" r="15" className="art-paper" />
      <circle cx="58" cy="62" r="15" className="art-line" />
      <path d="m51 62 5.5 5.5L66 57" className="art-accent" strokeWidth="2.6" />
    </>
  ),
  error: (
    <>
      <circle cx="48" cy="50" r="38" className="art-fill" />
      <path d={PAGE} className="art-paper" />
      <path d={FOLD} className="art-line" />
      <path d="M38 40h20M38 47h10" className="art-dim" />
      <path d="M58 52 76 82H40z" className="art-paper" strokeLinejoin="round" transform="translate(0 -2)" />
      <path d="M58 50 76 80H40z" className="art-danger" />
      <path d="M58 62v8" className="art-danger" strokeWidth="2.6" />
      <circle cx="58" cy="75" r="1.4" className="art-danger" />
    </>
  ),
}

/** One of five illustrations; decorative (hidden from assistive technology). */
export function EmptyIllustration({ name, className }: { name: IllustrationName; className?: string }) {
  return (
    <svg className={['empty__art', className].filter(Boolean).join(' ')} viewBox="0 0 96 96" aria-hidden="true" focusable="false">
      {ART[name]}
    </svg>
  )
}
