import { Fragment, type ReactNode } from 'react'

type Block =
  | { kind: 'p'; lines: string[] }
  | { kind: 'h'; text: string }
  | { kind: 'ul' | 'ol'; items: string[]; start?: number }
  | { kind: 'table'; head: string[]; rows: string[][] }

const BULLET = /^\s*[-*•]\s+(.*)$/
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/
const HEADING = /^\s*#{1,6}\s+(.*)$/
const TABLE_ROW = /^\s*\|.*\|\s*$/
const TABLE_RULE = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/

const splitRow = (line: string): string[] => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((cell) => cell.trim())

/** Splits the text into paragraphs, headings, lists and tables. Anything unrecognised stays a paragraph. */
function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  const blocks: Block[] = []
  let index = 0
  while (index < lines.length) {
    const line = lines[index] ?? ''
    if (!line.trim()) {
      index += 1
      continue
    }
    const heading = HEADING.exec(line)
    if (heading) {
      blocks.push({ kind: 'h', text: heading[1] ?? '' })
      index += 1
      continue
    }
    if (TABLE_ROW.test(line) && TABLE_RULE.test(lines[index + 1] ?? '')) {
      const rows: string[][] = []
      let next = index + 2
      while (next < lines.length && TABLE_ROW.test(lines[next] ?? '')) {
        rows.push(splitRow(lines[next] ?? ''))
        next += 1
      }
      blocks.push({ kind: 'table', head: splitRow(line), rows })
      index = next
      continue
    }
    const listKind = BULLET.test(line) ? 'ul' : NUMBERED.test(line) ? 'ol' : null
    if (listKind) {
      const pattern = listKind === 'ul' ? BULLET : NUMBERED
      const start = listKind === 'ol' ? Number(/\d+/.exec(line)?.[0]) : undefined
      const items: string[] = []
      while (index < lines.length) {
        const match = pattern.exec(lines[index] ?? '')
        if (!match) break
        items.push(match[1] ?? '')
        index += 1
      }
      blocks.push({ kind: listKind, items, start })
      continue
    }
    const paragraph: string[] = []
    while (index < lines.length) {
      const current = lines[index] ?? ''
      if (!current.trim() || HEADING.test(current) || BULLET.test(current) || NUMBERED.test(current) || TABLE_ROW.test(current)) break
      paragraph.push(current)
      index += 1
    }
    if (paragraph.length === 0) {
      // A lone line that looks like a table row without a rule below it: show it as text.
      paragraph.push(line)
      index += 1
    }
    blocks.push({ kind: 'p', lines: paragraph })
  }
  return blocks
}

const INLINE = /(\*\*(?=\S)[^*]+?\*\*|`[^`\n]+`|\[(\d{1,3})\])/g

interface MarkdownProps {
  text: string
  /** Renders the citation marker `[n]`; without it the marker stays plain text. */
  renderCitation?: (n: number, key: string) => ReactNode
}

/**
 * Small, safe Markdown subset for answers: paragraphs, headings, bullet and numbered lists, pipe tables, **bold**,
 * `code` and `[n]` source markers. It builds React elements only (no HTML string is ever injected).
 */
export function Markdown({ text, renderCitation }: MarkdownProps) {
  const inline = (source: string, prefix: string): ReactNode[] => {
    const nodes: ReactNode[] = []
    let last = 0
    let count = 0
    for (const match of source.matchAll(INLINE)) {
      const start = match.index ?? 0
      if (start > last) nodes.push(source.slice(last, start))
      const token = match[0]
      const key = `${prefix}-${count}`
      count += 1
      if (token.startsWith('**')) nodes.push(<strong key={key}>{inline(token.slice(2, -2), key)}</strong>)
      else if (token.startsWith('`')) nodes.push(<code key={key}>{token.slice(1, -1)}</code>)
      else if (renderCitation) nodes.push(<Fragment key={key}>{renderCitation(Number(match[2]), key)}</Fragment>)
      else nodes.push(token)
      last = start + token.length
    }
    if (last < source.length) nodes.push(source.slice(last))
    return nodes
  }

  return (
    <div className="answer-md">
      {parseBlocks(text).map((block, blockIndex) => {
        const key = `b${blockIndex}`
        switch (block.kind) {
          case 'h':
            return <p key={key} className="answer-md__h">{inline(block.text, key)}</p>
          case 'ul':
            return <ul key={key}>{block.items.map((item, i) => <li key={i}>{inline(item, `${key}-${i}`)}</li>)}</ul>
          case 'ol':
            return <ol key={key} start={block.start && block.start > 1 ? block.start : undefined}>{block.items.map((item, i) => <li key={i}>{inline(item, `${key}-${i}`)}</li>)}</ol>
          case 'table':
            return (
              <div key={key} className="answer-md__table-wrap">
                <table className="answer-md__table">
                  <thead>
                    <tr>{block.head.map((cell, i) => <th key={i}>{inline(cell, `${key}-h${i}`)}</th>)}</tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, r) => (
                      <tr key={r}>{row.map((cell, i) => <td key={i}>{inline(cell, `${key}-${r}-${i}`)}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          default:
            return (
              <p key={key}>
                {block.lines.map((line, i) => (
                  <Fragment key={i}>
                    {i > 0 && <br />}
                    {inline(line, `${key}-${i}`)}
                  </Fragment>
                ))}
              </p>
            )
        }
      })}
    </div>
  )
}
