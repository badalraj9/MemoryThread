// Textarea Component

import { forwardRef, type TextareaHTMLAttributes } from 'react';
import { cn } from '../../lib/utils';

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className, ...props }, ref) => {
    return (
      <textarea
        ref={ref}
        className={cn(
          'flex min-h-[44px] w-full rounded-md border border-[var(--color-border-default)] bg-[var(--color-bg-base)] px-4 py-3 text-sm text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none focus:border-[var(--color-accent-primary)] focus:ring-1 focus:ring-[var(--color-accent-primary)] disabled:cursor-not-allowed disabled:opacity-50 transition-colors resize-none',
          className
        )}
        {...props}
      />
    );
  }
);

Textarea.displayName = 'Textarea';