export interface DiffPart {
  type: 'same' | 'del' | 'ins'
  text: string
}

/** Above this many table cells the word diff is skipped and the whole text is shown as replaced. */
const MAX_CELLS = 160_000

const push = (parts: DiffPart[], type: DiffPart['type'], text: string) => {
  const last = parts[parts.length - 1]
  if (last && last.type === type) last.text += text
  else parts.push({ type, text })
}

/** Word-level difference between two texts (longest common subsequence): what the proposal removes and adds. */
export function diffWords(before: string, after: string): DiffPart[] {
  const a = before.split(/(\s+)/).filter(Boolean)
  const b = after.split(/(\s+)/).filter(Boolean)
  if (a.length * b.length > MAX_CELLS) {
    return [{ type: 'del', text: before }, { type: 'ins', text: after }]
  }
  // lengths[i][j] = length of the common subsequence of a[i..] and b[j..]
  const lengths: number[][] = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      const row = lengths[i] as number[]
      row[j] = a[i] === b[j] ? ((lengths[i + 1] as number[])[j + 1] as number) + 1 : Math.max((lengths[i + 1] as number[])[j] as number, row[j + 1] as number)
    }
  }
  const parts: DiffPart[] = []
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (a[i] === b[j]) {
      push(parts, 'same', a[i] as string)
      i += 1
      j += 1
    } else if (((lengths[i + 1] as number[])[j] as number) >= ((lengths[i] as number[])[j + 1] as number)) {
      push(parts, 'del', a[i] as string)
      i += 1
    } else {
      push(parts, 'ins', b[j] as string)
      j += 1
    }
  }
  while (i < a.length) push(parts, 'del', a[i++] as string)
  while (j < b.length) push(parts, 'ins', b[j++] as string)
  return joinChanges(parts)
}

/**
 * A word diff of two differently worded sentences alternates removed and added words with single spaces between them,
 * which is hard to read. Changes separated only by whitespace are merged into one removed run followed by one added run.
 */
function joinChanges(parts: DiffPart[]): DiffPart[] {
  const result: DiffPart[] = []
  let removed = ''
  let added = ''
  const flush = () => {
    if (removed) push(result, 'del', removed)
    if (added) push(result, 'ins', added)
    removed = ''
    added = ''
  }
  parts.forEach((part, index) => {
    if (part.type === 'del') removed += part.text
    else if (part.type === 'ins') added += part.text
    else if (!part.text.trim() && (removed || added) && parts[index + 1] && parts[index + 1]?.type !== 'same') {
      removed += part.text
      added += part.text
    } else {
      flush()
      push(result, 'same', part.text)
    }
  })
  flush()
  return result
}
