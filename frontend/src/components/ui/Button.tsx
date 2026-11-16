import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'accent' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md'
  children: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  className = '',
  children,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button type={type} className={`btn btn-${variant} btn-${size} ${className}`.trim()} {...rest}>
      {children}
    </button>
  )
}
