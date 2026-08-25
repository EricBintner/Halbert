import { useState, useRef, useEffect, ReactNode } from 'react';
import { Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { createPortal } from 'react-dom';

export interface InfoTooltipProps {
  content: ReactNode;
  className?: string;
  side?: 'top' | 'right' | 'bottom' | 'left';
  href?: string;
}

export function InfoTooltip({ content, className, side = 'top', href }: InfoTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);
  const [coords, setCoords] = useState({ top: 0, left: 0, actualSide: side });
  const triggerRef = useRef<HTMLElement>(null);

  const updatePosition = () => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();

    let top = 0;
    let left = 0;
    const gap = 8;

    top = rect.top - gap;
    left = rect.left + rect.width / 2;

    if (side === 'bottom') {
      top = rect.bottom + gap;
    } else if (side === 'left') {
      top = rect.top + rect.height / 2;
      left = rect.left - gap;
    } else if (side === 'right') {
      top = rect.top + rect.height / 2;
      left = rect.right + gap;
    }

    if ((side === 'top' || side === 'bottom') && top < 150) {
      top = rect.bottom + gap;
      setCoords({ top, left, actualSide: 'bottom' });
    } else {
      setCoords({ top, left, actualSide: side });
    }
  };

  const handleMouseEnter = () => {
    updatePosition();
    setIsVisible(true);
  };

  const handleMouseLeave = () => {
    setIsVisible(false);
  };

  useEffect(() => {
    if (!isVisible) return;
    const handleScroll = () => setIsVisible(false);
    window.addEventListener('scroll', handleScroll, true);
    window.addEventListener('resize', handleScroll);
    return () => {
      window.removeEventListener('scroll', handleScroll, true);
      window.removeEventListener('resize', handleScroll);
    };
  }, [isVisible]);

  const Component = href ? 'a' : 'button';
  const props = href ? {
    href,
    target: '_blank',
    rel: 'noopener noreferrer',
    onClick: (e: React.MouseEvent) => e.stopPropagation()
  } : {
    type: 'button' as const
  };

  return (
    <>
      <Component
        ref={triggerRef as any}
        {...props}
        className={cn(
          "text-text-muted hover:text-primary transition-colors cursor-help inline-flex items-center justify-center",
          className
        )}
        aria-label={href ? "Read documentation" : "More information"}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        onFocus={() => setIsVisible(true)}
        onBlur={() => setIsVisible(false)}
      >
        <Info className="w-3.5 h-3.5" />
      </Component>

      {isVisible && typeof document !== 'undefined' && createPortal(
        <div
          className={cn(
            "fixed z-50 overflow-hidden rounded-md border border-border bg-surface-raised px-3 py-1.5 text-xs text-text shadow-md animate-in fade-in-0 zoom-in-95",
            "max-w-xs leading-relaxed pointer-events-none"
          )}
          style={{
            top: coords.top,
            left: coords.left,
            transform: coords.actualSide === 'top' ? 'translate(-50%, -100%)' :
                       coords.actualSide === 'bottom' ? 'translate(-50%, 0)' :
                       coords.actualSide === 'left' ? 'translate(-100%, -50%)' :
                       'translate(0, -50%)'
          }}
        >
          {content}
        </div>,
        document.body
      )}
    </>
  );
}
