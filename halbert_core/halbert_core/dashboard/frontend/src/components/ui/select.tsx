// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

const selectVariants = cva(
  "appearance-none rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 pr-8",
  {
    variants: {
      variant: {
        default: "bg-surface-raised border border-border text-text hover:bg-surface",
        ghost: "bg-transparent border-none text-text hover:bg-surface-raised",
      },
      size: {
        default: "h-10 px-3 py-2",
        sm: "h-9 px-2 py-1 text-xs",
        lg: "h-11 px-4 py-2",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  group?: string;
}

export interface SelectProps
  extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'>,
    VariantProps<typeof selectVariants> {
  /** Data-driven options. When provided, renders <option> elements from this array. */
  options?: SelectOption[];
  /** Placeholder shown as a disabled first option. */
  placeholder?: string;
  /** Fallback: render raw <option> children when `options` is not provided. */
  children?: React.ReactNode;
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, variant, size, options, placeholder, children, ...props }, ref) => {
    return (
      <div className={cn("relative", className)}>
        <select
          className={cn(selectVariants({ variant, size }), "w-full")}
          ref={ref}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options
            ? options.map((opt) => (
                <option key={opt.value} value={opt.value} disabled={opt.disabled}>
                  {opt.label}
                </option>
              ))
            : children}
        </select>
        <ChevronDown className={cn(
          "pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground",
          size === "sm" ? "h-3 w-3" : "h-4 w-4"
        )} />
      </div>
    );
  }
);
Select.displayName = "Select";

export { Select, selectVariants };
