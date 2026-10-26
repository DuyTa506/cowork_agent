# Frontend structure

React 19 + TypeScript (strict) + Vite, plain CSS, no external fonts or CDNs (the app runs offline on the LAN).

```
src/
  api/          typed client: client.ts (fetch wrapper, ApiError, 401 handling, upload with progress),
                types.ts (mirrors docs/openapi.json), one module per area (auth, documents, units, admin)
  auth/         AuthProvider/useAuth (token in sessionStorage), RequireAuth / RequireAdmin route guards
  components/   design-system UI kit (Button, IconButton, Tooltip, Field/Input/Select/Checkbox/Switch, Modal, ConfirmDialog,
                Drawer, Menu, Tabs, Chip/Badge, StatCard, DataTable, Pagination, Skeleton, EmptyState, Toast, Alert,
                Avatar, Icon (lucide), ...; API in design-system/qk3-documents/COMPONENTS.md), DocumentViewer,
                and feature folders: layout/ (shell: Sidebar, Topbar, CommandPalette, RouteProgress), documents/, admin/, ...
  hooks/        useAsyncData, useUnits, useDebouncedValue, useDocumentTitle, usePageMeta (title + breadcrumb),
                useJobs (background-job poll), useLayer (focus trap / Esc for layers), useTheme
  lib/          format.ts (dd/mm/yyyy, 1.562, sizes), labels.ts, documents.ts, settings.ts, theme.ts, storage.ts
  pages/        one file per route (+ StyleGuidePage at /_ui, dev only)
  styles/       tokens.css (colours, type, space, motion, light + dark, aliases for old names), base.css,
                ui*.css (controls, feedback, data, overlays), shell.css, auth.css, then one stylesheet per page area
```

## Adding a page

1. Create `src/pages/XxxPage.tsx`: call `usePageMeta({ title })`, render `<div className="page"><PageHeader title description>actions</PageHeader>…</div>`.
2. Register the route in `src/App.tsx` (inside the `RequireAuth` / `AppShell` route) and, if it needs a sidebar
   entry, add it to `NAV` in `components/layout/Sidebar.tsx`.
3. Fetch with `useAsyncData` and the `*Api` namespaces from `src/api`; report results with `useToast()`.

## Reusable pieces for the Assistant and Format-check pages

- `DocumentViewer` (`documentId`, optional `highlight={{from, to}}` in `pi` units) for citation previews.
- `DocumentDetailPanel` for a document's fields, steps and actions.
- `UploadDialog`-style flows: `api.documentsApi.uploadDocuments` reports progress; `uploadForm` in `api/client.ts`
  is the generic multipart helper (XHR, so progress works).
- `requestBlob` for authenticated binary downloads.

## Design system

Tokens, fonts (Be Vietnam Pro, Tinos, bundled with @fontsource) and icons (lucide-react) are bundled: no network at runtime.
Light/dark theme via `data-theme` on `<html>` (inline script in `index.html` prevents a flash; choice in localStorage `qk3.theme`).
`/_ui` (dev server only) is a living style guide of every token and component. Specs: `design-system/qk3-documents/MASTER.md`
(visual rules) and `COMPONENTS.md` (component API and usage rules). CSS class prefixes: `.pill*` chips, `.meter*` progress bars.
