import type { ReactNode } from "react";

/**
 * A table that may scroll sideways on a narrow screen. It can take keyboard focus and has
 * a name, so a keyboard user can reach it and scroll it with the arrow keys.
 */
export function TableScroll({ label, children }: { label: string; children: ReactNode }) {
  return (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- a scrollable region must be focusable (WCAG 2.1.1)
    <div className="table-wrap" role="region" aria-label={label} tabIndex={0}>
      {children}
    </div>
  );
}
