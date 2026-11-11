import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-xl font-medium transition-[color,background-color,border-color,box-shadow,transform] duration-150 ease-snappy active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "bg-accent text-on-accent shadow-[0_6px_18px_-8px_var(--accent)] hover:bg-accent-hover hover:shadow-[0_8px_22px_-8px_var(--accent)]",
        secondary: "border border-line bg-surface text-ink shadow-card hover:border-line-strong hover:bg-raised",
        ghost: "text-ink hover:bg-subtle",
        quiet: "text-muted hover:bg-subtle hover:text-ink",
        danger: "border border-danger-line bg-surface text-danger hover:bg-danger-soft",
        link: "h-auto px-0 text-accent underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-7 rounded-lg px-2.5 text-xs",
        md: "h-9 px-3.5 text-sm",
        lg: "h-11 px-5 text-sm",
        icon: "size-8 rounded-lg",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, type, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        type={asChild ? undefined : (type ?? "button")}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
