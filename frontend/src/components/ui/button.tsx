import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

/**
 * Monochrome button (DESIGN.md Components → Buttons).
 *   primary   — solid #000 bg + #fff text, no shadow
 *   secondary — 1px #000 border, transparent bg, #000 text
 *   tertiary  — text only, underline on hover
 * Focus ring: dark outer + light halo (no blue).
 */
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-[var(--radius-DEFAULT)] font-sans text-sm font-medium transition-all outline-none select-none disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*=size-])]:size-4",
  {
    variants: {
      variant: {
        primary:
          "bg-ink-900 text-ink-100 hover:bg-ink-800 active:translate-y-px focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2",
        secondary:
          "border border-ink-900 bg-transparent text-ink-900 hover:bg-ink-300 active:translate-y-px focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2",
        tertiary:
          "bg-transparent text-ink-900 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2",
        destructive:
          "border-2 border-ink-900 bg-ink-900 text-ink-100 font-bold hover:bg-ink-800 focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2",
        ghost:
          "bg-transparent text-ink-800 hover:bg-ink-300 focus-visible:outline-2 focus-visible:outline-ink-800 focus-visible:outline-offset-2",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-6 text-base",
        icon: "size-9",
        "icon-sm": "size-8",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  },
)

export interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}

export { Button, buttonVariants }
