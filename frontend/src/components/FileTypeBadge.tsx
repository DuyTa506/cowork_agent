import { extensionOf } from '../lib/files'

interface Props {
  /** File name (the extension decides the look) or a bare extension. */
  name: string
  size?: 'sm' | 'md' | 'lg'
}

type Kind = 'word' | 'doc' | 'pdf' | 'other'

const KIND_TITLES: Record<Kind, string> = {
  word: 'Tệp Word (.docx)',
  doc: 'Tệp Word đời cũ (.doc)',
  pdf: 'Tệp PDF',
  other: 'Tệp',
}

/**
 * A page glyph with a folded corner and a solid coloured label band carrying the extension, so the format reads at a glance:
 * DOCX blue, legacy DOC slate (dashed fold, a different grey-blue), PDF red. The text label keeps it readable without colour.
 */
export function FileTypeBadge({ name, size = 'md' }: Props) {
  const ext = extensionOf(name)
  const label = ext ? ext.toUpperCase() : 'FILE'
  const kind = kindOf(ext)
  return (
    <span className={`ftype ftype--${size} ftype--${kind}`} role="img" aria-label={`Tệp ${label}`} title={KIND_TITLES[kind]}>
      <svg viewBox="0 0 32 40" aria-hidden="true" focusable="false">
        <path className="ftype__page" d="M3.5 1h16.6L29 9.9V37a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3a2 2 0 0 1 .5-2z" />
        <path className="ftype__fold" d="M20 1v7a2 2 0 0 0 2 2h7" />
        <path className="ftype__lines" d="M8 14h9M8 18h16M8 22h13" />
      </svg>
      <b className="ftype__label">{label}</b>
    </span>
  )
}

function kindOf(ext: string): Kind {
  if (ext === 'docx') return 'word'
  if (ext === 'doc') return 'doc'
  if (ext === 'pdf') return 'pdf'
  return 'other'
}
