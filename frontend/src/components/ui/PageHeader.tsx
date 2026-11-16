import type { ReactNode } from 'react'

type PageHeaderProps = {
  title: string
  description: string
  badge?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, description, badge, actions }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="page-header-text">
        <div className="page-title-row">
          <h1>{title}</h1>
          {badge}
        </div>
        <p>{description}</p>
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </header>
  )
}
