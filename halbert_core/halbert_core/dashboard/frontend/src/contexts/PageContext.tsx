/**
 * PageContext - Systematic context awareness for chat
 * 
 * This context tracks:
 * 1. Current page the user is viewing
 * 2. Items visible on that page (for auto-context)
 * 3. Focused item (when user clicks chat button on a specific discovery)
 * 
 * Usage:
 * - Wrap app with <PageContextProvider>
 * - Discovery cards call useFocusedItem(discovery) when clicked
 * - SidePanel/Chat reads context automatically
 */

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react'
import { useLocation } from 'react-router-dom'

// Discovery item that can be focused
export interface FocusedItem {
  id: string
  name: string
  title: string
  type: string
  status?: string
  description?: string
  data?: Record<string, unknown>
}

interface PageContextType {
  // Current page from route
  currentPage: string
  
  // Item user clicked chat button on (most important context)
  focusedItem: FocusedItem | null
  setFocusedItem: (item: FocusedItem | null) => void
  
  // List of visible item IDs on current page (for broader context)
  visibleItems: string[]
  registerVisibleItem: (id: string) => void
  unregisterVisibleItem: (id: string) => void
  clearVisibleItems: () => void
  
  // Build context string for chat API
  buildPageContext: () => string
}

const PageContext = createContext<PageContextType | null>(null)

export function PageContextProvider({ children }: { children: ReactNode }) {
  const location = useLocation()
  const currentPage = location.pathname.replace('/', '') || 'dashboard'
  
  const [focusedItem, setFocusedItem] = useState<FocusedItem | null>(null)
  const [visibleItems, setVisibleItems] = useState<string[]>([])
  
  const registerVisibleItem = useCallback((id: string) => {
    setVisibleItems(prev => prev.includes(id) ? prev : [...prev, id])
  }, [])
  
  const unregisterVisibleItem = useCallback((id: string) => {
    setVisibleItems(prev => prev.filter(item => item !== id))
  }, [])
  
  const clearVisibleItems = useCallback(() => {
    setVisibleItems([])
  }, [])
  
  // Listen for focused item events from openChat()
  useEffect(() => {
    const handleSetFocusedItem = (e: CustomEvent<FocusedItem>) => {
      console.log('[PageContext] Setting focused item:', e.detail)
      setFocusedItem(e.detail)
    }
    
    window.addEventListener('halbert:set-focused-item', handleSetFocusedItem as EventListener)
    return () => {
      window.removeEventListener('halbert:set-focused-item', handleSetFocusedItem as EventListener)
    }
  }, [])
  
  // Clear focused item when page changes
  useEffect(() => {
    setFocusedItem(null)
  }, [currentPage])
  
  // Build rich context string for chat
  const buildPageContext = useCallback(() => {
    const parts: string[] = []
    
    // If user clicked chat on a specific item, prioritize that
    if (focusedItem) {
      parts.push(`**User clicked chat on: @${focusedItem.id}**`)
      parts.push(`Name: ${focusedItem.title}`)
      parts.push(`Type: ${focusedItem.type}`)
      if (focusedItem.status) parts.push(`Status: ${focusedItem.status}`)
      if (focusedItem.description) parts.push(`Description: ${focusedItem.description}`)
      
      // Include all data fields
      if (focusedItem.data) {
        parts.push('Details:')
        for (const [key, value] of Object.entries(focusedItem.data)) {
          if (value != null && value !== '') {
            const niceKey = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
            parts.push(`  - ${niceKey}: ${value}`)
          }
        }
      }
    }
    
    // Add visible items count for broader context
    if (visibleItems.length > 0 && !focusedItem) {
      parts.push(`Visible items on page: ${visibleItems.length}`)
      // Could expand to include item details if needed
    }
    
    return parts.join('\n')
  }, [focusedItem, visibleItems])
  
  return (
    <PageContext.Provider value={{
      currentPage,
      focusedItem,
      setFocusedItem,
      visibleItems,
      registerVisibleItem,
      unregisterVisibleItem,
      clearVisibleItems,
      buildPageContext,
    }}>
      {children}
    </PageContext.Provider>
  )
}

// Hook to use page context
export function usePageContext() {
  const context = useContext(PageContext)
  if (!context) {
    throw new Error('usePageContext must be used within PageContextProvider')
  }
  return context
}

// Hook for components to set focused item when chat button is clicked
export function useChatWithItem() {
  const { setFocusedItem } = usePageContext()
  
  return useCallback((item: FocusedItem) => {
    setFocusedItem(item)
    // Could also trigger opening the chat panel here
  }, [setFocusedItem])
}
