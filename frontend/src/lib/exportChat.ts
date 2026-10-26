import type { UiMessage } from '../components/assistant/types'
import { saveBlob } from './download'

const ROLE_LABEL: Record<UiMessage['role'], string> = { user: 'ĐỒNG CHÍ', assistant: 'TRỢ LÝ AI' }

/** The conversation as a Markdown document: each entry with its role, time and (for answers) the numbered sources. */
export function conversationToMarkdown(title: string, messages: readonly UiMessage[]): string {
  const lines = [`# ${title}`, '']
  for (const message of messages) {
    const when = new Date(message.created_at).toLocaleString('vi-VN')
    lines.push(`## ${ROLE_LABEL[message.role]} · ${when}`, '', message.content.trim(), '')
    if (message.citations.length > 0) {
      lines.push('Nguồn trích dẫn:')
      for (const cite of message.citations) {
        const where = [cite.ref, cite.section].filter(Boolean).join(' · ')
        lines.push(`${cite.n}. ${cite.title}${where ? ` (${where})` : ''}`)
      }
      lines.push('')
    }
  }
  return lines.join('\n')
}

/** Saves the conversation as `<title>.md`; characters a file name cannot hold are dropped. */
export function exportConversation(title: string, messages: readonly UiMessage[]): void {
  const name = title.replace(/[\\/:*?"<>|]+/g, ' ').trim().slice(0, 80) || 'cuoc-tro-chuyen'
  saveBlob(new Blob([conversationToMarkdown(title, messages)], { type: 'text/markdown;charset=utf-8' }), `${name}.md`)
}
