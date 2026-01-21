import React from 'react';
import { motion, type HTMLMotionProps } from 'framer-motion';
import { cn } from '../../utils/cn';

interface CardProps extends HTMLMotionProps<'div'> {
  variant?: 'default' | 'interactive' | 'glass';
  padding?: 'none' | 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

const paddingClasses = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = 'default', padding = 'md', children, ...props }, ref) => {
    const baseClasses = cn(
      'rounded-2xl overflow-hidden transition-all duration-300',
      paddingClasses[padding],
      {
        'bg-white shadow-lg shadow-slate-200/50 border border-slate-100': variant === 'default',
        'bg-white shadow-lg shadow-slate-200/50 border border-slate-100 cursor-pointer hover:shadow-xl hover:shadow-slate-200/70 hover:-translate-y-1 hover:border-primary-200': variant === 'interactive',
        'bg-white/70 backdrop-blur-xl border border-white/20 shadow-xl': variant === 'glass',
      },
      className
    );

    if (variant === 'interactive') {
      return (
        <motion.div
          ref={ref}
          className={baseClasses}
          whileHover={{ y: -4 }}
          whileTap={{ scale: 0.98 }}
          {...props}
        >
          {children}
        </motion.div>
      );
    }

    return (
      <motion.div
        ref={ref}
        className={baseClasses}
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        {...props}
      >
        {children}
      </motion.div>
    );
  }
);

Card.displayName = 'Card';

export const CardHeader: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <div className={cn('border-b border-slate-100 pb-4 mb-4', className)}>
    {children}
  </div>
);

export const CardTitle: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <h3 className={cn('text-xl font-bold text-slate-900', className)}>
    {children}
  </h3>
);

export const CardDescription: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <p className={cn('text-sm text-slate-500 mt-1', className)}>
    {children}
  </p>
);

export const CardContent: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <div className={className}>
    {children}
  </div>
);

export const CardFooter: React.FC<{ children: React.ReactNode; className?: string }> = ({
  children,
  className,
}) => (
  <div className={cn('border-t border-slate-100 pt-4 mt-4', className)}>
    {children}
  </div>
);

export default Card;
