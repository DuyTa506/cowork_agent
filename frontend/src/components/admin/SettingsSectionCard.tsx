import { useState } from 'react'
import { ApiError, adminApi, type SaveSettingsResult, type SettingField, type SettingsSection, type TestConnectionResult } from '../../api'
import { TESTABLE_SECTIONS, buildPayload, initialDraft, type FieldDraft, type SecretDraft, type SectionDraft } from '../../lib/settings'
import { Alert } from '../Alert'
import { Button } from '../Button'
import { Chip } from '../Chip'
import { ConfirmDialog } from '../ConfirmDialog'
import { Field } from '../Field'
import { Select } from '../Select'
import { Switch } from '../Switch'
import { useToast } from '../Toast'
import { SecretInput } from './SecretInput'

interface SettingsSectionCardProps {
  section: SettingsSection
  onSaved: (sectionKey: string, result: SaveSettingsResult) => void
}

/** Hosts the server reports when a saved endpoint is outside the private network and needs the administrator's consent. */
function externalHosts(error: unknown): string[] | null {
  if (!(error instanceof ApiError) || error.status !== 409 || error.code !== 'external_endpoint') return null
  const hosts = error.data.hosts
  return Array.isArray(hosts) ? hosts.map(String) : []
}

/**
 * One settings section generated from its metadata: an input per field kind, "Kiểm tra kết nối" for model endpoints and
 * "Lưu", which sends only the changed fields. Endpoints outside the internal network require an explicit confirmation.
 */
export function SettingsSectionCard({ section, onSaved }: SettingsSectionCardProps) {
  const notify = useToast()
  const [draft, setDraft] = useState<SectionDraft>(() => initialDraft(section))
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)
  const [pendingHosts, setPendingHosts] = useState<string[] | null>(null)

  const { values: changes, errors } = buildPayload(section, draft, true)
  const dirty = Object.keys(changes).length > 0
  const invalid = Object.keys(errors).length > 0
  const testable = TESTABLE_SECTIONS.has(section.key)

  const set = (name: string, value: FieldDraft) => {
    setDraft((current) => ({ ...current, [name]: value }))
    setTestResult(null)
  }

  const save = async (confirmHosts: string[]) => {
    setSaving(true)
    setSaveError(null)
    try {
      const result = await adminApi.saveSettings(section.key, changes, confirmHosts)
      setPendingHosts(null)
      notify(result.changed.length > 0 ? `Đã lưu cấu hình "${section.label}".` : 'Không có thay đổi nào cần lưu.')
      onSaved(section.key, result)
    } catch (failure) {
      const hosts = externalHosts(failure)
      if (hosts && confirmHosts.length === 0) {
        setPendingHosts(hosts)
      } else {
        setPendingHosts(null)
        setSaveError(failure instanceof Error ? failure.message : 'Không lưu được cấu hình.')
      }
    } finally {
      setSaving(false)
    }
  }

  const test = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      setTestResult(await adminApi.testSettings(section.key, buildPayload(section, draft, false).values))
    } catch (failure) {
      setTestResult({ ok: false, message: failure instanceof Error ? failure.message : 'Không kiểm tra được kết nối.', latency_ms: 0, detail: {} })
    } finally {
      setTesting(false)
    }
  }

  const renderField = (field: SettingField) => {
    const current = draft[field.name]
    const error = errors[field.name]
    if (field.secret) {
      return (
        <SecretInput
          key={field.name}
          label={field.label}
          hint={field.help || undefined}
          isSet={typeof field.value === 'object' && field.value.set}
          draft={current as SecretDraft}
          onChange={(next) => set(field.name, next)}
        />
      )
    }
    if (field.kind === 'bool') {
      return (
        <div key={field.name} className="field">
          <Switch checked={current as boolean} onChange={(checked) => set(field.name, checked)} label={field.label} />
          {field.help && <div className="field__hint field__hint--switch">{field.help}</div>}
        </div>
      )
    }
    return (
      <Field key={field.name} label={field.label} hint={field.help || undefined} error={error}>
        {({ id, describedBy, invalid: isInvalid }) =>
          field.kind === 'choice' ? (
            <Select id={id} aria-describedby={describedBy} value={current as string} options={field.choices.map((choice) => ({ value: choice, label: choice }))} onChange={(value) => set(field.name, value)} />
          ) : (
            <input
              id={id}
              className="input"
              type={field.kind === 'int' || field.kind === 'float' ? 'number' : 'text'}
              inputMode={field.kind === 'url' ? 'url' : undefined}
              step={field.kind === 'float' ? 'any' : field.kind === 'int' ? 1 : undefined}
              min={field.minimum ?? undefined}
              max={field.maximum ?? undefined}
              autoComplete="off"
              spellCheck={false}
              aria-describedby={describedBy}
              aria-invalid={isInvalid || undefined}
              value={current as string}
              onChange={(event) => set(field.name, event.target.value)}
            />
          )
        }
      </Field>
    )
  }

  return (
    <section className="card card--flush settings-card" aria-labelledby={`section-${section.key}`}>
      <header className="settings-card__head">
        <div className="settings-card__titles">
          <h3 className="settings-card__title" id={`section-${section.key}`}>{section.label}</h3>
          <p className="settings-card__desc">{section.description}</p>
        </div>
        {(section.used_by || section.sends_document_text) && (
          <div className="settings-card__tags">
            {section.used_by && <Chip tone="grey" icon="tools">Dùng cho: {section.used_by}</Chip>}
            {section.sends_document_text && <Chip tone="amber" icon="alert">Nhận nội dung văn bản · chỉ đặt trong mạng nội bộ</Chip>}
          </div>
        )}
      </header>

      <div className="settings-card__body">
        <div className="settings-card__fields">{section.fields.map(renderField)}</div>
        {saveError && <Alert kind="error">{saveError}</Alert>}
      </div>

      <footer className="settings-card__foot">
        {testable && <Button icon="refresh" onClick={test} loading={testing} disabled={invalid}>Kiểm tra kết nối</Button>}
        <div className="settings-card__result" role="status" aria-live="polite">
          {testResult && (
            <>
              <Chip tone={testResult.ok ? 'green' : 'red'} icon={testResult.ok ? 'checkCircle' : 'alertCircle'}>
                {testResult.ok ? `Kết nối thành công${testResult.latency_ms > 0 ? ` · ${testResult.latency_ms} ms` : ''}` : 'Kết nối thất bại'}
              </Chip>
              {(!testResult.ok || !/thành công/i.test(testResult.message)) && <span className="settings-card__result-msg">{testResult.message}</span>}
            </>
          )}
        </div>
        {dirty && <Button variant="ghost" onClick={() => { setDraft(initialDraft(section)); setTestResult(null); setSaveError(null) }} disabled={saving}>Hoàn tác</Button>}
        <Button variant="primary" icon="save" onClick={() => save([])} loading={saving} disabled={!dirty || invalid}>Lưu</Button>
      </footer>

      {pendingHosts && (
        <ConfirmDialog
          title="Máy chủ nằm ngoài mạng nội bộ"
          confirmLabel="Vẫn lưu và gửi văn bản tới máy chủ này"
          danger
          onCancel={() => setPendingHosts(null)}
          onConfirm={() => save(pendingHosts)}
        >
          <p>
            Máy chủ dưới đây <strong>nằm ngoài mạng nội bộ</strong> và sẽ nhận nội dung văn bản của kho
            (khi lập chỉ mục, tìm kiếm hoặc trả lời). Chỉ xác nhận nếu bạn chắc chắn được phép gửi dữ liệu ra ngoài.
          </p>
          <ul className="host-list">{pendingHosts.map((host) => <li key={host}><code>{host}</code></li>)}</ul>
        </ConfirmDialog>
      )}
    </section>
  )
}
