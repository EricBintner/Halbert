// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2023 shadcn (https://ui.shadcn.com)
// SPDX-FileCopyrightText: 2024-2026 Eric Bintner and Halbert Contributors (modifications)
// Derived from shadcn/ui, distributed under the MIT License; see THIRD-PARTY-LICENSES.md §3.5.
import * as React from "react"
import * as LabelPrimitive from "@radix-ui/react-label"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
)

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> &
    VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root
    ref={ref}
    className={cn(labelVariants(), className)}
    {...props}
  />
))
Label.displayName = LabelPrimitive.Root.displayName

export { Label }
