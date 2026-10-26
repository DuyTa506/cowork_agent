/** Finding a cited passage in the text layer of a PDF page. */

const strip = (text: string): string => text.normalize('NFC').toLowerCase().replace(/\s+/g, '')

export interface TextMatch {
  /** Index range (inclusive) of the text items of the page that hold the passage. */
  from: number
  to: number
}

const MAX_WORDS = 12
const MIN_WORDS = 3
const MIN_CHARS = 12

/**
 * Looks for the beginning of `snippet` in the text `items` of one page (text items may split a line anywhere and a line break may or may
 * not leave a space, so spaces are ignored on both sides). Starts with the first words and, when they are not found as written (a
 * hyphenated word, a table cell between them), tries fewer. A match is then extended over as many of the following words as also match.
 */
export function findPassage(items: readonly string[], snippet: string): TextMatch | null {
  const words = snippet.split(/\s+/).map(strip).filter(Boolean)
  if (words.length === 0) return null

  let hay = ''
  const starts: number[] = []
  for (const item of items) {
    starts.push(hay.length)
    hay += strip(item)
  }
  const itemAt = (offset: number): number => {
    let low = 0
    let high = starts.length - 1
    while (low < high) {
      const mid = (low + high + 1) >> 1
      if ((starts[mid] ?? 0) <= offset) low = mid
      else high = mid - 1
    }
    return low
  }

  for (let count = Math.min(MAX_WORDS, words.length); count >= Math.min(MIN_WORDS, words.length); count -= 1) {
    const needle = words.slice(0, count).join('')
    if (needle.length < MIN_CHARS && words.length > count) continue
    const at = hay.indexOf(needle)
    if (at < 0) continue
    let end = at + needle.length
    for (const word of words.slice(count)) {
      if (!hay.startsWith(word, end)) break
      end += word.length
    }
    return { from: itemAt(at), to: itemAt(Math.max(at, end - 1)) }
  }
  return null
}
