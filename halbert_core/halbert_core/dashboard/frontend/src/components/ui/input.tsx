// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2023 shadcn (https://ui.shadcn.com)
// SPDX-FileCopyrightText: 2024-2026 Eric Bintner and Halbert Contributors (modifications)
// Derived from shadcn/ui, distributed under the MIT License; see THIRD-PARTY-LICENSES.md §3.5.
import * as React from "react"
import { cn } from "@/lib/utils"

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
