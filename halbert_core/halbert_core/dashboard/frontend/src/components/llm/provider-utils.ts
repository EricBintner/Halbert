// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import type { LLMProvider } from '@/types/llm';

export const LOCAL_PROVIDERS: readonly LLMProvider[] = ['ollama', 'lm-studio'] as const;

export function isLocalProvider(p: LLMProvider | undefined): boolean {
  return !!p && (LOCAL_PROVIDERS as readonly string[]).includes(p);
}
