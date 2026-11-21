import React, { useState } from 'react';
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Inbox,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';

export interface AreaPoint {
  bucket: string;
  value: number;
}

export interface StackedSeriesPoint {
  bucket: string;
  values: Array<{ key: string; label: string; value: number; color: string }>;
}

export interface RankBarItem {
  id: string;
  title: string;
  subtitle?: string;
  value: number;
  valueLabel: string;
  secondaryLabel?: string;
}

function formatShortBucket(bucket: string): string {
  if (!bucket) return '';
  if (bucket.length === 10 && bucket.includes('-')) {
    // YYYY-MM-DD -> MM/DD
    return `${bucket.slice(5, 7)}/${bucket.slice(8, 10)}`;
  }
  return bucket;
}

export const DeltaBadge: React.FC<{ delta?: number | null; label?: string | null }> = ({
  delta,
  label,
}) => {
  if (delta === null || delta === undefined) {
    return label ? <span className="text-[11px] text-slate-400">{label}</span> : null;
  }
  const isPos = delta > 0;
  const isNeg = delta < 0;
  const color = isPos
    ? 'text-emerald-700 bg-emerald-50'
    : isNeg
    ? 'text-rose-700 bg-rose-50'
    : 'text-slate-600 bg-slate-100';

  return (
    <span className="inline-flex items-center gap-1.5 flex-wrap">
      <span className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-semibold font-mono ${color}`}>
        {isPos ? (
          <TrendingUp className="w-2.5 h-2.5" />
        ) : isNeg ? (
          <TrendingDown className="w-2.5 h-2.5" />
        ) : (
          <Minus className="w-2.5 h-2.5" />
        )}
        {isPos ? `+${delta}%` : `${delta}%`}
      </span>
      {label && <span className="text-[11px] text-slate-400">{label}</span>}
    </span>
  );
};

export const AreaTrendChart: React.FC<{
  title: string;
  subtitle?: string;
  data: AreaPoint[];
  color?: string;
  unit?: string;
  loading?: boolean;
  headerRight?: React.ReactNode;
}> = ({ title, subtitle, data, color = '#4f46e5', unit = '', loading = false, headerRight }) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const width = 560;
  const height = 180;
  const pad = { top: 16, right: 16, bottom: 28, left: 40 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const maxVal = Math.max(1, ...data.map((d) => d.value));
  const yTicks = [0, Math.round(maxVal / 2), maxVal];

  const coords = data.map((d, idx) => {
    const x =
      data.length === 1
        ? pad.left + plotW / 2
        : pad.left + (idx / Math.max(1, data.length - 1)) * plotW;
    const y = pad.top + plotH - (d.value / maxVal) * plotH;
    return { x, y, ...d };
  });

  const linePath = coords
    .map((c, idx) => `${idx === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`)
    .join(' ');
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords[coords.length - 1].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)} L ${coords[0].x.toFixed(1)} ${(pad.top + plotH).toFixed(1)} Z`
      : '';

  const labelStep = Math.max(1, Math.ceil(data.length / 6));
  const hovered = hoverIdx !== null && coords[hoverIdx] ? coords[hoverIdx] : null;
  const totalSum = data.reduce((acc, d) => acc + d.value, 0);

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs flex flex-col justify-between">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {headerRight}
          {!loading && (
            <span className="text-xs font-mono font-bold text-slate-800 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-lg">
              {totalSum.toLocaleString()}
              {unit ? ` ${unit}` : ''}
            </span>
          )}
        </div>
      </div>

      {loading ? (
        <div className="h-[180px] rounded-xl bg-slate-100/80 animate-pulse" />
      ) : data.length === 0 ? (
        <div className="h-[180px] flex flex-col items-center justify-center text-slate-400 text-xs bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
          <Inbox className="w-5 h-5 mb-1.5 text-slate-300" />
          <span>No records in selected period</span>
        </div>
      ) : (
        <div className="relative">
          {hovered && (
            <div className="absolute right-2 top-0 z-10 pointer-events-none bg-slate-900 text-white text-[11px] font-mono px-2.5 py-1 rounded-lg shadow-md">
              <span className="text-slate-300">{hovered.bucket}:</span>{' '}
              <span className="font-bold">
                {hovered.value.toLocaleString()}
                {unit ? ` ${unit}` : ''}
              </span>
            </div>
          )}
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-[180px] overflow-visible"
            onMouseLeave={() => setHoverIdx(null)}
          >
            <defs>
              <linearGradient id={`area-${title.replace(/\W+/g, '')}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity="0.22" />
                <stop offset="100%" stopColor={color} stopOpacity="0.01" />
              </linearGradient>
            </defs>

            {yTicks.map((tick, i) => {
              const y = pad.top + plotH - (tick / maxVal) * plotH;
              return (
                <g key={i}>
                  <line
                    x1={pad.left}
                    y1={y}
                    x2={width - pad.right}
                    y2={y}
                    stroke="#e2e8f0"
                    strokeDasharray="3 3"
                  />
                  <text
                    x={pad.left - 8}
                    y={y + 3}
                    textAnchor="end"
                    className="fill-slate-400 text-[10px] font-mono"
                  >
                    {tick}
                  </text>
                </g>
              );
            })}

            {areaPath && (
              <path d={areaPath} fill={`url(#area-${title.replace(/\W+/g, '')})`} />
            )}
            {linePath && (
              <path
                d={linePath}
                fill="none"
                stroke={color}
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            )}

            {coords.map((c, idx) => (
              <g key={c.bucket}>
                {idx % labelStep === 0 && (
                  <text
                    x={c.x}
                    y={height - 6}
                    textAnchor="middle"
                    className="fill-slate-400 text-[10px] font-mono"
                  >
                    {formatShortBucket(c.bucket)}
                  </text>
                )}
                <circle
                  cx={c.x}
                  cy={c.y}
                  r={hoverIdx === idx ? 4.5 : coords.length <= 20 ? 2.8 : 0}
                  fill={color}
                  stroke="#ffffff"
                  strokeWidth="1.5"
                />
                <rect
                  x={c.x - Math.max(8, plotW / Math.max(1, coords.length) / 2)}
                  y={pad.top}
                  width={Math.max(16, plotW / Math.max(1, coords.length))}
                  height={plotH}
                  fill="transparent"
                  className="cursor-crosshair"
                  onMouseEnter={() => setHoverIdx(idx)}
                />
              </g>
            ))}
          </svg>
        </div>
      )}
    </div>
  );
};

export const MultiBarChart: React.FC<{
  title: string;
  subtitle?: string;
  data: StackedSeriesPoint[];
  legend: Array<{ key: string; label: string; color: string }>;
  loading?: boolean;
  unit?: string;
}> = ({ title, subtitle, data, legend, loading = false, unit = '' }) => {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);

  const width = 560;
  const height = 180;
  const pad = { top: 16, right: 16, bottom: 28, left: 42 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;

  const maxVal = Math.max(
    1,
    ...data.flatMap((d) => d.values.map((v) => v.value))
  );
  const yTicks = [0, Math.round(maxVal / 2), maxVal];
  const groupW = plotW / Math.max(1, data.length);
  const barGap = 2;
  const numBars = Math.max(1, legend.length);
  const singleBarW = Math.max(3, Math.min(18, (groupW * 0.72) / numBars - barGap));
  const labelStep = Math.max(1, Math.ceil(data.length / 6));
  const hovered = hoverIdx !== null && data[hoverIdx] ? data[hoverIdx] : null;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs flex flex-col justify-between">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2 mb-3">
        <div>
          <h3 className="text-sm font-bold text-slate-900">{title}</h3>
          {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
        </div>
        <div className="flex items-center gap-3 flex-wrap text-[11px] text-slate-600">
          {legend.map((l) => (
            <span key={l.key} className="inline-flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-xs" style={{ backgroundColor: l.color }} />
              <span>{l.label}</span>
            </span>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="h-[180px] rounded-xl bg-slate-100/80 animate-pulse" />
      ) : data.length === 0 ? (
        <div className="h-[180px] flex flex-col items-center justify-center text-slate-400 text-xs bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
          <Inbox className="w-5 h-5 mb-1.5 text-slate-300" />
          <span>No records in selected period</span>
        </div>
      ) : (
        <div className="relative">
          {hovered && (
            <div className="absolute right-2 top-0 z-10 pointer-events-none bg-slate-900 text-white text-[11px] font-mono px-2.5 py-1.5 rounded-lg shadow-md space-y-0.5">
              <div className="text-slate-300 font-semibold">{hovered.bucket}</div>
              {hovered.values.map((v) => (
                <div key={v.key} className="flex items-center justify-between gap-3">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full" style={{ backgroundColor: v.color }} />
                    <span>{v.label}:</span>
                  </span>
                  <span className="font-bold">
                    {v.value.toLocaleString()}
                    {unit ? ` ${unit}` : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
          <svg
            viewBox={`0 0 ${width} ${height}`}
            className="w-full h-[180px] overflow-visible"
            onMouseLeave={() => setHoverIdx(null)}
          >
            {yTicks.map((tick, i) => {
              const y = pad.top + plotH - (tick / maxVal) * plotH;
              return (
                <g key={i}>
                  <line
                    x1={pad.left}
                    y1={y}
                    x2={width - pad.right}
                    y2={y}
                    stroke="#e2e8f0"
                    strokeDasharray="3 3"
                  />
                  <text
                    x={pad.left - 8}
                    y={y + 3}
                    textAnchor="end"
                    className="fill-slate-400 text-[10px] font-mono"
                  >
                    {tick}
                  </text>
                </g>
              );
            })}

            {data.map((pt, idx) => {
              const cx = pad.left + idx * groupW + groupW / 2;
              const totalGroupW = numBars * singleBarW + (numBars - 1) * barGap;
              const startX = cx - totalGroupW / 2;
              return (
                <g key={pt.bucket}>
                  {hoverIdx === idx && (
                    <rect
                      x={pad.left + idx * groupW + 2}
                      y={pad.top}
                      width={Math.max(4, groupW - 4)}
                      height={plotH}
                      fill="#f1f5f9"
                      rx={4}
                    />
                  )}
                  {pt.values.map((v, vIdx) => {
                    const barH = Math.max(v.value > 0 ? 2 : 0, (v.value / maxVal) * plotH);
                    const x = startX + vIdx * (singleBarW + barGap);
                    const y = pad.top + plotH - barH;
                    return (
                      <rect
                        key={v.key}
                        x={x}
                        y={y}
                        width={singleBarW}
                        height={barH}
                        fill={v.color}
                        rx={2}
                      />
                    );
                  })}
                  {idx % labelStep === 0 && (
                    <text
                      x={cx}
                      y={height - 6}
                      textAnchor="middle"
                      className="fill-slate-400 text-[10px] font-mono"
                    >
                      {formatShortBucket(pt.bucket)}
                    </text>
                  )}
                  <rect
                    x={pad.left + idx * groupW}
                    y={pad.top}
                    width={groupW}
                    height={plotH}
                    fill="transparent"
                    className="cursor-pointer"
                    onMouseEnter={() => setHoverIdx(idx)}
                  />
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
};

export const HorizontalRankChart: React.FC<{
  title: string;
  subtitle?: string;
  items: RankBarItem[];
  barColorClass?: string;
  loading?: boolean;
  emptyText?: string;
  onItemClick?: (id: string) => void;
}> = ({
  title,
  subtitle,
  items,
  barColorClass = 'bg-indigo-500',
  loading = false,
  emptyText = 'No ranked data available.',
  onItemClick,
}) => {
  const maxVal = Math.max(1, ...items.map((i) => i.value));

  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs flex flex-col">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-slate-900">{title}</h3>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4, 5].map((n) => (
            <div key={n} className="space-y-1.5">
              <div className="h-3 w-2/3 bg-slate-100 rounded animate-pulse" />
              <div className="h-2 w-full bg-slate-100 rounded-full animate-pulse" />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="py-8 flex flex-col items-center justify-center text-slate-400 text-xs">
          <Inbox className="w-5 h-5 mb-1.5 text-slate-300" />
          <span>{emptyText}</span>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item, idx) => {
            const pct = Math.max(4, Math.round((item.value / maxVal) * 100));
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => onItemClick?.(item.id)}
                className={`w-full text-left group rounded-lg p-1.5 -mx-1.5 transition-colors ${
                  onItemClick ? 'hover:bg-slate-50 cursor-pointer' : 'cursor-default'
                }`}
              >
                <div className="flex items-center justify-between gap-2 text-xs mb-1">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-[10px] font-mono font-bold text-slate-400 w-4 shrink-0">
                      #{idx + 1}
                    </span>
                    <span className="font-semibold text-slate-800 group-hover:text-indigo-600 truncate transition-colors">
                      {item.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 font-mono text-[11px]">
                    {item.secondaryLabel && (
                      <span className="text-slate-400 hidden sm:inline">{item.secondaryLabel}</span>
                    )}
                    <span className="font-bold text-slate-900">{item.valueLabel}</span>
                  </div>
                </div>
                {item.subtitle && (
                  <div className="text-[11px] text-slate-400 font-mono truncate pl-6 mb-1">
                    {item.subtitle}
                  </div>
                )}
                <div className="pl-6">
                  <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-300 ${barColorClass}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export const KpiSkeletonGrid: React.FC<{ count?: number }> = ({ count = 8 }) => (
  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
    {Array.from({ length: count }).map((_, i) => (
      <div key={i} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-2xs space-y-3">
        <div className="flex items-center justify-between">
          <div className="h-3 w-24 bg-slate-100 rounded animate-pulse" />
          <div className="w-8 h-8 rounded-lg bg-slate-100 animate-pulse" />
        </div>
        <div className="h-7 w-28 bg-slate-200/70 rounded animate-pulse" />
        <div className="h-3 w-36 bg-slate-100 rounded animate-pulse" />
      </div>
    ))}
  </div>
);

export const TableSkeletonRows: React.FC<{ cols: number; rows?: number }> = ({ cols, rows = 6 }) => (
  <>
    {Array.from({ length: rows }).map((_, rIdx) => (
      <tr key={rIdx}>
        {Array.from({ length: cols }).map((__, cIdx) => (
          <td key={cIdx} className="py-3.5 px-4">
            <div
              className="h-3.5 bg-slate-100 rounded animate-pulse"
              style={{ width: `${55 + ((rIdx * 17 + cIdx * 23) % 35)}%` }}
            />
          </td>
        ))}
      </tr>
    ))}
  </>
);

export const ErrorRetryBanner: React.FC<{
  message: string;
  onRetry: () => void;
}> = ({ message, onRetry }) => (
  <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between gap-3">
    <div className="flex items-center gap-2.5 min-w-0">
      <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
      <span className="font-medium truncate">{message}</span>
    </div>
    <button
      type="button"
      onClick={onRetry}
      className="px-3 py-1.5 rounded-lg bg-white border border-rose-200 hover:bg-rose-100 text-rose-700 font-semibold text-xs inline-flex items-center gap-1.5 shrink-0 cursor-pointer transition-colors"
    >
      <RefreshCw className="w-3.5 h-3.5" />
      <span>Retry</span>
    </button>
  </div>
);

export const PaginationFooter: React.FC<{
  page: number;
  limit: number;
  total: number;
  itemCount: number;
  entityLabel: string;
  onPageChange: (nextPage: number) => void;
}> = ({ page, limit, total, itemCount, entityLabel, onPageChange }) => {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  const start = itemCount > 0 ? (page - 1) * limit + 1 : 0;
  const end = Math.min(page * limit, total);

  return (
    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-500 pt-3 border-t border-slate-100">
      <span>
        Showing <span className="font-semibold text-slate-700">{start.toLocaleString()}</span>–
        <span className="font-semibold text-slate-700">{end.toLocaleString()}</span> of{' '}
        <span className="font-semibold text-slate-700">{total.toLocaleString()}</span> {entityLabel}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="px-2.5 py-1.5 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer inline-flex items-center gap-1"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Prev</span>
        </button>
        <span className="font-mono text-xs px-2 text-slate-700">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
          className="px-2.5 py-1.5 rounded-lg border border-slate-200 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 transition-colors cursor-pointer inline-flex items-center gap-1"
        >
          <span className="hidden sm:inline">Next</span>
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};
