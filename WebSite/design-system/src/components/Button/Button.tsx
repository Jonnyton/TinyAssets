import * as React from "react";
import "./Button.css";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "link";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps {
  /** Button label / contents. */
  children?: React.ReactNode;
  /** Visual emphasis. `primary` = ember action; `secondary` = violet; `ghost` = quiet outline; `link` = inline text. */
  variant?: ButtonVariant;
  /** Control height + type scale. */
  size?: ButtonSize;
  /** When set, renders an anchor (`<a>`) instead of a `<button>`. */
  href?: string;
  /** Disable interaction (button form only visually disables; anchors get a `disabled` class). */
  disabled?: boolean;
  /** Click handler. Ignored when `disabled`. */
  onClick?: (e: React.MouseEvent) => void;
  /** Extra class names appended to the root. */
  className?: string;
}

/**
 * Button — the one action control. Ember `primary` is reserved for the single
 * most important action on a surface; everything else steps down to secondary,
 * ghost, or link. Renders as an anchor when `href` is provided.
 */
export function Button({
  children,
  variant = "primary",
  size = "md",
  href,
  disabled = false,
  onClick,
  className = "",
}: ButtonProps) {
  const cls = `btn btn--${variant} btn--${size}${disabled ? " disabled" : ""}${className ? " " + className : ""}`;

  if (href) {
    return (
      <a href={href} className={cls} aria-disabled={disabled || undefined}>
        {children}
      </a>
    );
  }
  return (
    <button
      type="button"
      className={cls}
      disabled={disabled}
      onClick={disabled ? undefined : onClick}
    >
      {children}
    </button>
  );
}

export default Button;
