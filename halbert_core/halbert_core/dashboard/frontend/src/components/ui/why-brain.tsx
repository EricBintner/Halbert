/**
 * WhyBrain Component
 * 
 * A brain icon that indicates whether an item has a "Why" explanation.
 * - Grey: No explanation (undefined)
 * - Pink/Magenta: Has explanation (defined)
 * 
 * Clicking opens the WhyOverlay to view/edit the explanation.
 */
import * as React from 'react'
import { Brain } from 'lucide-react'
import { cn } from '@/lib/utils'
import { WhyOverlay } from './why-overlay'

interface WhyBrainProps {
  /** Unique identifier for this item (e.g., "service:nginx", "disk:nvme0n1") */
  itemId: string
  /** Human-readable name of the item */
  itemName: string
  /** Type/category of the item */
  itemType: string
  /** Current "why" explanation (undefined if not set) */
  why?: string
  /** Callback when why is saved */
  onWhySaved?: (why: string) => void
  /** Size variant */
  size?: 'sm' | 'md' | 'lg'
  /** Additional class names */
  className?: string
}

export function WhyBrain({
  itemId,
  itemName,
  itemType,
  why,
  onWhySaved,
  size = 'md',
  className,
}: WhyBrainProps) {
  const [isOpen, setIsOpen] = React.useState(false)
  const [currentWhy, setCurrentWhy] = React.useState(why)
  
  const isDefined = Boolean(currentWhy && currentWhy.trim().length > 0)
  
  const sizeClasses = {
    sm: 'h-3.5 w-3.5',
    md: 'h-4 w-4',
    lg: 'h-5 w-5',
  }
  
  const handleSave = (newWhy: string) => {
    setCurrentWhy(newWhy)
    onWhySaved?.(newWhy)
  }
  
  return (
    <>
      <button
        onClick={(e) => {
          e.stopPropagation()
          setIsOpen(true)
        }}
        className={cn(
          "inline-flex items-center justify-center rounded-md p-1 transition-all duration-200",
          "hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-1",
          isDefined 
            ? "text-pink-400 hover:text-pink-300" 
            : "text-muted-foreground/50 hover:text-muted-foreground",
          className
        )}
        title={isDefined ? "View/edit why this exists" : "Add explanation for why this exists"}
        aria-label={isDefined ? `Why: ${currentWhy}` : "Add why explanation"}
      >
        <Brain 
          className={cn(
            sizeClasses[size],
            isDefined && "fill-pink-400/20"
          )} 
        />
      </button>
      
      <WhyOverlay
        open={isOpen}
        onOpenChange={setIsOpen}
        itemId={itemId}
        itemName={itemName}
        itemType={itemType}
        initialWhy={currentWhy}
        onSave={handleSave}
      />
    </>
  )
}

export default WhyBrain
