import React from 'react';
import { cn } from '../../utils/cn';

type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'neutral' | 'accent';

interface BadgeProps {
  variant?: BadgeVariant;
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
  className?: string;
  icon?: React.ReactNode;
}

const variantClasses: Record<BadgeVariant, string> = {
  primary: 'bg-primary-100 text-primary-700 border-primary-200',
  success: 'bg-success-100 text-success-600 border-success-200',
  warning: 'bg-warning-100 text-warning-600 border-warning-200',
  danger: 'bg-danger-100 text-danger-600 border-danger-200',
  neutral: 'bg-slate-100 text-slate-600 border-slate-200',
  accent: 'bg-accent-100 text-accent-700 border-accent-200',
};

const sizeClasses = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-xs',
  lg: 'px-4 py-1.5 text-sm',
};

export const Badge: React.FC<BadgeProps> = ({
  variant = 'neutral',
  size = 'md',
  children,
  className,
  icon,
}) => {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full font-semibold border',
        variantClasses[variant],
        sizeClasses[size],
        className
      )}
    >
      {icon && <span className="flex-shrink-0">{icon}</span>}
      {children}
    </span>
  );
};

export default Badge;
