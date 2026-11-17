import { Bus, CircleHelp, Ship, TrainFront, TramFront } from "lucide-react";
import { MODE_ORDER, modeLabel } from "../lib/format";

const ICONS = { bus: Bus, rail: TrainFront, ferry: Ship, tram: TramFront } as const;

export function ModeIcon({ mode, size = 16 }: { mode: string | null | undefined; size?: number }) {
  const Icon = ICONS[mode as keyof typeof ICONS] ?? CircleHelp;
  return <Icon size={size} aria-hidden="true" />;
}

export function ModeLabel({ mode }: { mode: string | null | undefined }) {
  return (
    <span className="row" style={{ gap: 6, flexWrap: "nowrap" }}>
      <ModeIcon mode={mode} />
      {modeLabel(mode)}
    </span>
  );
}

/** Filter buttons for transport modes. `null` means all modes. */
export function ModeFilter({
  value,
  onChange,
}: {
  value: string | null;
  onChange: (mode: string | null) => void;
}) {
  return (
    <div className="row" role="group" aria-label="Filter by mode">
      <button
        type="button"
        className="chip chip-button"
        aria-pressed={value === null}
        onClick={() => onChange(null)}
      >
        All
      </button>
      {MODE_ORDER.map((mode) => (
        <button
          key={mode}
          type="button"
          className="chip chip-button"
          aria-pressed={value === mode}
          onClick={() => onChange(value === mode ? null : mode)}
        >
          <ModeIcon mode={mode} />
          {modeLabel(mode)}
        </button>
      ))}
    </div>
  );
}
