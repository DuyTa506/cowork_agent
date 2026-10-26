/** Lower-case extension of a file name without the dot ("Kế hoạch.DOCX" -> "docx"); a bare extension is returned as is. */
export function extensionOf(name: string): string {
  const base = name.trim().toLowerCase()
  const dot = base.lastIndexOf('.')
  return dot >= 0 ? base.slice(dot + 1) : base.length <= 5 ? base : ''
}
