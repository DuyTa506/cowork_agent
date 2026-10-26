# QK3 Documents — Shared components (phase 1 foundation)

How to build pages on the new design system. Source of truth for look and feel is `MASTER.md`; this file is the API and the rules.
Live gallery of everything in every state, light and dark: run `npm run dev` and open **`/_ui`** (dev only).

All paths are under `frontend/src/`. CSS lives in `styles/`: `tokens.css` (colours, type, space, motion, **aliases for the old token names**),
`base.css` (reset, `.page`, helpers), `ui.css` (controls), `ui-feedback.css`, `ui-data.css`, `ui-overlay.css`, `shell.css`, `auth.css`.
Never write raw colours or hex in page CSS: use tokens (`var(--surface)`, `var(--text-2)`, `var(--primary)` …). Old names (`--line`, `--muted`,
`--red`, `--navy`, …) still resolve through aliases but do not use them in new code.

## Page skeleton

```tsx
usePageMeta({ title: 'Kho văn bản' })                       // tab title + top-bar breadcrumb
return (
  <div className="page">                                     {/* 24 px padding (16 on phones), max 1280 */}
    <PageHeader title="Kho văn bản" description="Tra cứu văn bản đã lập chỉ mục.">
      <Button variant="primary" icon="upload">Tải văn bản lên</Button>   {/* at most ONE primary button */}
    </PageHeader>
    …content…
  </div>
)
```

* `.page` (centered, padded), `.page--wide` (no max width), `.page--narrow` (880), `.page--flush` (no padding, for full-bleed split layouts such as the assistant; give the `PageHeader` its own padding then — it does by default outside `.page`).
* The shell's `<main>` is a flex column that scrolls; full-height layouts can use `flex: 1 1 0; min-height: 0` as `.asst` does.
* Spacing between blocks: 24 px between sections, 16 px between cards, 12 px between controls (`.vstack`, `.hstack` helpers).

### Top bar title / breadcrumb — `hooks/usePageMeta.tsx`
`usePageMeta({ title, crumbs? })`. The top bar always starts with "Quân khu 3"; without `crumbs` it shows the section from `components/layout/nav.ts`
(`/kho/12` → *Kho văn bản › Chi tiết*). For a detail page pass the real trail:
`usePageMeta({ title: doc.title, crumbs: [{ label: 'Kho văn bản', to: '/kho' }, { label: documentSymbol(doc) }] })`.
Old `useDocumentTitle(title)` still works (tab title only).

### Shell services
* `useCommandPalette().open()` — Ctrl+K / `/` open it everywhere. It navigates with `navigate('/kho', { state: { action: 'upload' } })` for "Tải văn bản lên": the Kho page must open its upload dialog when `location.state?.action === 'upload'`.
* `useJobs()` → `{ active, reachable, refresh }`: documents waiting/processing (polled every 8 s while the tab is visible). Call `refresh()` after an upload so the top bar reacts at once.
* `useTheme()` → `{ theme, setTheme, toggle }`. Stored in `localStorage` key `qk3.theme`; `index.html` applies it before first paint.
* `useToast()` → `notify(message, kind?, { action?, duration? })`; kinds `success` (default) · `error` · `info` · `warning`. Errors stay 8 s, others 4 s, pause on hover.
* Storage that may be blocked: use `lib/storage.ts` (`readStorage` / `writeStorage`), never raw `localStorage`.

## Rules

| Situation | Use |
|---|---|
| Show the **detail of a record** (document, account, finding) or anything with tabs/long forms | **Drawer** (right, 520/640/800). Row click opens it, `Esc` closes. |
| A **short decision or a form of ≤ 5 fields** (rename, change password, choose a folder) | **Modal** (480 default). |
| **Irreversible or bulk action** | **ConfirmDialog** with `danger`; the title names the object ("Xóa văn bản 33/QĐ-QK3?"). The destructive button is only filled red here. |
| Row/overflow actions, user menu | **Menu** (never a hand-made popover). |
| Feedback to an action that already finished | **Toast**. Something the user must fix or read next to a control | **Alert** (inline). |

**Loading:** first load → skeleton that mimics the final layout (`DataTable loading`, `Skeleton`, `StatCard loading`); background reload → keep old data, no spinner; ≥ 1 s work → `Progress` or a Button `loading`. A lone `Spinner` only for tiny spots.
**Empty:** `EmptyState` with an illustration (`documents` first-time empty, `search` filtered to nothing, `chat`, `check`, `error`), a one-sentence reason and the primary next action. `compact` inside panels and drawers.
**Error:** `Alert kind="error"` with the message and a "Thử lại" button where the data would have been (or `EmptyState illustration="error"` when the whole page failed). Field errors via `Field error`.
**Status is never colour alone:** `Chip`/`StateChip` always carry text and a dot or icon.
Dark mode is automatic; if you need a colour that is not a token, add a token to `tokens.css` for both themes.

## Components

Every file is `components/<Name>.tsx`; import as `import { Button } from '../components/Button'`.

### Button — `Button.tsx`
`variant`: `primary` · `secondary` (= `default`) · `ghost` · `danger` · `danger-solid` (confirm dialogs only). `size`: `sm` 28 · `md` 36 · `lg` 44. `icon` (leading, an `IconName`), `iconEnd`, `loading` (spinner + label kept, disables), `block`. `type` defaults to `button`.
```tsx
<Button variant="primary" icon="upload" onClick={…}>Tải văn bản lên</Button>
<Button variant="danger" icon="trash" loading={busy}>Xóa</Button>
```

### IconButton — `IconButton.tsx`
`icon`, **`label` (required; also the tooltip)**, `size` `sm|md|lg` (a number = icon px, legacy), `outline`, `danger`, `tooltip` (`top|bottom|left|right|false`). Pass `aria-pressed` / `aria-expanded` for toggles.
`<IconButton icon="edit" label="Đổi tên" onClick={…} />`

### Tooltip — `Tooltip.tsx`
`<Tooltip content="…" side="top"><button>…</button></Tooltip>`. Child must be focusable. Not for essential information.

### Icon, DocTypeIcon — `Icon.tsx`
`<Icon name="search" size={18} />` (decorative, `aria-hidden`; lucide, stroke 1.75; 18 px controls, 20 px nav). Names are in the `ICONS` map (see the gallery); add a name there when you need a glyph — never import lucide in a page. `docTypeIcon(type, secret)` / `<DocTypeIcon type="Quyết định" secret />` give the type glyph tile (Gavel, CalendarRange, FileBarChart, Mail, FileText; secret = ShieldAlert).

### Field, Input, Textarea, Select, DateInput, Checkbox, Switch
```tsx
<Field label="Số hiệu" hint="Ví dụ 33/QĐ-QK3" error={err} required>
  {({ id, describedBy, invalid }) => <Input id={id} aria-describedby={describedBy} invalid={invalid} icon="search" />}
</Field>
<Input type="password" revealable size="lg" icon="lock" />        // show/hide button built in
<Textarea …/>   <Select value options onChange />   <DateInput value="2026-10-13" onChange />   // dd/mm/yyyy text
<Checkbox checked onChange label description indeterminate />     // without label pass aria-label
<Switch checked onChange label description />                      // applies immediately; use Checkbox for "apply on Save"
```
Labels sit above, always present (`hideLabel` keeps it for screen readers). Controls are 36 px (`size` `sm` 28, `lg` 44). Plain `className="input|select|textarea"` still styles native elements.

### Chip, Badge, StateChip, LevelChip, StatusDot — `Chip.tsx`, `StatusDot.tsx`
`<Chip tone="ok|info|warn|danger|neutral|brand" icon? dot? solid? busy? size="md|lg">Text</Chip>` (22 px pill; old tones `green|blue|amber|red|grey` still accepted). `<Badge tone icon>12</Badge>` small count/role label. `<StateChip state={doc.state} />` (dot, pulsing while processing), `<LevelChip level="mat" />` (solid red + shield). `StatusDot` = quiet dot + text for dense tables.

### Avatar — `Avatar.tsx`
`<Avatar name="Nguyễn Văn An" size="sm|md|lg" onDark? />`.

### Alert — `Alert.tsx`
`<Alert kind="error|warning|info|success" title? action={<Button size="sm">Thử lại</Button>} onClose?>text</Alert>`.

### Toast — `Toast.tsx`
`const notify = useToast(); notify('Đã lưu vào kho.')`; `notify('Không lưu được.', 'error', { action: { label: 'Thử lại', onClick } })`.

### Spinner, Progress, Skeleton — `Spinner.tsx`, `Progress.tsx`, `Skeleton.tsx`
`<Spinner label="Đang tải" size={24} />` · `<Progress value={42} label="Đang tải lên" valueText="42%" tone? />` (omit `value` = indeterminate; class family `.meter`) · `<Skeleton width height circle />`, `<SkeletonText lines={3} />`. Size skeletons like the real content.

### EmptyState — `EmptyState.tsx`
`<EmptyState illustration="search" title="Không có văn bản phù hợp" description="Thử bỏ bớt điều kiện lọc." action={<Button>Xóa bộ lọc</Button>} compact? />`.

### Tabs — `Tabs.tsx`
`<Tabs items={[{key,label,count?,icon?}]} value onChange label="…" idPrefix="doc" />` + panel `<div {...tabPanelProps('doc', value)}>`. Left/Right/Home/End work. Inside a Drawer pass it as the `tabs` prop.

### StatCard — `StatCard.tsx`
`<div className="stat-grid"><StatCard label="Sẵn sàng" value="1.540" icon="checkCircle" tone="ok" hint? selected onClick /></div>` — with `onClick` it is a filter toggle (`aria-pressed`); `loading` shows a skeleton number.

### DataTable, Pagination — `DataTable.tsx`, `Pagination.tsx`
```tsx
<DataTable
  caption="Danh sách văn bản" columns={cols} rows={rows} getKey={(d) => d.id}
  selectedKey={openId} onSelect={(d) => setOpenId(d.id)}               // row click / Enter opens a Drawer
  selection={{ selected, onChange: setSelected }} rowLabel={(d) => d.number}   // optional checkbox column
  loading={loading && !rows.length} skeletonRows={8}
  empty={<EmptyState illustration="search" … />}
  footer={<Pagination className="table-foot" offset limit total noun="văn bản" onOffsetChange />}
/>
```
`Column`: `{ key, header, render, nowrap?, numeric?, align?, width?, hideBelow?: 'md'|'lg'|'xl', primary?, srHeader? }`. Cells: `<span className="cell-main">strong</span><span className="cell-sub">muted</span>` for the 2-line 56 px row. Header sticks to the top of the scrolling page. Below 768 px rows become stacked cards using each `header` as label (`primary` column prints without label). Hide low-value columns with `hideBelow` instead of horizontal scrolling.

### Modal, ConfirmDialog, Drawer
```tsx
{open && <Modal title="Đổi tên" description? size="md" onClose footer={<><Button>Hủy</Button><Button variant="primary">Lưu</Button></>}>…</Modal>}
{del && <ConfirmDialog danger title="Xóa văn bản 33/QĐ-QK3?" confirmLabel="Xóa văn bản" onConfirm={async () => …} onCancel>Không thể hoàn tác.</ConfirmDialog>}
{id && <Drawer title subtitle chips={<StateChip …/>} tabs={<Tabs …/>} width="md|lg|xl" onClose footer={primary actions} footerStart={destructive action}>…</Drawer>}
```
Mount = open. Focus is trapped, `Esc`/backdrop close (not while `busy`), focus returns to the opener. `data-autofocus` marks the initial control (ConfirmDialog focuses "Hủy"). Modals become bottom sheets on phones. Hook `hooks/useLayer.ts` gives any custom layer the same behaviour.

### Menu — `Menu.tsx`
```tsx
<Menu label="Thao tác" placement="bottom-end" items={[
  { key: 'dl', label: 'Tải tệp gốc', icon: 'download', onSelect },
  { type: 'separator', key: 's' },
  { key: 'rm', label: 'Xóa', icon: 'trash', danger: true, onSelect },
]} trigger={(props, { open }) => <IconButton {...props} icon="more" label="Thao tác" />} />
```
Entries: item · `separator` · `label` · `header`. Keyboard: Enter/Space/↓ open, ↑↓ Home End letters move, Esc closes (only the menu), Tab closes. Focus returns to the opener before `onSelect` runs, so an item may open a Modal.

### FileTypeBadge, PageHeader, UnitSelect
Unchanged APIs. `PageHeader` now renders the page `h1` + optional `description` + actions inside the content (not in the top bar).

## Tokens cheat sheet
Surfaces `--bg --surface --surface-2 --surface-hover --border --border-strong`; text `--text --text-2 --text-3 --placeholder`; brand `--primary --primary-hover --primary-soft --primary-ink` (text on soft backgrounds) `--on-primary --accent`; status pairs `--ok|warn|danger|info|neutral` + `-soft` + `-line`, `--on-solid` (text on a solid status fill); document `--desk --paper --paper-ink --highlight`; shape `--r-ctl 8 --r-card 12 --r-pill`; shadow `--shadow-1|2|3 --shadow-paper`; motion `--dur-fast 150 --dur-menu 200 --dur-panel 260 --ease --ease-in`; z-index `--z-*`. Space `--sp-1…--sp-14` (4·8·12·16·20·24·32·40·56). Fonts `--font` (Be Vietnam Pro), `--font-doc` (Times New Roman → Tinos), `--font-mono`.

## Deviations from MASTER.md (deliberate)
* `--text-3` light `#5B6B82` (spec `#64748B` is 4.3:1 on `--bg`), `--placeholder` `#64738A`, `--ok` `#147A39` and `--warn` `#A8480A` (spec values were 4.4:1 / lower on their soft backgrounds). Added `--primary-ink` (dark theme text on `--primary-soft`, spec pair was 4.0:1) and `--on-solid`, `--on-primary` (dark theme primary buttons use dark text).
* New `--control-border` (`#7D8DA4` / dark `#5A6C96`, ≥ 3:1) for input, select, textarea, checkbox and switch outlines; `--border-strong` stays for dividers and button outlines.
* Chip family is `.pill*` and progress bar `.meter*` in CSS (old assistant/documents stylesheets already own `.chip*` and `.progress__*`).
