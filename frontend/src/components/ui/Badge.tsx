import type { ReactNode } from 'react'
import type { BadgeTone } from '../../types'

type BadgeProps = {
  tone?: BadgeTone
  children: ReactNode
  className?: string
}

export function Badge({ tone = 'neutral', children, className = '' }: BadgeProps) {
  return <span className={`badge badge-${tone} ${className}`.trim()}>{children}</span>
}
