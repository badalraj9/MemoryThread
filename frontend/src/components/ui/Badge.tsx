// Badge Component - Sci-punk

import { forwardRef, type HTMLAttributes } from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-sm px-2.5 py-1 text-[10px] font-medium tracking-wider transition-all',
  {
    variants: {
      variant: {
        default: 'bg-[var(--color-bg-surface-raised)] border border-[var(--color-border-default)] text-[var(--color-text-tertiary)] uppercase',
        truth: 'bg-[var(--color-truth-high)]/10 border border-[var(--color-truth-high)]/30 text-[var(--color-truth-high)]',
        confidence: 'bg-[var(--color-neon-cyan)]/10 border border-[var(--color-neon-cyan)]/30 text-[var(--color-neon-cyan)]',
        authority: 'bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/30 text-[var(--color-warning)]',
        type: 'bg-[var(--color-neon-violet)]/10 border border-[var(--color-neon-violet)]/30 text-[var(--color-neon-violet)]',
        source: 'bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)] text-[var(--color-text-tertiary)] uppercase',
        success: 'bg-[var(--color-success)]/10 border border-[var(--color-success)]/30 text-[var(--color-success)]',
        warning: 'bg-[var(--color-warning)]/10 border border-[var(--color-warning)]/30 text-[var(--color-warning)]',
        error: 'bg-[var(--color-error)]/10 border border-[var(--color-error)]/30 text-[var(--color-error)]',
        info: 'bg-[var(--color-info)]/10 border border-[var(--color-info)]/30 text-[var(--color-info)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => {
    return (
      <span
        ref={ref}
        className={cn(badgeVariants({ variant, className }))}
        {...props}
      />
    );
  }
);

Badge.displayName = 'Badge';