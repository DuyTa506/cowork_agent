import type { ReactNode } from 'react'

interface PageHeaderProps {
  /** The page's `h1` (24/32). A ReactNode so a back link can be passed. */
  title: ReactNode
  /** One sentence under the title. */
  description?: ReactNode
  /** Right-aligned actions: at most one primary Button. */
  children?: ReactNode
}

/**
 * Header at the top of a page's content: h1, one-line description and the page actions on the right. Inside a `.page`
 * container it has no side padding; directly in the shell's `<main>` it pads itself 24 px.
 */
export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header__text">
        <h1 className="page-header__title">{title}</h1>
        {description && <p className="page-header__desc">{description}</p>}
      </div>
      {children && <div className="page-header__actions">{children}</div>}
    </header>
  )
}
