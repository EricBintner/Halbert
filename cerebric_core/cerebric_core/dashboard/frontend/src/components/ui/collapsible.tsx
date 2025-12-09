import * as React from "react"
import { cn } from "@/lib/utils"
import { ChevronDown, ChevronRight } from "lucide-react"

interface CollapsibleProps {
  title: React.ReactNode
  children: React.ReactNode
  defaultOpen?: boolean
  summary?: React.ReactNode
  className?: string
  headerClassName?: string
  contentClassName?: string
  actions?: React.ReactNode
  stickyHeader?: boolean  // Make header sticky when expanded
}

export function Collapsible({
  title,
  children,
  defaultOpen = false,
  summary,
  className,
  headerClassName,
  contentClassName,
  actions,
  stickyHeader = false,
}: CollapsibleProps) {
  const [isOpen, setIsOpen] = React.useState(defaultOpen)

  return (
    <div className={cn("rounded-lg border bg-card text-card-foreground shadow-sm", className)}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          "flex w-full items-center justify-between px-4 py-3 text-left rounded-t-lg",
          "hover:bg-muted/50 transition-colors",
          isOpen && "border-b",
          isOpen && stickyHeader && "sticky -top-8 z-10 bg-card",
          headerClassName
        )}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {isOpen ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <div className="flex-1 min-w-0">
            <div className="font-medium">{title}</div>
            {!isOpen && summary && (
              <div className="text-sm text-muted-foreground truncate mt-0.5">
                {summary}
              </div>
            )}
          </div>
        </div>
        {actions && (
          <div className="flex items-center gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
            {actions}
          </div>
        )}
      </button>
      {isOpen && (
        <div className={cn("p-4", contentClassName)}>
          {children}
        </div>
      )}
    </div>
  )
}

interface CollapsibleGroupProps {
  children: React.ReactNode
  className?: string
}

export function CollapsibleGroup({ children, className }: CollapsibleGroupProps) {
  return (
    <div className={cn("space-y-3", className)}>
      {children}
    </div>
  )
}
