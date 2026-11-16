import type { ReactNode } from 'react'

type CardProps = {
  children: ReactNode
  className?: string
}

export function Card({ children, className = '' }: CardProps) {
  return <div className={`card ${className}`.trim()}>{children}</div>
}

type SectionCardProps = {
  title: string
  description?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export function SectionCard({
  title,
  description,
  action,
  children,
  className = '',
}: SectionCardProps) {
  return (
    <section className={`card section-card ${className}`.trim()}>
      <header className="section-head">
        <div>
          <h2>{title}</h2>
          {description && <p>{description}</p>}
        </div>
        {action && <div className="section-action">{action}</div>}
      </header>
      {children}
    </section>
  )
}
