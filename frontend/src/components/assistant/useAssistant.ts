import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError, chatApi } from '../../api'
import type { ChatDraft, ChatSession, ChatStep, SendBody } from '../../api/chat'
import { ACCEPTED_EXTENSIONS } from './Composer'
import type { ComposerFile, UiMessage } from './types'

/** How often a file that is still being indexed is asked about. */
const POLL_MS = 1500
/** A turn that was running when the page was opened is looked up again this often, for at most WAIT_TRIES times. */
const WAIT_MS = 2000
const WAIT_TRIES = 60
/** The assistant is warmed up at most this often per conversation. */
const WARM_EVERY_MS = 30_000
/** After "stop" the server is given this long to end the stream itself before the request is cut. */
const STOP_GRACE_MS = 4000

const messageOf = (error: unknown, fallback: string): string => (error instanceof Error && error.message ? error.message : fallback)
const isAbort = (error: unknown): boolean => error instanceof DOMException && error.name === 'AbortError'

/** The server refused the message before the stream started (empty, attachment not ready, conversation busy). */
const isRefusal = (error: unknown): boolean => error instanceof ApiError && (error.status === 409 || error.status === 422)

const PENDING_KEY = 'pending'

/** A step arrives first as `running` and again when it ends: replace by id, keep the order of first appearance. */
function upsertStep(steps: ChatStep[], step: ChatStep): ChatStep[] {
  const index = steps.findIndex((existing) => String(existing.id) === String(step.id))
  if (index < 0) return [...steps, step]
  return steps.map((existing, i) => (i === index ? step : existing))
}

/** When a turn ends early, steps that were still running can no longer finish. */
const settleSteps = (steps: ChatStep[]): ChatStep[] =>
  steps.map((step) => (step.status === 'running' ? { ...step, status: 'error', summary: step.summary || 'Chưa hoàn thành' } : step))

export interface SendOptions {
  /** The Canvas chip is on (or the request is about the draft). */
  canvas?: boolean
  /** The block and selected text a canvas request refers to. */
  context?: SendBody['context']
  /** Attach the files of the composer (false for requests made from the canvas). */
  withFiles?: boolean
  /** Attach these (ready) attachments instead of the composer's files, for example when asking again. */
  attachmentIds?: number[]
}

/**
 * State and actions of the Trợ lý AI screen: the conversation list, the open conversation (messages, draft, files in
 * the composer) and the streaming of one turn. The open conversation is kept in the URL (`?s=<id>`); a conversation is
 * created on the first message or upload.
 */
export function useAssistant() {
  const [params, setParams] = useSearchParams()
  const sessionId = params.get('s')?.trim() || null

  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionsError, setSessionsError] = useState<string | null>(null)

  const [messages, setMessages] = useState<UiMessage[]>([])
  const [names, setNames] = useState<ReadonlyMap<number, string>>(new Map())
  const [draft, setDraft] = useState<ChatDraft | null>(null)
  const [files, setFiles] = useState<ComposerFile[]>([])
  const [canvasOn, setCanvasOn] = useState(false)
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [stopping, setStopping] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  /** Increases whenever the server reports a draft change during a turn; the screen opens the canvas on it. */
  const [canvasPing, setCanvasPing] = useState(0)
  const [pollTick, setPollTick] = useState(0)
  const [reloadTick, setReloadTick] = useState(0)
  const [waitTick, setWaitTick] = useState(0)
  const [awaiting, setAwaiting] = useState(false)

  const idRef = useRef<string | null>(sessionId)
  const loadedRef = useRef<string | null>(null)
  const creatingRef = useRef<Promise<string> | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const turnRef = useRef(0)
  const runningRef = useRef(false)
  const warmedRef = useRef(new Map<string, number>())
  const stopAskedRef = useRef(false)
  const counter = useRef(0)
  const filesRef = useRef<ComposerFile[]>([])
  const messagesRef = useRef<UiMessage[]>([])
  /** Conversations this visit created (a first keystroke or upload makes one); an unused one is removed again when left. */
  const createdRef = useRef(new Set<string>())
  /** The id in the address bar the last time it changed. */
  const urlIdRef = useRef<string | null>(sessionId)
  useEffect(() => {
    // `idRef` runs ahead of the address bar while a conversation is being created (the router updates a moment later),
    // so it follows the URL only when the URL itself changes.
    if (urlIdRef.current !== sessionId) {
      urlIdRef.current = sessionId
      idRef.current = sessionId
    }
    filesRef.current = files
    messagesRef.current = messages
  })

  /* ---------- conversation list ---------- */

  const loadSessions = useCallback(async (silent = false) => {
    if (!silent) setSessionsLoading(true)
    try {
      setSessions(await chatApi.listSessions())
      setSessionsError(null)
    } catch (error) {
      if (!silent) setSessionsError(messageOf(error, 'Không tải được danh sách cuộc trò chuyện.'))
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  /* ---------- open conversation ---------- */

  /**
   * Stops listening to the running turn (if any). The server keeps answering and saves the result, so leaving a
   * conversation does not cancel it; only the Stop button does.
   */
  const endTurn = useCallback(() => {
    turnRef.current += 1
    const controller = abortRef.current
    abortRef.current = null
    controller?.abort()
    runningRef.current = false
    setRunning(false)
    setStopping(false)
    setAwaiting(false)
  }, [])

  /** Starts the assistant for a conversation in the background (at most every WARM_EVERY_MS). */
  const warmNow = useCallback((id: string) => {
    const last = warmedRef.current.get(id) ?? 0
    if (Date.now() - last < WARM_EVERY_MS) return
    warmedRef.current.set(id, Date.now())
    chatApi.warmSession(id)
  }, [])

  useEffect(() => {
    if (loadedRef.current === sessionId && sessionId !== null) return
    endTurn()
    setFiles([])
    setNotice(null)
    setCanvasOn(false)
    if (sessionId === null) {
      loadedRef.current = null
      setMessages([])
      setNames(new Map())
      setDraft(null)
      setLoadError(null)
      setLoading(false)
      return
    }
    const controller = new AbortController()
    setLoading(true)
    setLoadError(null)
    setMessages([])
    setDraft(null)
    chatApi
      .getSession(sessionId, controller.signal)
      .then((detail) => {
        if (controller.signal.aborted) return
        loadedRef.current = sessionId
        setMessages(detail.messages.map((message) => ({ ...message, key: `m${message.id}` })))
        setNames(new Map(detail.attachments.map((attachment) => [attachment.id, attachment.name])))
        setDraft(detail.draft)
        setLoading(false)
        warmNow(sessionId)
        // A question without an answer: the turn is still running on the server (the page was reloaded meanwhile).
        const lastMessage = detail.messages[detail.messages.length - 1]
        if (lastMessage?.role === 'user') setWaitTick((value) => value + 1)
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return
        setLoadError(messageOf(error, 'Không tải được cuộc trò chuyện.'))
        setLoading(false)
      })
    return () => controller.abort()
    // endTurn and warmNow are stable; the conversation is (re)loaded only when the id or the retry counter changes.
  }, [sessionId, reloadTick, endTurn, warmNow])

  useEffect(() => () => endTurn(), [endTurn])

  // The last question has no answer yet: its turn is still running on the server. Show it as pending and look again until the answer is saved.
  useEffect(() => {
    if (waitTick === 0 || sessionId === null) return
    let cancelled = false
    setAwaiting(true)
    const stamp = new Date().toISOString()
    // After "stop" the last row is the local one that ended the turn; it is replaced by what the server saved.
    setMessages((current) =>
      current[current.length - 1]?.role === 'assistant'
        ? current
        : [...current, { key: PENDING_KEY, id: -1, role: 'assistant', content: '', steps: [], citations: [], status: 'running', attachment_ids: [], created_at: stamp, fresh: true }],
    )
    void (async () => {
      for (let attempt = 0; attempt < WAIT_TRIES; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, WAIT_MS))
        if (cancelled) return
        try {
          const detail = await chatApi.getSession(sessionId)
          if (cancelled) return
          if (detail.messages[detail.messages.length - 1]?.role === 'assistant') {
            setMessages(detail.messages.map((message, index) => ({ ...message, key: `m${message.id}`, fresh: index === detail.messages.length - 1 })))
            setDraft(detail.draft)
            setAwaiting(false)
            setStopping(false)
            void loadSessions(true)
            return
          }
        } catch {
          // Try again on the next round.
        }
      }
      if (cancelled) return
      setMessages((current) =>
        current.map((message) => (message.key === PENDING_KEY ? { ...message, status: 'error', error: 'Chưa nhận được câu trả lời. Tải lại cuộc trò chuyện sau ít phút hoặc hỏi lại.' } : message)),
      )
      setAwaiting(false)
      setStopping(false)
    })()
    return () => {
      cancelled = true
    }
  }, [waitTick, sessionId, loadSessions])

  /** Removes the open conversation when this visit created it and nothing was ever asked in it. */
  const discardIfUnused = useCallback(() => {
    const id = idRef.current
    if (id === null || !createdRef.current.has(id) || messagesRef.current.length > 0 || runningRef.current) return
    createdRef.current.delete(id)
    setSessions((current) => current.filter((session) => session.id !== id))
    void chatApi.deleteSession(id).catch(() => undefined)
  }, [])

  const select = useCallback(
    (id: string | null) => {
      if (id !== idRef.current) discardIfUnused()
      setParams(id === null ? {} : { s: String(id) })
    },
    [setParams, discardIfUnused],
  )

  // Leaving the page with an empty conversation of this visit.
  useEffect(() => discardIfUnused, [discardIfUnused])

  // Closing or reloading the tab with an empty conversation of this visit (no unmount runs then).
  useEffect(() => {
    const onPageHide = () => {
      const id = idRef.current
      if (id === null || !createdRef.current.has(id) || messagesRef.current.length > 0 || runningRef.current) return
      createdRef.current.delete(id)
      chatApi.deleteSessionOnExit(id)
    }
    window.addEventListener('pagehide', onPageHide)
    return () => window.removeEventListener('pagehide', onPageHide)
  }, [])

  const reload = useCallback(() => {
    loadedRef.current = null
    setReloadTick((value) => value + 1)
  }, [])

  /** The id of the open conversation, creating one first when the screen is on a blank page. */
  const ensureSession = useCallback(async (): Promise<string> => {
    if (idRef.current !== null) return idRef.current
    if (!creatingRef.current) {
      creatingRef.current = (async () => {
        try {
          const created = await chatApi.createSession()
          createdRef.current.add(created.id)
          loadedRef.current = created.id
          idRef.current = created.id
          warmNow(created.id)
          // The row appears in the list with the first message (see `onSession`), not while the box is only focused.
          setParams({ s: String(created.id) }, { replace: true })
          return created.id
        } finally {
          creatingRef.current = null
        }
      })()
    }
    return creatingRef.current
  }, [setParams, warmNow])

  /** The composer was focused or typed in: get the assistant ready (a blank page gets its conversation now, so the start-up overlaps with typing). */
  const warm = useCallback(
    () => {
      const id = idRef.current
      if (id !== null) warmNow(id)
      else void ensureSession().catch(() => undefined)
    },
    [ensureSession, warmNow],
  )

  const rename = useCallback(async (id: string, title: string) => {
    const updated = await chatApi.renameSession(id, title)
    setSessions((current) => current.map((session) => (session.id === id ? updated : session)))
  }, [])

  const remove = useCallback(
    async (id: string) => {
      await chatApi.deleteSession(id)
      setSessions((current) => current.filter((session) => session.id !== id))
      if (idRef.current === id) select(null)
    },
    [select],
  )

  /* ---------- files in the composer ---------- */

  const addFiles = useCallback(
    async (list: File[]) => {
      const accepted = list.filter((file) => ACCEPTED_EXTENSIONS.some((extension) => file.name.toLowerCase().endsWith(extension)))
      const skipped = list.length - accepted.length
      setNotice(skipped > 0 ? `Chỉ nhận tệp .docx, .doc hoặc .pdf. Đã bỏ qua ${skipped} tệp.` : null)
      if (accepted.length === 0) return
      const items: ComposerFile[] = accepted.map((file) => ({
        key: `f${++counter.current}`, name: file.name, size: file.size, progress: 0, attachment: null, error: null,
      }))
      setFiles((current) => [...current, ...items])
      const update = (key: string, change: Partial<ComposerFile>) =>
        setFiles((current) => current.map((file) => (file.key === key ? { ...file, ...change } : file)))
      let sid: string
      try {
        sid = await ensureSession()
      } catch (error) {
        for (const item of items) update(item.key, { error: messageOf(error, 'Không tạo được cuộc trò chuyện.') })
        return
      }
      await Promise.all(
        items.map(async (item, index) => {
          try {
            const attachment = await chatApi.uploadAttachment(sid, accepted[index] as File, (progress) => update(item.key, { progress }))
            update(item.key, { attachment, progress: 1 })
            setNames((current) => new Map(current).set(attachment.id, attachment.name))
          } catch (error) {
            update(item.key, { error: messageOf(error, 'Không tải lên được.') })
          }
        }),
      )
    },
    [ensureSession],
  )

  const removeFile = useCallback((key: string) => {
    const file = filesRef.current.find((candidate) => candidate.key === key)
    setFiles((current) => current.filter((candidate) => candidate.key !== key))
    if (file?.attachment && idRef.current !== null) void chatApi.deleteAttachment(idRef.current, file.attachment.id).catch(() => undefined)
  }, [])

  // Ask again every POLL_MS about files that are still queued or being indexed.
  const waiting = files
    .filter((file) => file.attachment && (file.attachment.state === 'queued' || file.attachment.state === 'processing'))
    .map((file) => file.attachment?.id)
    .join(',')
  useEffect(() => {
    if (!waiting || sessionId === null) return
    let cancelled = false
    const timer = window.setTimeout(async () => {
      const latest = await Promise.all(waiting.split(',').map((id) => chatApi.getAttachment(sessionId, Number(id)).catch(() => null)))
      if (cancelled) return
      setFiles((current) =>
        current.map((file) => {
          const fresh = latest.find((attachment) => attachment && attachment.id === file.attachment?.id)
          return fresh ? { ...file, attachment: fresh } : file
        }),
      )
      setPollTick((value) => value + 1)
    }, POLL_MS)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [waiting, sessionId, pollTick])

  /* ---------- one turn ---------- */

  /** Sends a question and follows the answer. Resolves false when nothing was sent (the text should go back to the box). */
  const send = useCallback(
    async (text: string, options: SendOptions = {}): Promise<boolean> => {
      if (runningRef.current) return false
      runningRef.current = true
      stopAskedRef.current = false
      setRunning(true)
      setNotice(null)
      let sid: string
      try {
        sid = await ensureSession()
      } catch (error) {
        runningRef.current = false
        setRunning(false)
        setNotice(messageOf(error, 'Không tạo được cuộc trò chuyện.'))
        return false
      }

      const canvasRequested = options.canvas ?? canvasOn
      const withFiles = options.withFiles !== false
      const attached = withFiles && !options.attachmentIds ? filesRef.current.filter((file) => file.attachment?.state === 'ready') : []
      const attachmentIds = options.attachmentIds ?? attached.flatMap((file) => (file.attachment ? [file.attachment.id] : []))
      if (withFiles) setFiles([])
      // The Canvas chip is for this message only; later messages still see the open draft on the server.
      if (options.canvas === undefined) setCanvasOn(false)

      const n = ++counter.current
      const startedAt = Date.now()
      const created = new Date().toISOString()
      const liveKey = `a${n}`
      const base = { steps: [], citations: [], created_at: created }
      setMessages((current) => [
        ...current,
        { ...base, key: `u${n}`, id: -2 * n, role: 'user', content: text, status: 'done', attachment_ids: attachmentIds },
        { ...base, key: liveKey, id: -2 * n - 1, role: 'assistant', content: '', status: 'running', attachment_ids: [], fresh: true, startedAt },
      ])

      const token = ++turnRef.current
      const controller = new AbortController()
      abortRef.current = controller
      const patch = (change: (message: UiMessage) => UiMessage) => {
        if (token === turnRef.current) setMessages((current) => current.map((message) => (message.key === liveKey ? change(message) : message)))
      }
      const fail = (reason: string) =>
        patch((message) => (message.status === 'running' ? { ...message, status: 'error', error: reason, steps: settleSteps(message.steps) } : message))

      let finished = false
      let started = false
      let refused = false
      try {
        await chatApi.streamMessage(
          sid,
          { text, attachment_ids: attachmentIds, canvas: canvasRequested, context: options.context },
          {
            onSession: (event) => {
              started = true
              if (token !== turnRef.current) return
              setMessages((current) => current.map((message) => (message.key === `u${n}` ? { ...message, id: event.user_message_id } : message)))
              const now = new Date().toISOString()
              setSessions((current) =>
                current.some((session) => session.id === sid)
                  ? current.map((session) => (session.id === sid ? { ...session, title: event.title || session.title } : session))
                  : [{ id: sid, title: event.title || 'Cuộc trò chuyện mới', created_at: now, updated_at: now }, ...current],
              )
            },
            onModeration: (event) => {
              if (token === turnRef.current) setNotice(event.message)
            },
            onStep: (step) => patch((message) => ({ ...message, steps: upsertStep(message.steps, step) })),
            onCanvas: (next) => {
              if (token !== turnRef.current) return
              setDraft(next)
              setCanvasPing((value) => value + 1)
            },
            onAnswer: ({ text: answer, citations }) => patch((message) => ({ ...message, content: answer, citations })),
            onError: (reason) => fail(reason),
            onDone: ({ message_id, status }) => {
              finished = true
              patch((message) => ({
                ...message,
                id: message_id,
                durationMs: Date.now() - startedAt,
                status: message.status === 'error' || status === 'error' ? 'error' : status === 'stopped' ? 'stopped' : 'done',
                steps: status === 'done' ? message.steps : settleSteps(message.steps),
              }))
            },
          },
          controller.signal,
        )
        if (!finished) fail('Kết nối bị gián đoạn trước khi trợ lý trả lời xong.')
      } catch (error) {
        if (isAbort(error)) {
          patch((message) => (message.status === 'running' ? { ...message, status: 'stopped', steps: settleSteps(message.steps) } : message))
          // The server did not end the turn in time (it can still be starting up): follow it until its result is saved.
          if (stopAskedRef.current && token === turnRef.current) setWaitTick((value) => value + 1)
        } else if (!started && isRefusal(error)) {
          // Refused before the stream began: take the question back out of the transcript and give the text back.
          refused = true
          if (token === turnRef.current) {
            setMessages((current) => current.filter((message) => message.key !== `u${n}` && message.key !== liveKey))
            setNotice(error instanceof ApiError && error.status === 409 ? 'Trợ lý đang trả lời tin nhắn trước. Đợi câu trả lời xong rồi gửi lại.' : messageOf(error, 'Không gửi được tin nhắn.'))
          }
        } else {
          fail(messageOf(error, 'Không gửi được tin nhắn.'))
        }
      } finally {
        if (token === turnRef.current) {
          abortRef.current = null
          runningRef.current = false
          setRunning(false)
          setStopping(false)
        }
        void loadSessions(true)
      }
      return !refused
    },
    [canvasOn, ensureSession, loadSessions],
  )

  /**
   * Stops the running turn: the server is told and normally ends the stream with a "stopped" result (keeping the steps
   * done so far); if it does not within a few seconds the request is cut.
   */
  const stop = useCallback(() => {
    const id = idRef.current
    if (id === null) return
    setStopping(true)
    stopAskedRef.current = true
    void chatApi.stopSession(id).catch(() => undefined)
    const controller = abortRef.current
    if (controller) window.setTimeout(() => controller.abort(), STOP_GRACE_MS)
  }, [])

  return {
    sessionId,
    sessions, sessionsLoading, sessionsError, loadSessions,
    messages, attachmentNames: names, loading, loadError, reload,
    draft, setDraft,
    files, addFiles, removeFile,
    canvasOn, setCanvasOn,
    running: running || awaiting, stopping, notice, setNotice, canvasPing,
    select, rename, remove, send, stop, warm, ensureSession,
  }
}
