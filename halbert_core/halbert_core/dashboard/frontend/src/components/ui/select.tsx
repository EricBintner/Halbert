// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import * as React from "react"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

export interface SelectProps
  extends React.SelectHTMLAttributes<HTMLSelectElement> {
  /** Size variant */
  variant?: "default" | "sm"
}

const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className, children, variant = "default", ...props }, ref) => {
    return (
      <div className="relative">
        <select
          className={cn(
            "flex w-full appearance-none rounded-md border border-input bg-background text-foreground ring-offset-background",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "pr-8", // Space for chevron
            variant === "sm" ? "h-8 px-2 text-xs" : "h-10 px-3 py-2 text-sm",
            className
          )}
          ref={ref}
          {...props}
        >
          {children}
        </select>
        <ChevronDown className={cn(
          "absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none text-muted-foreground",
          variant === "sm" ? "h-3 w-3" : "h-4 w-4"
        )} />
      </div>
    )
  }
)
Select.displayName = "Select"

export { Select }
