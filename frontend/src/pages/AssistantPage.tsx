import { useEffect, useRef, useState } from 'react'
import type { Citation, StepDocumentRef } from '../api/chat'
import { Alert } from '../components/Alert'
import { Button } from '../components/Button'
import { Composer } from '../components/assistant/Composer'
import { SessionList } from '../components/assistant/SessionList'
import { SidePanel, type PanelTab } from '../components/assistant/SidePanel'
import { SourcePanel } from '../components/assistant/SourcePanel'
import { useSourceFileName } from '../components/assistant/sourceFile'
import { Transcript, type StarterId } from '../components/assistant/Transcript'
import { sourceFromCitation, sourceFromStepRef, type SourceRef } from '../components/assistant/types'
import { useAssistant } from '../components/assistant/useAssistant'
import { CanvasPanel } from '../components/canvas/CanvasPanel'
import { FileTypeBadge } from '../components/FileTypeBadge'
import { Icon } from '../components/Icon'
import { IconButton } from '../components/IconButton'
import { ResizeHandle } from '../components/ResizeHandle'
import { useResizableWidth } from '../hooks/useResizableWidth'
import { useAuth } from '../auth/AuthContext'
import { exportConversation } from '../lib/exportChat'
import { usePageMeta } from '../hooks/usePageMeta'
import { useMediaQuery } from '../hooks/useMediaQuery'

const STARTER_TEXT: Record<StarterId, string> = {
  search: 'Tìm các văn bản quy định về ',
  summarize: 'Tóm tắt văn bản ',
  compose: 'Soạn công văn ',
}

/** File-type badge in the tab of an opened source (its extension is looked up like in the source cards). */
function SourceTabLead({ source, names }: { source: SourceRef; names: ReadonlyMap<number, string> }) {
  const fileName = useSourceFileName(source.kind, source.id, names)
  return <FileTypeBadge name={fileName} size="sm" />
}

/** Below this width the right-hand panel and the conversation list are shown over the chat instead of beside it. */
const NARROW = '(max-width: 900px)'
/** The conversation list closes itself when the right-hand panel opens on screens narrower than this. */
const ROOMY_WIDTH = 1600

/**
 * "Trợ lý AI": conversation list, transcript with the assistant's steps, answers and citations, the composer
 * (upload, Canvas) and, beside the chat, the Canvas draft and cited sources.
 */
export function AssistantPage() {
  const chat = useAssistant()
  const { user } = useAuth()
  const narrow = useMediaQuery(NARROW)
  const [railOpen, setRailOpen] = useState(() => window.innerWidth >= 1200)
  const [canvasOpen, setCanvasOpen] = useState(false)
  const [sources, setSources] = useState<SourceRef[]>([])
  const [active, setActive] = useState('canvas')
  const [showPanel, setShowPanel] = useState(false)
  const [prefill, setPrefill] = useState<{ text: string; nonce: number } | null>(null)
  const openedFor = useRef<string | null>(null)
  const handledPing = useRef(0)
  const [composerKey, setComposerKey] = useState(0)
  const { sessionId, draft, loading, canvasPing } = chat
  const railSize = useResizableWidth('qk3.asst.rail', 240, 180, 420)
  const dockSize = useResizableWidth('qk3.asst.dock', 640, 360, 1100)


  const makeRoom = () => {
    if (window.innerWidth < ROOMY_WIDTH) setRailOpen(false)
  }

  // Another conversation: its own canvas and sources.
  useEffect(() => {
    setSources([])
    setCanvasOpen(false)
    setShowPanel(false)
    setActive('canvas')
    openedFor.current = null
  }, [sessionId])

  // A conversation that already has a draft shows it when loaded.
  useEffect(() => {
    if (draft && !loading && sessionId !== null && openedFor.current !== sessionId) {
      openedFor.current = sessionId
      setCanvasOpen(true)
      setActive('canvas')
      makeRoom()
    }
  }, [draft, loading, sessionId])

  // The assistant created or changed the draft during a turn.
  useEffect(() => {
    if (canvasPing === handledPing.current) return
    handledPing.current = canvasPing
    openedFor.current = sessionId
    setCanvasOpen(true)
    setActive('canvas')
    makeRoom()
  }, [canvasPing, sessionId])

  useEffect(() => {
    if (!draft) setCanvasOpen(false)
  }, [draft])

  const openSource = (source: SourceRef) => {
    // A document opened from a step has no cited passage: keep a citation that is already open.
    setSources((current) => {
      const existing = current.find((item) => item.key === source.key)
      if (!existing) return [...current, source]
      return current.map((item) => (item.key === source.key && (source.n !== null || existing.n === null) ? source : item))
    })
    setActive(source.key)
    setShowPanel(true)
    makeRoom()
  }
  const openCitation = (citation: Citation) => {
    const source = sourceFromCitation(citation)
    if (source) openSource(source)
  }
  const openStepDocument = (reference: StepDocumentRef) => {
    const source = sourceFromStepRef(reference)
    if (source) openSource(source)
  }

  const closeTab = (key: string) => {
    if (key === 'canvas') setCanvasOpen(false)
    else setSources((current) => current.filter((item) => item.key !== key))
  }

  const tabs: PanelTab[] = []
  if (draft && canvasOpen && sessionId !== null) {
    tabs.push({
      key: 'canvas',
      label: `Dự thảo ${draft.template.name.toLowerCase()}`,
      lead: <Icon name="canvas" size={18} />,
      closable: false,
      content: (
        <CanvasPanel
          sessionId={sessionId}
          draft={draft}
          running={chat.running}
          onDraft={chat.setDraft}
          onClose={() => closeTab('canvas')}
          onAsk={(prompt, context) => {
            setShowPanel(true)
            void chat.send(prompt, { canvas: true, context, withFiles: false })
          }}
        />
      ),
    })
  }
  if (sessionId !== null) {
    for (const source of sources) {
      tabs.push({
        key: source.key,
        label: source.ref || source.title,
        lead: <SourceTabLead source={source} names={chat.attachmentNames} />,
        closable: true,
        content: (
          <SourcePanel
            source={source}
            sessionId={sessionId}
            attachmentNames={chat.attachmentNames}
            busy={chat.running}
            onSummarize={(item) => {
              setShowPanel(false)
              void chat.send(`Tóm tắt văn bản ${item.ref || item.title}.`, { withFiles: false })
            }}
          />
        ),
      })
    }
  }
  const activeKey = tabs.some((tab) => tab.key === active) ? active : (tabs[0]?.key ?? '')
  const hasPanel = tabs.length > 0

  const choose = (id: string | null) => {
    chat.select(id)
    setPrefill(null)
    setComposerKey((value) => value + 1)
    if (narrow) setRailOpen(false)
  }

  const startWith = (id: StarterId) => {
    if (id === 'compose') chat.setCanvasOn(true)
    setPrefill({ text: STARTER_TEXT[id], nonce: Date.now() })
  }

  const openCanvas = () => {
    setCanvasOpen(true)
    setActive('canvas')
    setShowPanel(true)
    makeRoom()
  }

  const sessionTitle = sessionId !== null ? chat.sessions.find((session) => session.id === sessionId)?.title : undefined
  const title = sessionTitle || (sessionId !== null ? 'Cuộc trò chuyện' : 'Cuộc trò chuyện mới')
  usePageMeta({
    title: sessionTitle ? `${sessionTitle} · Trợ lý AI` : 'Trợ lý AI',
    crumbs: sessionTitle ? [{ label: 'Trợ lý AI', to: '/tro-ly' }, { label: sessionTitle }] : [{ label: 'Trợ lý AI' }],
  })

  return (
    <div className="asst" data-panel={hasPanel ? 'yes' : 'no'} data-show-panel={showPanel ? 'yes' : 'no'}>
      <div className="asst__body">
        {railOpen && (
          <>
            {narrow && <div className="asst__scrim" onClick={() => setRailOpen(false)} aria-hidden="true" />}
            <div className="asst__rail" id="asst-rail" style={narrow ? undefined : { flexBasis: railSize.width }}>
              <SessionList
                sessions={chat.sessions}
                activeId={sessionId}
                loading={chat.sessionsLoading}
                error={chat.sessionsError}
                onSelect={choose}
                onNew={() => choose(null)}
                onRename={chat.rename}
                onDelete={chat.remove}
                onReload={() => void chat.loadSessions()}
              />
              <ResizeHandle size={railSize} edge="right" label="Độ rộng danh sách cuộc trò chuyện" />
            </div>
          </>
        )}
        <section className="asst__conv" aria-label="Cuộc trò chuyện">
          <header className="asst__bar">
            <IconButton
              icon={railOpen ? 'panelLeftClose' : 'panelLeftOpen'}
              label={railOpen ? 'Ẩn danh sách cuộc trò chuyện' : 'Hiện danh sách cuộc trò chuyện'}
              aria-expanded={railOpen}
              aria-controls="asst-rail"
              onClick={() => setRailOpen((open) => !open)}
            />
            <h1 className="asst__title">{title}</h1>
            {user && (
              <span className="asst__scope" title={`Trợ lý chỉ tìm trong văn bản của ${user.unit_name} và các đơn vị trực thuộc mà bạn được phép xem`}>
                Phạm vi tìm: {user.unit_name} · mức {user.role === 'commander' ? 'Thường, Mật' : 'Thường'}
              </span>
            )}
            <div className="asst__bar-actions">
              {chat.messages.length > 0 && !chat.running && (
                <Button icon="download" onClick={() => exportConversation(title, chat.messages)}>Xuất cuộc trò chuyện</Button>
              )}
              {draft && !canvasOpen && <Button icon="canvas" onClick={openCanvas}>Mở Canvas</Button>}
              {narrow && hasPanel && !showPanel && <Button icon="canvas" onClick={() => setShowPanel(true)}>Canvas và nguồn</Button>}
            </div>
          </header>
          <Transcript
            messages={chat.messages}
            attachmentNames={chat.attachmentNames}
            loading={chat.loading}
            error={chat.loadError}
            running={chat.running}
            hasDraft={draft !== null}
            onRetry={chat.reload}
            onOpenCitation={openCitation}
            onOpenDocument={openStepDocument}
            onStarter={startWith}
            onRegenerate={(question) => void chat.send(question.content, { attachmentIds: question.attachment_ids, withFiles: false })}
            onOpenCanvas={openCanvas}
          />
          {chat.notice && (
            <div className="asst__notice">
              <Alert kind="warning" action={<button type="button" className="btn" onClick={() => chat.setNotice(null)}>Đóng</button>}>{chat.notice}</Alert>
            </div>
          )}
          <Composer
            // Choosing another conversation starts with an empty box.
            key={composerKey}
            files={chat.files}
            canvasOn={chat.canvasOn}
            running={chat.running}
            stopping={chat.stopping}
            disabled={chat.loading}
            prefill={prefill}
            placeholder={chat.canvasOn ? 'Mô tả văn bản cần soạn, ví dụ: công văn đề nghị cấp bổ sung vật tư…' : undefined}
            onCanvasChange={chat.setCanvasOn}
            onAddFiles={(files) => void chat.addFiles(files)}
            onRemoveFile={chat.removeFile}
            onWarm={chat.warm}
            onSend={(text) => void chat.send(text).then((sent) => !sent && setPrefill({ text, nonce: Date.now() }))}
            onStop={chat.stop}
          />
          <div className="sr-only" role="status" aria-live="polite">{chat.running ? 'Trợ lý đang xử lý yêu cầu' : ''}</div>
        </section>
        {hasPanel && <SidePanel tabs={tabs} active={activeKey} onSelect={setActive} onClose={closeTab} onBack={() => setShowPanel(false)} size={narrow ? undefined : dockSize} />}
      </div>
    </div>
  )
}
