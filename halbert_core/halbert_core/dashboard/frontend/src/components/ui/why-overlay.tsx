// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * WhyOverlay Component
 * 
 * Full-screen overlay for editing "Why" explanations.
 * Provides a simple text input for explaining why something exists.
 */
import * as React from 'react'
import { Brain, X, Save, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { api } from '@/lib/api'

interface WhyOverlayProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  itemId: string
  itemName: string
  itemType: string
  initialWhy?: string
  onSave?: (why: string) => void
}

export function WhyOverlay({
  open,
  onOpenChange,
  itemId,
  itemName,
  itemType,
  initialWhy = '',
  onSave,
}: WhyOverlayProps) {
  const [why, setWhy] = React.useState(initialWhy)
  const [isSaving, setIsSaving] = React.useState(false)
  const [saved, setSaved] = React.useState(false)
  const textareaRef = React.useRef<HTMLTextAreaElement>(null)
  
  // Reset state when overlay opens
  React.useEffect(() => {
    if (open) {
      setWhy(initialWhy)
      setSaved(false)
      // Focus textarea after animation
      setTimeout(() => textareaRef.current?.focus(), 100)
    }
  }, [open, initialWhy])
  
  // Close on escape
  React.useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        onOpenChange(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [open, onOpenChange])
  
  const handleSave = async () => {
    if (!why.trim()) return
    
    setIsSaving(true)
    try {
      // Save to backend
      await api.saveWhy(itemId, itemName, itemType, why.trim())
      
      onSave?.(why.trim())
      setSaved(true)
      
      // Close after brief delay to show success
      setTimeout(() => {
        onOpenChange(false)
      }, 500)
    } catch (error) {
      console.error('Failed to save why:', error)
    } finally {
      setIsSaving(false)
    }
  }
  
  // Save on Ctrl+Enter
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSave()
    }
  }
  
  if (!open) return null
  
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop with blur */}
      <div 
        className="absolute inset-0 bg-background/80 backdrop-blur-sm animate-in fade-in-0 duration-200"
        onClick={() => onOpenChange(false)}
      />
      
      {/* Content */}
      <div 
        className={cn(
          "relative z-50 w-full max-w-lg mx-4 rounded-xl border bg-card shadow-2xl",
          "animate-in fade-in-0 zoom-in-95 duration-200"
        )}
        onClick={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-3">
            <div className={cn(
              "p-2 rounded-lg",
              initialWhy ? "bg-pink-500/10" : "bg-muted"
            )}>
              <Brain className={cn(
                "h-5 w-5",
                initialWhy ? "text-pink-400" : "text-muted-foreground"
              )} />
            </div>
            <div>
              <h2 className="text-lg font-semibold">Why does this exist?</h2>
              <p className="text-sm text-muted-foreground">
                {itemType}: <span className="font-medium text-foreground">{itemName}</span>
              </p>
            </div>
          </div>
          
          <button
            onClick={() => onOpenChange(false)}
            className="p-2 rounded-lg hover:bg-accent transition-colors"
            aria-label="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        
        {/* Body */}
        <div className="p-4 space-y-4">
          <div className="space-y-2">
            <label 
              htmlFor="why-input" 
              className="text-sm font-medium text-muted-foreground"
            >
              Explain the purpose or rationale for this {itemType.toLowerCase()}
            </label>
            <textarea
              ref={textareaRef}
              id="why-input"
              value={why}
              onChange={(e) => setWhy(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Why does "${itemName}" exist? What purpose does it serve?`}
              className={cn(
                "w-full min-h-[120px] p-3 rounded-lg border bg-background resize-none",
                "placeholder:text-muted-foreground/50",
                "focus:outline-none focus:ring-2 focus:ring-pink-400/50 focus:border-pink-400/50",
                "transition-all duration-200"
              )}
            />
            <p className="text-xs text-muted-foreground">
              Press <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs">Ctrl</kbd>+
              <kbd className="px-1.5 py-0.5 rounded bg-muted text-xs">Enter</kbd> to save
            </p>
          </div>
        </div>
        
        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t bg-muted/30">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            <span>Auto-generate coming soon</span>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={() => onOpenChange(false)}
              className="px-3 py-2 text-sm rounded-lg hover:bg-accent transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={!why.trim() || isSaving}
              className={cn(
                "flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg transition-all",
                "bg-pink-500 text-white hover:bg-pink-600",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                saved && "bg-green-500 hover:bg-green-500"
              )}
            >
              {saved ? (
                <>Saved!</>
              ) : isSaving ? (
                <>Saving...</>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  Save
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default WhyOverlay
