import type * as Pdfjs from 'pdfjs-dist'

export type { PDFDocumentProxy, PDFPageProxy, RenderTask } from 'pdfjs-dist'

/** Where the data pdf.js loads on demand lives (copied from the package into `public/pdfjs`, so nothing is fetched from the internet). */
const DATA = `${import.meta.env.BASE_URL}pdfjs/`

export const PDFJS_OPTIONS = {
  cMapUrl: `${DATA}cmaps/`,
  cMapPacked: true,
  standardFontDataUrl: `${DATA}standard_fonts/`,
  wasmUrl: `${DATA}wasm/`,
  iccUrl: `${DATA}iccs/`,
} as const

let loading: Promise<typeof Pdfjs> | null = null

/** Loads pdf.js (a large library, so only when a page view is first opened) and points it at the locally bundled worker. */
export function loadPdfjs(): Promise<typeof Pdfjs> {
  loading ??= Promise.all([
    import('pdfjs-dist'),
    import('pdfjs-dist/build/pdf.worker.min.mjs?url'),
  ]).then(([lib, worker]) => {
    lib.GlobalWorkerOptions.workerSrc = worker.default
    return lib
  })
  loading.catch(() => { loading = null })
  return loading
}
