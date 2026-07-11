"use client";

import { ROLE_COLOR, fmtPrice, type CrosshairData } from "@/lib/chart/helpers";
import { cn } from "@/lib/cn";
import { useLocale } from "@/lib/locale";
import { gregorianLocale } from "@/lib/resolve-locale";
import { roleShort } from "@/lib/scenario-format";

export function CrosshairTooltip({ data }: { data: CrosshairData }) {
  const locale = useLocale();
  // Flip to the opposite side near the right edge so it never covers the price
  // scale. Width from data.w to avoid a layout read during render.
  const containerWidth = data.w;
  const isRightHalf = data.x > containerWidth * 0.6;
  const style: React.CSSProperties = isRightHalf
    ? { right: containerWidth - data.x + 16, top: 60 }
    : { left: data.x + 16, top: 60 };

  const change = data.bar.close - data.bar.open;
  const changePct = (change / data.bar.open) * 100;
  const up = change >= 0;
  const date = new Date(data.time * 1000);

  return (
    <div
      className="absolute z-10 pointer-events-none min-w-[180px] ewl-card-flat px-3 py-2 text-[10px] font-mono"
      style={style}
      role="tooltip"
    >
      <div className="text-[10px] uppercase tracking-[0.14em] text-faint mb-1.5">
        {/* UTC tz to match the UTC-rendered axis (see toUTC). */}
        {date.toLocaleDateString(gregorianLocale(locale), {
          year: "numeric",
          month: "short",
          day: "numeric",
          timeZone: "UTC",
        })}
      </div>
      <Row label="O" value={fmtPrice(data.bar.open, locale)} />
      <Row label="H" value={fmtPrice(data.bar.high, locale)} tone="up" />
      <Row label="L" value={fmtPrice(data.bar.low, locale)} tone="down" />
      <Row label="C" value={fmtPrice(data.bar.close, locale)} accent />
      <div className="flex items-center justify-between gap-3 pt-1 mt-1 border-t border-border text-[10px]">
        <span className="text-muted">Δ</span>
        <span
          className={cn(
            "font-semibold",
            up ? "text-up" : "text-down",
          )}
        >
          {up ? "+" : ""}
          {fmtPrice(change, locale)} ({up ? "+" : ""}
          {changePct.toFixed(2)}%)
        </span>
      </div>
      {data.role && (
        <div className="flex items-center gap-1.5 pt-1.5 mt-1.5 border-t border-border">
          <span
            className="w-2 h-2 rounded-full"
            style={{ background: ROLE_COLOR[data.role] }}
          />
          <span className="text-[10px] uppercase tracking-[0.14em] font-semibold text-text-dim">
            Wave {roleShort(data.role)}
          </span>
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  tone,
  accent,
}: {
  label: string;
  value: string;
  tone?: "up" | "down";
  accent?: boolean;
}) {
  const color = accent
    ? "text-accent-bright"
    : tone === "up"
    ? "text-up"
    : tone === "down"
    ? "text-down"
    : "text-text-dim";
  return (
    <div className="flex items-center justify-between gap-3 leading-tight py-0.5">
      <span className="text-faint w-3">{label}</span>
      <span className={`ewl-num font-semibold ${color}`}>{value}</span>
    </div>
  );
}
