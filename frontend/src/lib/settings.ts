import type { SecretState, SettingField, SettingsPayload, SettingsSection, SettingValue } from '../api'

/** Sections that have a "Kiểm tra kết nối" button (the backend can probe their endpoint). */
export const TESTABLE_SECTIONS = new Set(['llm', 'embedding', 'rerank', 'ocr'])

export type SecretMode = 'keep' | 'change' | 'clear'

export interface SecretDraft {
  mode: SecretMode
  text: string
}

/** What the form holds while editing: text for most fields, a boolean for switches, a SecretDraft for secrets. */
export type FieldDraft = string | boolean | SecretDraft

export type SectionDraft = Record<string, FieldDraft>

const isSecretState = (value: SettingValue): value is SecretState => typeof value === 'object'

/** Form state for a section as currently saved on the server. */
export function initialDraft(section: SettingsSection): SectionDraft {
  const draft: SectionDraft = {}
  for (const field of section.fields) {
    if (field.secret) {
      const isSet = isSecretState(field.value) && field.value.set
      draft[field.name] = { mode: isSet ? 'keep' : 'change', text: '' } satisfies SecretDraft
    } else if (field.kind === 'bool') {
      draft[field.name] = field.value === true
    } else {
      draft[field.name] = String(field.value ?? '')
    }
  }
  return draft
}

/** The value a field's text stands for, or an error message in Vietnamese. */
function parseField(field: SettingField, text: string): { value: string | number } | { error: string } {
  if (field.kind === 'int' || field.kind === 'float') {
    const trimmed = text.trim()
    const number = Number(trimmed)
    const valid = trimmed !== '' && Number.isFinite(number) && (field.kind === 'float' || Number.isInteger(number))
    if (!valid) return { error: field.kind === 'int' ? 'Nhập một số nguyên.' : 'Nhập một số.' }
    if (field.minimum !== null && number < field.minimum) return { error: `Giá trị tối thiểu là ${field.minimum}.` }
    if (field.maximum !== null && number > field.maximum) return { error: `Giá trị tối đa là ${field.maximum}.` }
    return { value: number }
  }
  return { value: text }
}

export interface BuiltPayload {
  /** Changed fields only (`changesOnly`) or every field (for a connection test). */
  values: SettingsPayload
  errors: Record<string, string>
}

/**
 * Turns the form into the request body. Secrets are omitted when untouched (the server keeps them), `""` when cleared and
 * the new text when changed.
 * @param changesOnly send only fields that differ from the saved values (saving); otherwise send all (testing).
 */
export function buildPayload(section: SettingsSection, draft: SectionDraft, changesOnly: boolean): BuiltPayload {
  const values: SettingsPayload = {}
  const errors: Record<string, string> = {}
  for (const field of section.fields) {
    const current = draft[field.name]
    if (field.secret) {
      const secret = current as SecretDraft
      if (secret.mode === 'clear') values[field.name] = ''
      else if (secret.mode === 'change' && secret.text !== '') values[field.name] = secret.text
      continue
    }
    if (field.kind === 'bool') {
      if (!changesOnly || current !== field.value) values[field.name] = current as boolean
      continue
    }
    const parsed = parseField(field, current as string)
    if ('error' in parsed) {
      errors[field.name] = parsed.error
    } else if (!changesOnly || parsed.value !== field.value) {
      values[field.name] = parsed.value
    }
  }
  return { values, errors }
}
