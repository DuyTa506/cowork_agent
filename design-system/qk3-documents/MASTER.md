# QK3 Documents — Design System (MASTER)

Source of truth for the web UI. Derived with the *ui-ux-pro-max* skill (style **Accessible & Ethical**, government / enterprise,
dials: density 7 · motion 3 · variance 4) and adapted to a dense desktop work tool used for hours by clerks and officers.
Page-specific overrides live in `pages/<page>.md`; they win over this file.

## Why the first UI failed (do not repeat)
Flat "admin template" look: everything the same grey-on-white weight, nothing to look at first, huge dead white areas, every
control the same size, no sense of progress or of what the system is doing. A document tool must feel *calm, precise and in control*.

## Principles
1. **One obvious thing per screen** — a clear primary action, a clear next step, secondary controls visually quiet.
2. **Show state, never leave the user guessing** — skeletons while loading, progress for anything > 1 s, empty states that say what to do, errors next to the thing that failed with a way out.
3. **Dense but breathable** — 14 px table text, 15 px reading text, 36 px controls (44 px hit area on touch), 4 px spacing scale; whitespace groups, borders rarely.
4. **Documents are the heroes** — paper (Times-like serif on white with soft shadow) on a neutral "desk"; app chrome stays quiet around it.
5. **Keyboard first** — every action reachable, visible focus ring, `Ctrl+K` command palette, `Esc` closes layers, `Enter` submits.
6. **Accessible by default** — contrast ≥ 4.5:1 (text) / 3:1 (UI), never colour alone (always icon or text with a status colour), `prefers-reduced-motion` honoured, labels on every input, icon-only buttons have `aria-label` + tooltip.
7. **Offline** — no CDN, no web fonts from the network; fonts and icons are bundled by the build.

## Foundations

### Colour (semantic tokens; light first, dark via `[data-theme="dark"]`, never raw hex in components)
| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#F3F5F9` | `#0B1220` | app desk |
| `--surface` | `#FFFFFF` | `#111A2C` | cards, panels, tables |
| `--surface-2` | `#F8FAFC` | `#16213A` | table header, quiet blocks, inputs on surface |
| `--surface-hover` | `#EEF2F8` | `#1B2845` | row / item hover |
| `--border` | `#E2E8F0` | `#25324F` | hairlines |
| `--border-strong` | `#CBD5E1` | `#34446A` | inputs, focus-less outlines |
| `--text` | `#0F172A` | `#E6ECF8` | primary text |
| `--text-2` | `#475569` | `#A9B6D0` | secondary text |
| `--text-3` | `#64748B` | `#8190B0` | hints, meta (≥ 4.5:1 on `--surface`) |
| `--brand-950` | `#071632` | `#071632` | sidebar bottom / login panel |
| `--brand-900` | `#0A1F44` | `#0A1F44` | sidebar |
| `--brand-700` | `#12397A` | `#1B4B99` | sidebar active, headings accent |
| `--primary` | `#1D4ED8` | `#4F83F7` | primary buttons, links, focus ring |
| `--primary-hover` | `#1E40AF` | `#6B96F8` | |
| `--primary-soft` | `#E8EEFE` | `#16275A` | selected row, chips, user bubble |
| `--accent` | `#C9971C` | `#E0B13C` | emblem gold: active-nav marker, small highlights only (≤ 5 % of a screen) |
| `--ok` / `--ok-soft` | `#15803D` / `#E6F4EA` | `#4ADE80` / `#12301F` | ready, success |
| `--warn` / `--warn-soft` | `#B45309` / `#FEF3C7` | `#FBBF24` / `#3A2A08` | needs review, warning |
| `--danger` / `--danger-soft` | `#B91C1C` / `#FDE8E8` | `#F87171` / `#3A1414` | failed, secret ("Mật"), destructive |
| `--info` / `--info-soft` | `#0369A1` / `#E0F2FE` | `#38BDF8` / `#0C2A3D` | processing, hints |
Document "paper": `#FFFFFF` on `--desk` `#E6E9EF` (dark: paper stays white — it is a document, with a darker desk `#0E1626`).
Findings: error `--danger`, warning `--warn`, spelling `--info` (blue wavy underline).
Ownership (canvas): system = dotted underline `--text-3`, assistant = `--primary-soft` background, user = dashed `--accent` underline.

### Typography (bundled with `@fontsource`, subsets latin + latin-ext + **vietnamese**)
- UI & headings: **Be Vietnam Pro** 400/500/600/700. Fallback: `system-ui, "Segoe UI", Roboto, "Noto Sans", sans-serif`.
- Document paper: **Tinos** (metric-compatible with Times New Roman) → `"Times New Roman", Tinos, "Liberation Serif", serif`.
- Scale (px / line-height): 12/16 meta · 13/18 small · 14/20 table & controls · **15/24 body & chat** · 17/26 lead · 20/28 h3 · 24/32 h2 · 30/38 h1 (login/empty hero only).
- Weights: 400 body, 500 labels/nav, 600 headings & buttons, 700 only for numbers in stat cards. Letter-spacing 0; never all-caps long text.
- Numbers in tables use `font-variant-numeric: tabular-nums`.

### Space, shape, elevation
- Space scale 4·8·12·16·20·24·32·40·56. Page padding 24 (desktop) / 16 (≤ 768). Card padding 16–20.
- Radius: controls 8, cards/panels 12, chips/pills 999, paper 2.
- Elevation: `--shadow-1: 0 1px 2px rgb(15 23 42/.06), 0 1px 1px rgb(15 23 42/.04)` (cards) · `--shadow-2: 0 8px 24px rgb(15 23 42/.10)` (menus, drawers) · `--shadow-3: 0 20px 48px rgb(15 23 42/.18)` (modals, command palette) · paper `0 1px 3px rgb(15 23 42/.12), 0 12px 32px rgb(15 23 42/.10)`.
- Borders: 1 px `--border`; separate with space first, lines second.

### Motion
150 ms (hover/press) · 200 ms (menus, popovers) · 260 ms (drawers, route enter). Easing `cubic-bezier(.2,.7,.2,1)` in, `cubic-bezier(.4,0,1,1)` out; exits faster than enters. Animate `opacity`/`transform` only. Loading uses skeleton shimmer (1.4 s) and a thin top progress bar for route changes. Everything wrapped in `@media (prefers-reduced-motion: no-preference)`.

### Iconography
`lucide-react` (bundled, tree-shaken), 18 px in controls, 20 px in nav, stroke 1.75, `aria-hidden` when decorative. No emoji as icons. Doc-type glyphs: Quyết định ⚖︎→`Gavel`, Kế hoạch `CalendarRange`, Báo cáo `FileBarChart`, Công văn `Mail`, default `FileText`; secret = `ShieldAlert`.

## Layout
- **App shell**: sidebar 248 px (collapses to 72 px rail ≤ 1100 px or by toggle, state remembered) + top bar 56 px + content. Sidebar is dark navy gradient (`--brand-900`→`--brand-950`), emblem + "QUÂN KHU 3 / Hệ thống AI xử lý văn bản" at top, nav items 40 px tall with 3 px `--accent` marker on active, nav order: **Trợ lý AI · Kho văn bản · Kiểm tra thể thức · Quản trị** (admin only), footer: system-status chip + user card.
- **Top bar**: breadcrumb/page title left; centre-right a search field that opens the **command palette** (`Ctrl+K`): search documents by number / title / unit, jump to pages, quick actions (Hỏi trợ lý, Tải văn bản lên, Kiểm tra thể thức, Đổi giao diện sáng/tối); right: background-job indicator (documents being processed), theme toggle, user menu.
- **Page header** (inside content): H1 (24/32, 600) + one-line description (`--text-2`) + primary action on the right. Never more than one primary button.
- **Responsive**: ≥ 1280 two/three-pane layouts; 768–1279 panes stack or become drawers; < 768 sidebar becomes a drawer opened from a hamburger, tables become stacked cards. No horizontal page scroll at any width ≥ 360.
- **Drawers over modals** for detail views; modals only for short decisions/forms (≤ 5 fields). Modal 480/640 px wide, focus trapped, `Esc` closes, primary action bottom-right, destructive actions confirm with the object's name.

## Components (recipes)
- **Button**: primary (filled `--primary`, white text, 36 px, 600), secondary (surface + `--border-strong`), ghost (text only, hover `--surface-hover`), danger (outlined red; filled only inside confirm dialogs). Loading state = spinner + label kept, disabled while loading. Icon-only: 36 px square, tooltip.
- **Input/Select/Textarea**: 36 px, `--surface`, 1 px `--border-strong`, radius 8, label above (13/500, `--text-2`), helper below, error text in `--danger` with icon + `aria-describedby`; focus = 2 px `--primary` ring + 2 px offset.
- **Chip/Badge**: 22 px, radius 999, soft background + same-hue text + leading dot or icon. States: Sẵn sàng (ok), Đang xử lý (info, animated dot), Cần rà soát (warn), Cần OCR (warn), Lỗi (danger), Mật (danger, `ShieldAlert`), Thường (neutral).
- **Stat card**: label 13 `--text-2`, number 28/700 tabular, delta/hint 12 `--text-3`; clickable (acts as filter), selected = `--primary-soft` + 2 px `--primary` bottom border.
- **Table**: header `--surface-2` 12/600 uppercase-free; rows 56 px (two-line cell: strong first line + `--text-3` second), hover `--surface-hover`, selected `--primary-soft`; sticky header; row click opens drawer; checkbox column for bulk actions; footer with count + pagination; skeleton rows while loading.
- **Tabs**: underline style, 40 px, count pills; keyboard arrows.
- **Drawer**: right, 520–640 px, header (title + chips + close), tabbed body, sticky action footer.
- **Toast**: bottom-right stack, 4 s (errors 8 s, with action), `role="status"`; **Alert**: inline, icon + title + text + action.
- **Empty state**: 96 px line illustration (inline SVG, brand colours), title, one sentence, primary action. **Skeleton**: matches final layout to avoid shift.
- **Command palette**: centred 640 px, input + grouped results, arrow keys + Enter, recent items, footer hints.
- **Avatar**: 32 px initials on `--primary-soft`, unit under name in user card.

## Surfaces (page overrides in `pages/`)
- **Đăng nhập**: split screen — left brand panel (`--brand-950` gradient, emblem 96 px, "Hệ thống AI xử lý văn bản", 3 short value lines, "Mạng nội bộ · phiên được kiểm soát"), right form card 400 px; show/hide password, caps-lock hint, inline error, loading button.
- **Kho văn bản**: stat cards row (Tất cả · Sẵn sàng · Đang xử lý · Cần rà soát/OCR · Lỗi) that filter; search + filter chips (loại, đơn vị, mức, ngày) with "Xóa bộ lọc"; table; detail drawer; drag-and-drop anywhere → upload sheet with per-file progress, duplicate shown as link; bulk delete/reprocess.
- **Trợ lý AI**: session panel (grouped Hôm nay / Hôm qua / 7 ngày / Cũ hơn, search, rename/delete in row menu) · centred conversation (max 760) · empty state with greeting and 4 suggestion cards · assistant messages are document-like (no bubble), user messages right-aligned `--primary-soft` · "Quá trình xử lý" timeline card (running = shimmer + spinner, done = check, parallel steps side by side) · citation chips `[1]` + "Nguồn" cards (doc-type icon, số hiệu, trích yếu, đơn vị, ngày) · composer floating card: attachments row, textarea auto-grow, `+` menu, Canvas pill, send/stop.
- **Canvas**: split view (conversation | canvas, resizable, canvas ≥ 520 px) · toolbar: template badge, "Phiên bản n", check pill ("Thể thức: 0 lỗi" ok / "3 lỗi" danger, click opens findings), Xuất DOCX, Lưu vào kho · paper on desk, zoom 80–140 % · owner legend · proposal diff with Accept/Reject inline, `Ctrl+Enter` accepts.
- **Kiểm tra thể thức**: 3-step header (1 Chọn tệp · 2 Kết quả · 3 Sửa & tải về); dropzone with profile + spelling options; result = summary cards (Lỗi/Cảnh báo/Chính tả/Tự sửa được) + findings list (grouped, filter chips, checkbox per fix) + paper preview with highlights, synced on click; sticky action bar "Sửa N mục · Tải bản đã sửa · Lưu vào kho".
- **Quản trị**: tabs Tài khoản · Hệ thống · Nhật ký; model settings as cards with a status dot, "Kiểm tra kết nối" inline result, secret fields "Đã đặt · Đổi/Xóa", external-host confirm as a clear warning dialog; users table + drawer.

## Content tone
Vietnamese, administrative-military register but plain: short verbs ("Tải lên", "Kiểm tra", "Lưu vào kho"), no exclamation marks, no emoji. Errors say what happened and what to do. Dates `dd/mm/yyyy`, times 24 h, numbers with `.` thousands.

## Pre-delivery checklist
- [ ] Contrast ≥ 4.5:1 text, ≥ 3:1 UI, in light **and** dark
- [ ] All controls reachable and visible-focus with keyboard; `Esc`/`Enter` behave
- [ ] Icon-only buttons labelled; icons not the only carrier of meaning
- [ ] Loading, empty, error, partial and long-content states designed
- [ ] 360 / 768 / 1024 / 1440 px: no horizontal page scroll, targets ≥ 44 px on touch
- [ ] `prefers-reduced-motion` respected; animations only on transform/opacity
- [ ] No network requests for fonts/scripts/images (offline build)
- [ ] Console clean
