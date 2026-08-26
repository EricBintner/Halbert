// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium font-heading ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-background hover:bg-primary/90 active:bg-primary/80",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/80 active:scale-[0.97]",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground active:bg-accent/80",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80 active:bg-secondary/70",
        ghost: "hover:bg-accent hover:text-accent-foreground active:bg-accent/80",
        link: "text-primary underline-offset-4 hover:underline",
        pill: "rounded-full border gap-1.5 font-semibold",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
        "icon-sm": "h-7 w-7 p-1",
      },
      tone: {
        default: "",
        success: "",
        warning: "",
      },
    },
    compoundVariants: [
      { variant: "pill", size: "default", className: "h-7 px-3 text-xs" },
      { variant: "pill", tone: "default", className: "border-border bg-surface text-text-muted hover:bg-surface-raised" },
      { variant: "pill", tone: "success", className: "border-success/40 bg-success/10 text-success hover:bg-success/20" },
      { variant: "pill", tone: "warning", className: "border-amber-500/40 bg-amber-500/10 text-amber-400 hover:bg-amber-500/20" },
    ],
    defaultVariants: {
      variant: "default",
      size: "default",
      tone: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
  icon?: React.ElementType;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, tone, asChild = false, loading = false, icon: Icon, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, tone, className }))}
        ref={ref}
        disabled={props.disabled || loading}
        {...props}
      >
        {asChild
          ? children
          : <>
              {loading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {!loading && Icon && <Icon className={cn("h-4 w-4", children ? "mr-2" : "")} />}
              {children}
            </>
        }
      </Comp>
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
