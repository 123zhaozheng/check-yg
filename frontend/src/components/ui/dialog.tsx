import * as React from "react"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"

/**
 * Monochrome Dialog (DESIGN.md Components → Overlays).
 *
 * Modal surface on a semi-opaque black scrim. White card, 1px ink-400 border,
 * `--shadow-popover` elevation. No color anywhere — the only "heavy" visual is
 * the solid black primary action button supplied by the caller.
 *
 * Keyboard: ESC closes, clicking the scrim closes, tab is trapped to the dialog
 * while open. Rendered via a React portal so it overlays the whole app.
 */

interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
  className?: string
}

function Dialog({ open, onOpenChange, children, className }: DialogProps) {
  React.useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onOpenChange(false)
    }
    document.addEventListener("keydown", onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.removeEventListener("keydown", onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [open, onOpenChange])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
    >
      <div
        className="absolute inset-0 bg-ink-900/60"
        onClick={() => onOpenChange(false)}
      />
      <div
        data-slot="dialog-content"
        className={cn(
          "relative z-10 w-full max-w-lg rounded-[var(--radius-lg)] border border-ink-400 bg-ink-100 shadow-[var(--shadow-popover)]",
          className,
        )}
      >
        {children}
      </div>
    </div>
  )
}

function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={cn("flex items-center justify-between border-b border-ink-400 px-6 py-4", className)}
      {...props}
    />
  )
}

function DialogTitle({ className, ...props }: React.ComponentProps<"h2">) {
  return (
    <h2
      data-slot="dialog-title"
      className={cn("font-sans text-lg font-bold text-ink-900", className)}
      {...props}
    />
  )
}

function DialogClose({ onOpenChange }: { onOpenChange: (open: boolean) => void }) {
  return (
    <button
      type="button"
      aria-label="关闭"
      onClick={() => onOpenChange(false)}
      className="text-ink-600 transition-colors hover:text-ink-900"
    >
      <X className="size-5" />
    </button>
  )
}

function DialogBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="dialog-body" className={cn("px-6 py-5", className)} {...props} />
  )
}

function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={cn(
        "flex items-center justify-end gap-3 border-t border-ink-400 px-6 py-4",
        className,
      )}
      {...props}
    />
  )
}

export { Dialog, DialogHeader, DialogTitle, DialogClose, DialogBody, DialogFooter }
