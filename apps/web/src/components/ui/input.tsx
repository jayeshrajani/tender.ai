import * as React from "react";

import { cn } from "@/lib/cn";

const control =
  "w-full rounded-xl border border-line bg-surface px-3 text-sm text-ink placeholder:text-faint transition-colors duration-150 hover:border-line-strong focus-visible:border-accent focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-accent/15 disabled:cursor-not-allowed disabled:bg-subtle aria-[invalid=true]:border-danger [color-scheme:inherit]";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(control, "h-9", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => <textarea ref={ref} className={cn(control, "min-h-20 py-2", className)} {...props} />,
);
Textarea.displayName = "Textarea";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn(control, "select-chevron h-9 pr-8", className)} {...props}>
      {children}
    </select>
  ),
);
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-xs font-medium text-ink", className)} {...props} />;
}

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
}

export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  const hintId = `${htmlFor}-hint`;
  const errorId = `${htmlFor}-error`;
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Label htmlFor={htmlFor}>
        {label}
        {required ? <span className="text-danger"> *</span> : null}
      </Label>
      {React.isValidElement<{ "aria-describedby"?: string; "aria-invalid"?: boolean }>(children)
        ? React.cloneElement(children, {
            "aria-describedby": [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(" ") || undefined,
            "aria-invalid": error ? true : undefined,
          })
        : children}
      {hint && !error ? (
        <p id={hintId} className="text-2xs text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-2xs font-medium text-danger">
          {error}
        </p>
      ) : null}
    </div>
  );
}
