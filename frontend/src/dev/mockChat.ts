/**
 * Development stand-in for the chat backend, used only when `VITE_MOCK_CHAT=1` (see src/api/chat.ts, which loads this
 * file with a dynamic import behind that check, so it is not part of a normal build). It keeps sessions in memory and
 * replays a plausible server-sent-event sequence for every message. All text is made up.
 */
import type { RequestOptions } from '../api/client'
import type {
  ChatAttachment,
  ChatDraft,
  ChatMessage,
  ChatSession,
  ChatStep,
  Citation,
  DraftCheck,
  DraftPatch,
  SendBody,
} from '../api/chat'
import type { DocumentSummary, Paragraph } from '../api/types'

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    })
  })

const now = () => new Date().toISOString()

/* ---------- source documents ---------- */

const para = (pi: number, text: string, extra: Partial<Paragraph> = {}): Paragraph => ({
  pi, text, align: 'justify', bold: false, italic: false, table: null, row: null, col: null, ...extra,
})

const DOCS: Record<number, Paragraph[]> = {
  101: [
    para(0, 'PHÒNG THAM MƯU', { align: 'center', bold: true }),
    para(1, 'Số: 24/KH-PTM', { align: 'center' }),
    para(2, 'KẾ HOẠCH', { align: 'center', bold: true }),
    para(3, 'Tập huấn Công binh năm 2026', { align: 'center', bold: true }),
    para(4, 'I. MỤC ĐÍCH, YÊU CẦU', { bold: true }),
    para(5, 'Nâng cao trình độ chuyên môn, kỹ thuật cho cán bộ, chiến sĩ công binh; bảo đảm an toàn tuyệt đối trong quá trình huấn luyện.'),
    para(6, 'II. NỘI DUNG, THỜI GIAN', { bold: true }),
    para(7, 'Thời gian tập huấn 05 ngày, từ ngày 20/4 đến hết ngày 24/4/2026; địa điểm tại thao trường của đơn vị.'),
    para(8, 'Nội dung gồm rà phá bom mìn, xây dựng công sự, cầu đường.'),
    para(9, 'III. TỔ CHỨC THỰC HIỆN', { bold: true }),
    para(10, 'Phòng Hậu cần bảo đảm vật tư, trang bị; Phòng Tham mưu theo dõi, tổng hợp kết quả.'),
  ],
  102: [
    para(0, 'PHÒNG THAM MƯU', { align: 'center', bold: true }),
    para(1, 'Số: 31/HD-PTM', { align: 'center' }),
    para(2, 'HƯỚNG DẪN', { align: 'center', bold: true }),
    para(3, 'Báo cáo kết quả tập huấn', { align: 'center', bold: true }),
    para(4, '1. Yêu cầu chung', { bold: true }),
    para(5, 'Báo cáo phản ánh đầy đủ nội dung, thời gian và kết quả kiểm tra sau tập huấn.'),
    para(6, '2. Mẫu báo cáo', { bold: true }),
    para(7, 'Đơn vị sử dụng mẫu báo cáo kèm theo hướng dẫn này.'),
    para(8, '3. Thời hạn', { bold: true }),
    para(9, 'Các đơn vị gửi báo cáo kết quả tập huấn về Phòng Tham mưu trước 17 giờ ngày 30/4/2026 bằng văn bản điện tử.'),
  ],
}

const ATTACHMENT_TEXT: Paragraph[] = [
  para(0, 'CÔNG VĂN', { align: 'center', bold: true }),
  para(1, 'Đề nghị cấp vật tư phục vụ huấn luyện (tệp tạm trong cuộc trò chuyện).'),
  para(2, 'Danh mục gồm dụng cụ rà phá, vật liệu xây dựng công sự và trang bị bảo hộ.'),
]

/* ---------- state ---------- */

interface MockSession {
  session: ChatSession
  messages: ChatMessage[]
  attachments: (ChatAttachment & { bornAt: number })[]
  draft: ChatDraft | null
}

let nextId = 100
const store = new Map<string, MockSession>()

const CITATIONS: Citation[] = [
  {
    n: 1, doc_id: 101, kind: 'store', title: 'Kế hoạch tập huấn Công binh năm 2026', ref: '24/KH-PTM', doc_type: 'Kế hoạch',
    date: '2026-03-12', unit_name: 'Phòng Tham mưu', section: 'mục II', pi: [7, 7], readable: true,
    text: 'Thời gian tập huấn 05 ngày, từ ngày 20/4 đến hết ngày 24/4/2026; địa điểm tại thao trường của đơn vị.',
  },
  {
    n: 2, doc_id: 102, kind: 'store', title: 'Hướng dẫn báo cáo kết quả tập huấn', ref: '31/HD-PTM', doc_type: 'Hướng dẫn',
    date: '2026-04-02', unit_name: 'Phòng Tham mưu', section: 'mục 3', pi: [9, 9], readable: true,
    text: 'Các đơn vị gửi báo cáo kết quả tập huấn về Phòng Tham mưu trước 17 giờ ngày 30/4/2026 bằng văn bản điện tử.',
  },
  {
    n: 3, doc_id: 103, kind: 'store', title: 'Quy định bảo đảm vật tư (hạn chế)', ref: '07/QĐ-HC', doc_type: 'Quyết định',
    date: '2026-01-05', unit_name: 'Phòng Hậu cần', section: 'Điều 4', pi: [-1, -1], readable: false, text: '',
  },
]

function makeDraft(): ChatDraft {
  const f = (text: string, owner: 'system' | 'assistant' | 'user', label: string, extra: { needs_input?: boolean; multiline?: boolean } = {}) => ({
    label, text, owner, needs_input: extra.needs_input ?? false, multiline: extra.multiline ?? false,
  })
  return {
    id: 1,
    title: 'Công văn đề nghị cấp vật tư',
    version: 1,
    updated_at: now(),
    template: { code: 'M08', kind: 'CV', name: 'Công văn', doc_type: 'CV', authority: 'Thông tư 68/2023/TT-BQP' },
    fields: {
      co_quan_chu_quan: f('BỘ TƯ LỆNH QUÂN KHU 3', 'system', 'Cơ quan chủ quản'),
      co_quan_ban_hanh: f('PHÒNG THAM MƯU', 'system', 'Cơ quan ban hành'),
      so_ky_hieu: f('Số:      /CV-PTM', 'system', 'Số, ký hiệu'),
      quoc_hieu: f('CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM', 'system', 'Quốc hiệu'),
      tieu_ngu: f('Độc lập - Tự do - Hạnh phúc', 'system', 'Tiêu ngữ'),
      dia_danh_ngay: f('', 'user', 'Địa danh, ngày tháng', { needs_input: true }),
      trich_yeu: f('đề nghị cấp bổ sung vật tư phục vụ tập huấn Công binh', 'assistant', 'Trích yếu'),
      kinh_gui: f('Phòng Hậu cần', 'assistant', 'Kính gửi'),
      quyen_han: f('THỦ TRƯỞNG PHÒNG', 'assistant', 'Quyền hạn người ký'),
      nguoi_ky: f('', 'user', 'Cấp bậc, họ và tên người ký', { needs_input: true }),
      noi_nhan: f('- Như trên;\n- Lưu: VT, TM (A5).', 'assistant', 'Nơi nhận', { multiline: true }),
    },
    blocks: [
      {
        id: 'b1', kind: 'para', owner: 'assistant', proposal: null,
        text: 'Thực hiện Kế hoạch số 24/KH-PTM ngày 12/3/2026 về tập huấn Công binh năm 2026, Phòng Tham mưu đề nghị Phòng Hậu cần cấp bổ sung vật tư cho đợt tập huấn từ ngày 20/4 đến ngày 24/4/2026.',
      },
      {
        id: 'b2', kind: 'para', owner: 'assistant', proposal: null,
        text: 'Vật tư đề nghị gồm: dụng cụ rà phá, vật liệu xây dựng công sự và trang bị bảo hộ. Số lượng cụ thể có phụ lục kèm theo.',
      },
      { id: 'b3', kind: 'para', owner: 'assistant', proposal: null, text: 'Đề nghị Phòng Hậu cần sớm cấp vật tư.' },
      { id: 'b4', kind: 'para', owner: 'assistant', proposal: null, text: 'Phòng Tham mưu trân trọng đề nghị./.' },
    ],
    missing: ['dia_danh_ngay', 'nguoi_ky'],
    style: { preset: 'don_vi', detail: 'vua' },
    style_options: {
      presets: [{ id: 'don_vi', name: 'Chuẩn đơn vị' }, { id: 'lanh_dao', name: 'Báo cáo lãnh đạo' }, { id: 'chi_dao', name: 'Chỉ đạo cấp dưới' }],
      detail: [{ id: 'ngan', name: 'Ngắn' }, { id: 'vua', name: 'Vừa' }, { id: 'day_du', name: 'Đầy đủ' }],
    },
    history: [{ version: 1, at: now(), by: 'assistant', summary: 'Dựng bản dự thảo theo mẫu Công văn' }],
  }
}

function seed(): void {
  if (store.size > 0) return
  const thinking: ChatStep = {
    id: 't1', kind: 'thinking', title: 'Đã suy nghĩ 6 giây', summary: 'Cần tìm kế hoạch tập huấn 2026 và văn bản hướng dẫn báo cáo',
    status: 'done', duration_ms: 6000, tool: null, detail: { text: 'Người dùng hỏi về tập huấn Công binh 2026 và hạn nộp báo cáo.\nCần tìm kế hoạch và hướng dẫn báo cáo.' },
  }
  const search: ChatStep = {
    id: 's1', kind: 'tool', title: 'Tìm văn bản', summary: 'từ khóa · “tập huấn công binh 2026” · 6 đoạn trong 2 văn bản · 0,4 giây', status: 'done',
    duration_ms: 400, tool: 'search_documents',
    detail: {
      arguments: { query: 'tập huấn công binh 2026' },
      result: { count: 6, documents: [{ doc_id: 101, label: '24/KH-PTM', section: 'mục II' }, { doc_id: 102, label: '31/HD-PTM', section: 'mục 3' }] },
    },
  }
  const first: MockSession = {
    session: { id: 'mock1', title: 'Tập huấn Công binh 2026', created_at: now(), updated_at: now() },
    messages: [
      { id: 1, role: 'user', content: 'Tóm tắt các văn bản về tập huấn Công binh năm 2026 và cho biết hạn nộp báo cáo kết quả.', steps: [], citations: [], status: 'done', attachment_ids: [], created_at: now() },
      {
        id: 2, role: 'assistant', status: 'done', attachment_ids: [], created_at: now(), steps: [thinking, search], citations: CITATIONS.slice(0, 2),
        content: 'Có hai văn bản liên quan trong phạm vi quyền của bạn.\n\n**Kế hoạch tập huấn Công binh năm 2026** (24/KH-PTM, ngày 12/3/2026)[1]\n\n- Mục đích: nâng cao năng lực rà phá, xây dựng công sự cho cán bộ, chiến sĩ công binh.\n- Thời gian 05 ngày, từ 20/4 đến 24/4/2026, tại thao trường của đơn vị.\n\n**Hướng dẫn báo cáo kết quả tập huấn** (31/HD-PTM, ngày 02/4/2026)[2]\n\n- **Hạn nộp báo cáo: trước 17 giờ ngày 30/4/2026**, gửi về Phòng Tham mưu bằng văn bản điện tử.[2]',
      },
    ],
    attachments: [],
    draft: null,
  }
  const second: MockSession = {
    session: { id: 'mock2', title: 'Soạn công văn đề nghị vật tư', created_at: now(), updated_at: new Date(Date.now() - 3600_000).toISOString() },
    messages: [
      { id: 3, role: 'user', content: 'Soạn công văn gửi Phòng Hậu cần đề nghị cấp bổ sung vật tư cho đợt tập huấn Công binh tháng 4.', steps: [], citations: [], status: 'done', attachment_ids: [], created_at: now() },
      { id: 4, role: 'assistant', status: 'done', attachment_ids: [], created_at: now(), steps: [], citations: [], content: 'Đã dựng bản dự thảo theo mẫu Công văn trong canvas. Còn thiếu **người ký** và **ngày tháng**.' },
    ],
    attachments: [],
    draft: makeDraft(),
  }
  const third: MockSession = {
    session: { id: 'mock3', title: 'Tóm tắt quy chế kiểm kê', created_at: now(), updated_at: new Date(Date.now() - 86400_000 * 2).toISOString() },
    messages: [],
    attachments: [],
    draft: null,
  }
  for (const entry of [first, second, third]) store.set(entry.session.id, entry)
}

function must(id: string): MockSession {
  seed()
  const entry = store.get(id)
  if (!entry) throw Object.assign(new Error('Không tìm thấy cuộc trò chuyện.'), { status: 404 })
  return entry
}

function bump(entry: MockSession, by: 'assistant' | 'user', summary: string): ChatDraft {
  const draft = entry.draft
  if (!draft) throw new Error('Chưa có bản dự thảo.')
  draft.version += 1
  draft.updated_at = now()
  draft.history.unshift({ version: draft.version, at: now(), by, summary })
  draft.missing = Object.entries(draft.fields).filter(([, field]) => field.needs_input && !field.text.trim()).map(([key]) => key)
  entry.session.updated_at = now()
  return structuredClone(draft)
}

/* ---------- request router ---------- */

export async function mockRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  await sleep(120)
  seed()
  const method = options.method ?? 'GET'
  const respond = (value: unknown) => value as T
  const body = (options.body ?? {}) as Record<string, unknown>

  if (path === '/api/chat/sessions') {
    if (method === 'GET') return respond([...store.values()].map((e) => e.session).sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
    const session: ChatSession = { id: `mock${++nextId}`, title: String(body.title ?? 'Cuộc trò chuyện mới'), created_at: now(), updated_at: now() }
    store.set(session.id, { session, messages: [], attachments: [], draft: null })
    return respond(session)
  }

  const document = /^\/api\/documents\/(\d+)\/content$/.exec(path)
  if (document) return respond(DOCS[Number(document[1])] ?? ATTACHMENT_TEXT)

  const match = /^\/api\/chat\/sessions\/([^/]+)(\/.*)?$/.exec(path)
  if (!match) throw new Error(`mockChat: unsupported ${method} ${path}`)
  const entry = must(decodeURIComponent(match[1] ?? ''))
  const rest = match[2] ?? ''

  if (rest === '') {
    if (method === 'DELETE') {
      store.delete(entry.session.id)
      return respond(undefined)
    }
    if (method === 'PATCH') {
      entry.session.title = String(body.title ?? entry.session.title)
      return respond(entry.session)
    }
    return respond(structuredClone({ session: entry.session, messages: entry.messages, attachments: entry.attachments, draft: entry.draft }))
  }
  if (rest === '/stop' || rest === '/warm') return respond(undefined)

  const attachment = /^\/attachments\/(\d+)(\/content)?$/.exec(rest)
  if (attachment) {
    const found = entry.attachments.find((a) => a.id === Number(attachment[1]))
    if (!found) throw Object.assign(new Error('Không tìm thấy tệp.'), { status: 404 })
    if (attachment[2]) return respond(ATTACHMENT_TEXT)
    if (method === 'DELETE') {
      entry.attachments = entry.attachments.filter((a) => a !== found)
      return respond(undefined)
    }
    const age = Date.now() - found.bornAt
    if (found.state !== 'failed') found.state = age < 1200 ? 'queued' : age < 3500 ? 'processing' : 'ready'
    return respond({ ...found })
  }

  if (rest === '/draft') {
    if (method === 'GET') return respond(entry.draft ? structuredClone(entry.draft) : null)
    if (method === 'DELETE') {
      entry.draft = null
      return respond(undefined)
    }
    if (method === 'PATCH' && entry.draft) {
      const patch = body as DraftPatch
      for (const [key, text] of Object.entries(patch.fields ?? {})) {
        const field = entry.draft.fields[key]
        if (field) {
          field.text = text
          field.owner = 'user'
        }
      }
      for (const change of patch.blocks ?? []) {
        const block = entry.draft.blocks.find((b) => b.id === change.id)
        if (block) {
          if (change.table) block.table = change.table
          else block.text = change.text ?? block.text
          block.owner = 'user'
        }
      }
      if (patch.delete) entry.draft.blocks = entry.draft.blocks.filter((b) => !patch.delete?.includes(b.id))
      if (patch.insert) {
        const index = patch.insert.after === null ? 0 : entry.draft.blocks.findIndex((b) => b.id === patch.insert?.after) + 1
        entry.draft.blocks.splice(index, 0, { id: `b${++nextId}`, kind: patch.insert.kind, text: patch.insert.text, owner: 'user', proposal: null,
                                              ...(patch.insert.table ? { table: patch.insert.table } : {}) })
      }
      return respond(bump(entry, 'user', 'Người dùng chỉnh sửa trực tiếp'))
    }
  }
  const proposal = /^\/draft\/blocks\/([^/]+)\/(accept|reject)$/.exec(rest)
  if (proposal && entry.draft) {
    const block = entry.draft.blocks.find((b) => b.id === decodeURIComponent(proposal[1] ?? ''))
    if (block?.proposal) {
      if (proposal[2] === 'accept') block.text = block.proposal.text
      block.proposal = null
    }
    return respond(bump(entry, 'user', proposal[2] === 'accept' ? 'Chấp nhận đề xuất' : 'Từ chối đề xuất'))
  }
  if (rest === '/draft/check') {
    await sleep(500)
    const check: DraftCheck = {
      counts: { error: 1, warning: 1, manual: 1 },
      checked_at: now(),
      findings: [
        { severity: 'error', message: 'Thiếu cấp bậc, họ tên người ký (bắt buộc).', where: 'Người ký', ref: 'Điều 8' },
        { severity: 'warning', message: 'Đoạn 2 có cỡ chữ 13pt, mẫu yêu cầu 14pt.', where: 'Nội dung, đoạn 2', ref: 'Phụ lục I' },
              ],
    }
    return respond(check)
  }
  if (rest === '/draft/save') {
    await sleep(400)
    return respond({ document: { id: 999, title: entry.draft?.title ?? 'Dự thảo', original_name: 'du-thao.docx' } as unknown as DocumentSummary })
  }
  throw new Error(`mockChat: unsupported ${method} ${path}`)
}

export async function mockUpload(sessionId: string, file: File, onProgress: (fraction: number) => void): Promise<ChatAttachment> {
  const entry = must(sessionId)
  for (let step = 1; step <= 5; step += 1) {
    await sleep(120)
    onProgress(step / 5)
  }
  const created: ChatAttachment & { bornAt: number } = {
    id: ++nextId, name: file.name, size: file.size, state: 'queued', detail: '', title: '', document_type: '', chunk_count: 0, bornAt: Date.now(),
  }
  if (/fail/i.test(file.name)) {
    created.state = 'failed'
    created.detail = 'Không đọc được nội dung tệp.'
  }
  entry.attachments.push(created)
  return { ...created }
}

export function mockExport(): Blob {
  return new Blob(['mock docx'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
}

/* ---------- event stream ---------- */

const ANSWER =
  'Đã dựng bản dự thảo **Công văn** trong canvas theo hai văn bản cùng loại trong kho.\n\n' +
  '- Quốc hiệu, tên đơn vị, ký hiệu do hệ thống điền; thời gian tập huấn lấy theo Kế hoạch 24/KH-PTM [1].\n' +
  '- Thời hạn báo cáo theo Hướng dẫn 31/HD-PTM [2]; một quy định liên quan hậu cần tôi không mở được nội dung [3].\n\n' +
  '| Nội dung | Mốc thời gian |\n| --- | --- |\n| Tập huấn | 20/4 - 24/4/2026 [1] |\n| Nộp báo cáo | trước 17 giờ ngày 30/4/2026 [2] |\n\n' +
  'Còn thiếu:\n\n1. **Người ký**\n2. **Địa danh, ngày tháng**\n\nBạn có thể bôi đen một đoạn trong canvas để nhờ tôi viết lại.'

/**
 * Builds the same bytes a server would send: `event:`/`data:` frames, deliberately cut at odd places so the client's
 * parser is exercised. Aborting `signal` errors the stream with an AbortError, like an aborted fetch.
 */
export function mockEventStream(sessionId: string, body: SendBody, signal: AbortSignal): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder()
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const send = async (event: string, data: unknown, wait = 350) => {
        await sleep(wait, signal)
        const text = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
        const cut = Math.floor(text.length / 2)
        controller.enqueue(encoder.encode(text.slice(0, cut)))
        await sleep(5, signal)
        controller.enqueue(encoder.encode(text.slice(cut)))
      }
      try {
        const entry = must(sessionId)
        const first = entry.messages.length === 0
        const userId = ++nextId
        entry.messages.push({ id: userId, role: 'user', content: body.text, steps: [], citations: [], status: 'done', attachment_ids: body.attachment_ids ?? [], created_at: now() })
        if (first) entry.session.title = body.text.slice(0, 48)
        entry.session.updated_at = now()
        await send('session', { session_id: sessionId, user_message_id: userId, title: entry.session.title }, 150)

        const step = (id: string, patch: Partial<ChatStep>): ChatStep => ({
          id, kind: 'tool', title: '', summary: '', status: 'running', duration_ms: 0, tool: null, detail: null, ...patch,
        })
        const thinking = step('t1', { kind: 'thinking', title: 'Đang suy nghĩ', summary: 'Cần tìm công văn cùng loại và hướng dẫn báo cáo' })
        await send('step', { step: thinking }, 200)
        await send('step', {
          step: { ...thinking, status: 'done', title: 'Đã suy nghĩ 6 giây', duration_ms: 6000, detail: { text: 'Yêu cầu soạn công văn.\nCần tìm hai công văn cùng loại và văn bản hướng dẫn, sau đó dựng canvas theo mẫu M08.' } },
        }, 1200)

        const s1 = step('s1', { title: 'Tìm văn bản', summary: 'từ khóa · “tập huấn công binh 2026”', tool: 'search_documents', detail: { arguments: { query: 'tập huấn công binh 2026' } } })
        const s2 = step('s2', { title: 'Tìm văn bản', summary: 'ngữ nghĩa · “thời hạn báo cáo kết quả tập huấn”', tool: 'search_documents', detail: { arguments: { query: 'thời hạn báo cáo kết quả tập huấn' } } })
        await send('step', { step: s1 }, 100)
        await send('step', { step: s2 }, 80)
        await send('step', {
          step: { ...s1, status: 'done', duration_ms: 400, summary: 'từ khóa · “tập huấn công binh 2026” · 6 đoạn trong 3 văn bản · 0,4 giây',
            detail: { ...s1.detail, result: { count: 6, documents: [{ doc_id: 101, label: '24/KH-PTM', section: 'mục II' }, { doc_id: 'att1', label: 'CV_de_nghi_vat_tu.docx', section: 'đoạn 2' }] } } },
        }, 800)
        await send('step', {
          step: { ...s2, status: 'done', duration_ms: 600, summary: 'ngữ nghĩa · “thời hạn báo cáo kết quả tập huấn” · 0,6 giây',
            detail: { ...s2.detail, result: { count: 3, documents: [{ doc_id: 102, label: '31/HD-PTM', section: 'mục 3' }] } } },
        }, 500)
        const read = step('r1', { title: 'Đọc văn bản', summary: '24/KH-PTM · trang 1/2', tool: 'read_document', detail: { arguments: { doc_id: 101 } } })
        await send('step', { step: read }, 100)
        await send('step', { step: { ...read, status: 'done', duration_ms: 200, summary: '24/KH-PTM · trang 1/2 · 0,2 giây', detail: { ...read.detail, result: { count: 1, documents: [{ doc_id: 101, label: '24/KH-PTM', section: 'trang 1' }] } } } }, 600)

        if (body.context?.block_id) {
          const target = entry.draft?.blocks.find((b) => b.id === body.context?.block_id)
          const edit = step('e1', { title: 'Sửa đoạn', summary: 'đề xuất thay đoạn đã chọn', tool: 'canvas_edit_block' })
          await send('step', { step: edit }, 100)
          if (entry.draft && target) {
            target.proposal = {
              action: 'replace',
              text: body.context.selection
                ? `${body.context.selection.replace(/sớm cấp vật tư\.?$/, '')}cấp đủ, đúng chủng loại và bàn giao trước ngày 15/4/2026 để đơn vị kịp triển khai.`
                : 'Đề nghị Phòng Hậu cần cấp đủ, đúng chủng loại và bàn giao trước ngày 15/4/2026 để đơn vị kịp triển khai.',
              note: body.text.slice(0, 80),
            }
            await send('canvas', { draft: bump(entry, 'assistant', 'Đề xuất sửa một đoạn') }, 400)
          }
          await send('step', { step: { ...edit, status: 'done', duration_ms: 300, summary: 'đề xuất thay đoạn đã chọn · 0,3 giây' } }, 100)
        } else {
          const open = step('c1', { title: 'Mở canvas', summary: 'mẫu M08 · Công văn', tool: 'canvas_create' })
          await send('step', { step: open }, 100)
          if (!entry.draft) entry.draft = makeDraft()
          const fieldsOnly = structuredClone(entry.draft)
          fieldsOnly.blocks = []
          await send('canvas', { draft: fieldsOnly }, 500)
          await send('step', { step: { ...open, status: 'done', duration_ms: 500, summary: 'mẫu M08 · Công văn · 0,5 giây' } }, 100)
          const write = step('c2', { title: 'Soạn nội dung', summary: 'trích yếu, 4 đoạn nội dung', tool: 'canvas_set_content' })
          await send('step', { step: write }, 100)
          await send('canvas', { draft: structuredClone(entry.draft) }, 900)
          await send('step', { step: { ...write, status: 'done', duration_ms: 900, summary: 'trích yếu, 4 đoạn nội dung · 0,9 giây' } }, 100)
        }

        const answer = body.context?.block_id ? 'Tôi đã đề xuất lại đoạn bạn chọn. Hãy xem phần so sánh trong canvas và chấp nhận hoặc từ chối.' : ANSWER
        const citations = body.context?.block_id ? [] : CITATIONS
        entry.messages.push({ id: ++nextId, role: 'assistant', content: answer, steps: [], citations, status: 'done', attachment_ids: [], created_at: now() })
        await send('answer', { text: answer, citations }, 300)
        await send('done', { message_id: nextId, title: entry.session.title, status: 'done' }, 100)
        controller.close()
      } catch (error) {
        controller.error(error)
      }
    },
  })
}
