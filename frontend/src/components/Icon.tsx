import type { LucideIcon } from 'lucide-react'
import {
  ArrowBigUp,
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BetweenHorizontalEnd,
  BetweenVerticalEnd,
  Building2,
  CalendarDays,
  CalendarRange,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  ChevronUp,
  Circle,
  CircleAlert,
  CircleCheck,
  CircleHelp,
  CircleX,
  ClipboardList,
  Clock,
  Command,
  Copy,
  CornerDownLeft,
  Download,
  Ellipsis,
  EllipsisVertical,
  ExternalLink,
  Eye,
  EyeOff,
  File,
  FileBarChart,
  FileCheck,
  FileSearch,
  FileText,
  FileUp,
  FileX,
  FolderOpen,
  Gavel,
  History,
  House,
  Inbox,
  Info,
  KeyRound,
  Landmark,
  Layers,
  Lightbulb,
  ListChecks,
  ListFilter,
  LoaderCircle,
  Lock,
  LockKeyhole,
  LogOut,
  Mail,
  Maximize2,
  Menu,
  MessageSquareText,
  Minus,
  Moon,
  OctagonAlert,
  PanelLeft,
  PanelLeftClose,
  PanelLeftOpen,
  Paperclip,
  Pencil,
  PenLine,
  Plus,
  Quote,
  RectangleHorizontal,
  Redo2,
  RefreshCw,
  Save,
  ScanLine,
  Search,
  Send,
  Server,
  ShieldAlert,
  ShieldCheck,
  Sigma,
  SlidersHorizontal,
  Sparkles,
  SpellCheck,
  Square,
  Sun,
  Tag,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  TriangleAlert,
  Undo2,
  Upload,
  User,
  Users,
  WifiOff,
  Wrench,
  X,
  Zap,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'

/**
 * The icon set: lucide (ISC, bundled and tree-shaken, no network). Screens use the semantic names below and never import
 * lucide directly, so the set can change in one place. Add a name here when a screen needs a new glyph.
 */
const ICONS = {
  // navigation and areas
  chat: MessageSquareText,
  folder: FolderOpen,
  tag: Tag,
  shield: ShieldCheck,
  shieldAlert: ShieldAlert,
  sliders: SlidersHorizontal,
  home: House,
  bank: Landmark,
  building: Building2,
  users: Users,
  user: User,
  server: Server,
  tools: Wrench,
  canvas: PenLine,
  // tables on the canvas
  rowAdd: BetweenHorizontalEnd,
  columnAdd: BetweenVerticalEnd,
  landscape: RectangleHorizontal,
  sigma: Sigma,
  history: History,
  inbox: Inbox,
  layers: Layers,
  zap: Zap,
  sparkles: Sparkles,
  lightbulb: Lightbulb,
  listChecks: ListChecks,
  thumbUp: ThumbsUp,
  thumbDown: ThumbsDown,
  // files
  file: FileText,
  fileDoc: FileText,
  filePdf: FileText,
  fileX: FileX,
  fileCheck: FileCheck,
  fileSearch: FileSearch,
  fileUp: FileUp,
  fileBlank: File,
  gavel: Gavel,
  calendarRange: CalendarRange,
  calendar: CalendarDays,
  fileBarChart: FileBarChart,
  mail: Mail,
  clipboard: ClipboardList,
  // actions
  upload: Upload,
  download: Download,
  search: Search,
  close: X,
  check: Check,
  plus: Plus,
  minus: Minus,
  edit: Pencil,
  trash: Trash2,
  save: Save,
  copy: Copy,
  refresh: RefreshCw,
  undo: Undo2,
  redo: Redo2,
  send: ArrowUp,
  plane: Send,
  stop: Square,
  clip: Paperclip,
  quote: Quote,
  filter: ListFilter,
  logout: LogOut,
  key: KeyRound,
  lock: Lock,
  lockKey: LockKeyhole,
  eye: Eye,
  eyeOff: EyeOff,
  eyeSlash: EyeOff,
  zoomIn: ZoomIn,
  zoomOut: ZoomOut,
  expand: Maximize2,
  fit: Maximize2,
  spellcheck: SpellCheck,
  scan: ScanLine,
  externalLink: ExternalLink,
  command: Command,
  enter: CornerDownLeft,
  // status
  checkCircle: CircleCheck,
  alert: TriangleAlert,
  alertCircle: CircleAlert,
  warnOctagon: OctagonAlert,
  xCircle: CircleX,
  info: Info,
  help: CircleHelp,
  clock: Clock,
  circle: Clock,
  dot: Circle,
  spinner: LoaderCircle,
  offline: WifiOff,
  capsLock: ArrowBigUp,
  // chevrons and arrows
  chevronDown: ChevronDown,
  chevronUp: ChevronUp,
  chevronLeft: ChevronLeft,
  chevronRight: ChevronRight,
  chevronsUpDown: ChevronsUpDown,
  arrowLeft: ArrowLeft,
  arrowRight: ArrowRight,
  arrowUp: ArrowUp,
  arrowDown: ArrowDown,
  arrowUpRight: ArrowUpRight,
  // chrome
  menu: Menu,
  more: Ellipsis,
  moreVertical: EllipsisVertical,
  panelLeft: PanelLeft,
  panelLeftClose: PanelLeftClose,
  panelLeftOpen: PanelLeftOpen,
  sun: Sun,
  moon: Moon,
} as const satisfies Record<string, LucideIcon>

export type IconName = keyof typeof ICONS

interface IconProps {
  name: IconName
  /** Pixels; 18 in controls, 20 in navigation. */
  size?: number
  className?: string
  /** Line weight; the design system uses 1.75. */
  strokeWidth?: number
  /** Ignored: kept so call sites written for the previous icon set still compile. */
  weight?: string
}

/** Decorative icon (hidden from assistive technology; put the meaning in an adjacent label or `aria-label` on the control). */
export function Icon({ name, size = 18, className, strokeWidth = 1.75 }: IconProps) {
  const Glyph = ICONS[name]
  return <Glyph size={size} strokeWidth={strokeWidth} aria-hidden="true" focusable="false" className={className} />
}

const DOC_TYPE_ICONS: Record<string, IconName> = {
  'quyết định': 'gavel',
  'kế hoạch': 'calendarRange',
  'báo cáo': 'fileBarChart',
  'công văn': 'mail',
}

/** Glyph for a document type (Quyết định, Kế hoạch, Báo cáo, Công văn; anything else is a plain page). */
export function docTypeIcon(type: string | null | undefined, secret = false): IconName {
  if (secret) return 'shieldAlert'
  return DOC_TYPE_ICONS[(type ?? '').trim().toLowerCase()] ?? 'file'
}

interface DocTypeIconProps {
  type: string | null | undefined
  /** Secret ("Mật") documents get the red shield glyph. */
  secret?: boolean
  size?: 'sm' | 'md'
}

/** Rounded tile with the document-type glyph; use it as the leading visual of document rows, results and sources. */
export function DocTypeIcon({ type, secret = false, size = 'md' }: DocTypeIconProps) {
  return (
    <span className={['doc-icon', size === 'sm' && 'doc-icon--sm', secret && 'doc-icon--secret'].filter(Boolean).join(' ')}>
      <Icon name={docTypeIcon(type, secret)} size={size === 'sm' ? 16 : 18} />
    </span>
  )
}
