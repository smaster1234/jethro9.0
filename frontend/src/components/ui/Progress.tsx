import React from 'react';
import { motion } from 'framer-motion';
import { cn } from '../../utils/cn';

interface ProgressProps {
  value: number;
  max?: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  label?: string;
  variant?: 'primary' | 'success' | 'warning' | 'danger';
  className?: string;
  animated?: boolean;
}

const sizeClasses = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
};

const variantClasses = {
  primary: 'from-primary-500 to-accent-500',
  success: 'from-success-500 to-green-400',
  warning: 'from-warning-500 to-yellow-400',
  danger: 'from-danger-500 to-red-400',
};

export const Progress: React.FC<ProgressProps> = ({
  value,
  max = 100,
  size = 'md',
  showLabel = false,
  label,
  variant = 'primary',
  className,
  animated = true,
}) => {
  const percentage = Math.min(Math.max((value / max) * 100, 0), 100);

  return (
    <div className={cn('w-full', className)}>
      {(showLabel || label) && (
        <div className="flex justify-between items-center mb-2">
          <span className="text-sm font-medium text-slate-700">
            {label || 'התקדמות'}
          </span>
          <span className="text-sm font-semibold text-slate-900">
            {Math.round(percentage)}%
          </span>
        </div>
      )}
      <div
        className={cn(
          'w-full bg-slate-200 rounded-full overflow-hidden',
          sizeClasses[size]
        )}
      >
        <motion.div
          className={cn(
            'h-full bg-gradient-to-r rounded-full',
            variantClasses[variant]
          )}
          initial={animated ? { width: 0 } : false}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
        />
      </div>
    </div>
  );
};

export default Progress;
