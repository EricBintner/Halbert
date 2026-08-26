// SPDX-License-Identifier: MIT
// SPDX-FileCopyrightText: 2023 shadcn (https://ui.shadcn.com)
// SPDX-FileCopyrightText: 2024-2026 Eric Bintner and Halbert Contributors (modifications)
// Derived from shadcn/ui, distributed under the MIT License; see THIRD-PARTY-LICENSES.md §3.5.
import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
