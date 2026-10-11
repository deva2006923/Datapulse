import React, { useState, useMemo, useEffect } from 'react';
import {
  BarChart3,
  LineChart,
  PieChart,
  Activity,
  Table as TableIcon,
  Sparkles,
  Info,
  ArrowRight,
  ChevronRight,
  TrendingUp,
} from 'lucide-react';
import {
  VisualizationRecommendation,
  SupportedChartType,
} from '../services/visualizationAnalyzer';

export interface RecommendationBannerProps {
  recommendation: VisualizationRecommendation;
  viewMode: 'table' | 'chart';
  onApplyRecommendation: (type?: SupportedChartType) => void;
  onSetPrompt?: (newPrompt: string) => void;
}

export const RecommendationBanner: React.FC<RecommendationBannerProps> = ({
  recommendation,
  viewMode,
  onApplyRecommendation,
  onSetPrompt,
}) => {
  return (
    <div className="space-y-3">
      {/* Recommended Visualization Suggestion Header */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-indigo-50/90 via-purple-50/70 to-slate-50 border border-indigo-100 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs shadow-xs">
        <div className="flex items-start sm:items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-xs">
            <Sparkles className="w-4 h-4" />
          </div>
          <div className="space-y-0.5">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-bold text-slate-900 text-xs">
                AI Recommended Visualization:
              </span>
              <span className="px-2 py-0.5 rounded-full font-semibold font-mono bg-indigo-100 text-indigo-700 border border-indigo-200 text-[11px] capitalize flex items-center gap-1">
                {recommendation.recommendedType === 'table' ? (
                  <TableIcon className="w-3 h-3" />
                ) : recommendation.recommendedType === 'line' ? (
                  <LineChart className="w-3 h-3" />
                ) : recommendation.recommendedType === 'donut' ? (
                  <PieChart className="w-3 h-3" />
                ) : recommendation.recommendedType === 'scatter' ? (
                  <Activity className="w-3 h-3" />
                ) : recommendation.recommendedType === 'kpi' ? (
                  <TrendingUp className="w-3 h-3" />
                ) : (
                  <BarChart3 className="w-3 h-3" />
                )}
                <span>{recommendation.title}</span>
              </span>
            </div>
            <p className="text-slate-600 leading-relaxed text-[11px]">
              {recommendation.explanation}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 self-start md:self-auto shrink-0">
          <button
            type="button"
            onClick={() => onApplyRecommendation(recommendation.recommendedType)}
            className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-medium text-xs shadow-xs transition-colors cursor-pointer flex items-center gap-1.5"
          >
            <span>
              {viewMode === 'table' && recommendation.recommendedType !== 'table'
                ? `View as ${recommendation.recommendedType.toUpperCase()}`
                : viewMode === 'chart'
                ? 'Current View: Chart'
                : 'Selected View: Table'}
            </span>
            <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {/* Aggregation guidance callout if query returned unaggregated records */}
      {recommendation.requiresAggregationWarning && (
        <div className="p-3.5 rounded-xl bg-amber-50/80 border border-amber-200 text-amber-900 text-xs flex items-start gap-2.5">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <span className="font-bold block text-[11px] uppercase tracking-wide text-amber-800">
              Aggregation Note & Follow-up Guidance
            </span>
            <p className="text-[11px] text-amber-800/90 leading-relaxed">
              {recommendation.requiresAggregationWarning}
            </p>
            {onSetPrompt && (
              <button
                type="button"
                onClick={() =>
                  onSetPrompt(
                    `count of records grouped by ${recommendation.dimensionColumn || 'category'}`
                  )
                }
                className="mt-1 text-[11px] font-semibold text-indigo-700 hover:text-indigo-900 hover:underline cursor-pointer flex items-center gap-1"
              >
                <span>Pre-fill follow-up query: "count of records grouped by {recommendation.dimensionColumn || 'category'}"</span>
                <ChevronRight className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export interface QueryChartProps {
  results: Record<string, any>[];
  columns: string[];
  recommendation: VisualizationRecommendation;
  onSetPrompt?: (newPrompt: string) => void;
  onSwitchToTable?: () => void;
}

const PALETTE = [
  '#4f46e5', // indigo-600
  '#06b6d4', // cyan-500
  '#10b981', // emerald-500
  '#f59e0b', // amber-500
  '#ec4899', // pink-500
  '#8b5cf6', // purple-500
  '#3b82f6', // blue-500
  '#14b8a6', // teal-500
];

export const QueryChart: React.FC<QueryChartProps> = ({
  results,
  columns,
  recommendation,
  onSetPrompt,
  onSwitchToTable,
}) => {
  // Chart selection state
  const [selectedChartType, setSelectedChartType] = useState<SupportedChartType>(
    recommendation.recommendedType === 'table' ? 'bar' : recommendation.recommendedType
  );
  const [selectedDimension, setSelectedDimension] = useState<string>(
    recommendation.dimensionColumn || recommendation.availableDimensions[0] || columns[0] || ''
  );
  const [selectedMeasure, setSelectedMeasure] = useState<string>(
    recommendation.measureColumn || recommendation.availableMeasures[0] || ''
  );
  const [secondaryMeasure, setSecondaryMeasure] = useState<string>(
    recommendation.secondaryMeasureColumn ||
      recommendation.availableMeasures[1] ||
      recommendation.availableMeasures[0] ||
      ''
  );

  // Sync state if recommendation changes
  useEffect(() => {
    if (recommendation.dimensionColumn) {
      setSelectedDimension(recommendation.dimensionColumn);
    } else if (recommendation.availableDimensions[0]) {
      setSelectedDimension(recommendation.availableDimensions[0]);
    }

    if (recommendation.measureColumn) {
      setSelectedMeasure(recommendation.measureColumn);
    } else if (recommendation.availableMeasures[0]) {
      setSelectedMeasure(recommendation.availableMeasures[0]);
    }

    if (recommendation.recommendedType !== 'table') {
      setSelectedChartType(recommendation.recommendedType);
    }
  }, [recommendation]);

  const hasMeasures = recommendation.availableMeasures.length > 0;

  // Chart data extraction & normalization (safely capped to top 40 for rendering)
  const chartData = useMemo(() => {
    if (!results || results.length === 0) return [];
    const maxItems = 40;
    const slice = results.slice(0, maxItems);

    return slice.map((row, idx) => {
      const dimVal = row[selectedDimension];
      const rawMeasureVal = selectedMeasure ? row[selectedMeasure] : null;
      const measureVal =
        rawMeasureVal !== null && rawMeasureVal !== undefined && !isNaN(Number(rawMeasureVal))
          ? Number(rawMeasureVal)
          : 0;

      const rawSecVal = secondaryMeasure ? row[secondaryMeasure] : null;
      const secVal =
        rawSecVal !== null && rawSecVal !== undefined && !isNaN(Number(rawSecVal))
          ? Number(rawSecVal)
          : 0;

      return {
        label: dimVal !== null && dimVal !== undefined ? String(dimVal) : `Row ${idx + 1}`,
        value: measureVal,
        secondaryValue: secVal,
        raw: row,
      };
    });
  }, [results, selectedDimension, selectedMeasure, secondaryMeasure]);

  const maxMeasureVal = useMemo(() => {
    if (chartData.length === 0) return 1;
    const vals = chartData.map((d) => d.value);
    return Math.max(...vals, 1);
  }, [chartData]);

  const totalMeasureVal = useMemo(() => {
    return chartData.reduce((acc, curr) => acc + Math.max(0, curr.value), 0);
  }, [chartData]);

  return (
    <div className="space-y-4">
      {/* Chart Configuration Controls Bar */}
      <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-4 text-xs">
        {/* Chart Type Picker */}
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-600 whitespace-nowrap">
            Chart Type:
          </span>
          <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5">
            {(['bar', 'line', 'donut', 'scatter', 'kpi'] as SupportedChartType[]).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => setSelectedChartType(t)}
                className={`px-2.5 py-1 rounded text-[11px] font-medium transition-colors cursor-pointer capitalize flex items-center gap-1 ${
                  selectedChartType === t
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                {t === 'bar' && <BarChart3 className="w-3 h-3" />}
                {t === 'line' && <LineChart className="w-3 h-3" />}
                {t === 'donut' && <PieChart className="w-3 h-3" />}
                {t === 'scatter' && <Activity className="w-3 h-3" />}
                {t === 'kpi' && <TrendingUp className="w-3 h-3" />}
                <span>{t}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Dynamic Column / Axis Mappers */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Dimension / Grouping Selector */}
          {selectedChartType !== 'kpi' && (
            <div className="flex items-center gap-1.5">
              <label className="text-slate-500 font-medium">Category / X-Axis:</label>
              <select
                value={selectedDimension}
                onChange={(e) => setSelectedDimension(e.target.value)}
                className="bg-white border border-slate-300 rounded-md px-2 py-1 text-xs font-mono font-medium text-slate-800 outline-none focus:border-indigo-500 max-w-[160px] truncate"
              >
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c} {recommendation.columnProfiles[c]?.isIdentifier ? '(ID)' : ''}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Primary Measure Selector */}
          {hasMeasures ? (
            <div className="flex items-center gap-1.5">
              <label className="text-slate-500 font-medium">
                {selectedChartType === 'scatter' ? 'Y-Axis Measure:' : 'Measure / Metric:'}
              </label>
              <select
                value={selectedMeasure}
                onChange={(e) => setSelectedMeasure(e.target.value)}
                className="bg-white border border-slate-300 rounded-md px-2 py-1 text-xs font-mono font-bold text-indigo-700 outline-none focus:border-indigo-500 max-w-[160px] truncate"
              >
                {recommendation.availableMeasures.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <span className="text-[11px] text-slate-400 italic">
              (No aggregated measure in results)
            </span>
          )}

          {/* Secondary Measure for Scatter */}
          {selectedChartType === 'scatter' && recommendation.availableMeasures.length > 1 && (
            <div className="flex items-center gap-1.5">
              <label className="text-slate-500 font-medium">X-Axis Measure:</label>
              <select
                value={secondaryMeasure}
                onChange={(e) => setSecondaryMeasure(e.target.value)}
                className="bg-white border border-slate-300 rounded-md px-2 py-1 text-xs font-mono text-slate-800 outline-none focus:border-indigo-500 max-w-[160px] truncate"
              >
                {recommendation.availableMeasures.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </div>

      {/* Actual Chart Renders */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-xs min-h-[300px] flex flex-col justify-center">
        {/* Fallback if no numeric measures exist for charting */}
        {!hasMeasures && selectedChartType !== 'kpi' ? (
          <div className="text-center py-10 space-y-2">
            <Info className="w-8 h-8 text-slate-400 mx-auto" />
            <h4 className="text-sm font-bold text-slate-800">
              Cannot render meaningful chart without a numeric metric
            </h4>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              The current query returned individual records without aggregated measures.
              To compare data with a chart, switch to Table view or run a follow-up query with aggregations like SUM, AVG, or COUNT.
            </p>
            {onSwitchToTable && (
              <button
                type="button"
                onClick={onSwitchToTable}
                className="mt-2 px-4 py-1.5 rounded-lg bg-indigo-600 text-white font-medium text-xs hover:bg-indigo-700 transition-colors cursor-pointer"
              >
                Back to Table View
              </button>
            )}
          </div>
        ) : selectedChartType === 'kpi' ? (
          /* KPI Card View */
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4 py-4">
            {columns
              .filter((c) => typeof results[0]?.[c] === 'number' || columns.length <= 3)
              .slice(0, 4)
              .map((col) => (
                <div
                  key={col}
                  className="p-5 rounded-xl bg-gradient-to-br from-slate-50 to-indigo-50/30 border border-slate-200 shadow-xs space-y-1"
                >
                  <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider block">
                    {col}
                  </span>
                  <div className="text-3xl font-black font-mono text-indigo-700">
                    {typeof results[0]?.[col] === 'number'
                      ? results[0][col].toLocaleString()
                      : String(results[0]?.[col] ?? '—')}
                  </div>
                  <span className="text-[10px] text-slate-400 block">
                    Single summary measure from analytical query
                  </span>
                </div>
              ))}
          </div>
        ) : selectedChartType === 'bar' ? (
          /* Bar Chart View */
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-500 pb-2 border-b border-slate-100">
              <span className="font-semibold text-slate-700">
                Comparing {selectedMeasure} by {selectedDimension}
              </span>
              <span className="font-mono text-slate-400">
                Showing top {chartData.length} records
              </span>
            </div>

            <div className="space-y-3 pt-2">
              {chartData.map((d, idx) => {
                const pct = Math.min(100, Math.round((Math.max(0, d.value) / maxMeasureVal) * 100));
                return (
                  <div key={idx} className="space-y-1">
                    <div className="flex justify-between text-xs">
                      <span className="font-semibold text-slate-700 truncate max-w-xs">
                        {d.label}
                      </span>
                      <span className="font-mono text-indigo-700 font-bold">
                        {d.value.toLocaleString()}
                      </span>
                    </div>
                    <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden">
                      <div
                        className="bg-indigo-600 h-2.5 rounded-full transition-all duration-300"
                        style={{
                          width: `${pct}%`,
                          backgroundColor: PALETTE[idx % PALETTE.length],
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : selectedChartType === 'line' ? (
          /* Line Chart View */
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-500 pb-2 border-b border-slate-100">
              <span className="font-semibold text-slate-700">
                Trend of {selectedMeasure} across {selectedDimension}
              </span>
              <span className="font-mono text-slate-400">{chartData.length} intervals</span>
            </div>

            <div className="w-full h-64 relative pt-4">
              <svg className="w-full h-full overflow-visible" viewBox="0 0 500 200">
                {/* Horizontal grid lines */}
                <line x1="0" y1="20" x2="500" y2="20" stroke="#f1f5f9" strokeWidth="1" />
                <line x1="0" y1="70" x2="500" y2="70" stroke="#f1f5f9" strokeWidth="1" />
                <line x1="0" y1="120" x2="500" y2="120" stroke="#f1f5f9" strokeWidth="1" />
                <line x1="0" y1="170" x2="500" y2="170" stroke="#cbd5e1" strokeWidth="1" />

                {/* Polyline */}
                {chartData.length > 1 && (
                  <polyline
                    fill="none"
                    stroke="#4f46e5"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    points={chartData
                      .map((d, i) => {
                        const x = (i / (chartData.length - 1)) * 480 + 10;
                        const y = 170 - (d.value / maxMeasureVal) * 140;
                        return `${x},${isNaN(y) ? 170 : y}`;
                      })
                      .join(' ')}
                  />
                )}

                {/* Data Points */}
                {chartData.map((d, i) => {
                  const x = (i / Math.max(1, chartData.length - 1)) * 480 + 10;
                  const y = 170 - (d.value / maxMeasureVal) * 140;
                  return (
                    <circle
                      key={i}
                      cx={x}
                      cy={isNaN(y) ? 170 : y}
                      r="4"
                      className="fill-indigo-600 stroke-white stroke-2 hover:r-6 cursor-pointer"
                    >
                      <title>{`${d.label}: ${d.value}`}</title>
                    </circle>
                  );
                })}
              </svg>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-100">
              <span>{chartData[0]?.label}</span>
              <span>{chartData[chartData.length - 1]?.label}</span>
            </div>
          </div>
        ) : selectedChartType === 'donut' ? (
          /* Donut / Pie View */
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-500 pb-2 border-b border-slate-100">
              <span className="font-semibold text-slate-700">
                Share of {selectedMeasure} by {selectedDimension}
              </span>
              <span className="font-mono text-slate-400">{chartData.length} categories</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-center py-4">
              {/* Donut SVG */}
              <div className="relative w-48 h-48 mx-auto">
                <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100">
                  {chartData.map((item, idx) => {
                    const r = 38;
                    const cx = 50;
                    const cy = 50;
                    const circumference = 2 * Math.PI * r;
                    const safeTotal = totalMeasureVal > 0 ? totalMeasureVal : 1;
                    const fraction = Math.max(0, item.value) / safeTotal;
                    const strokeDasharray = `${fraction * circumference} ${circumference}`;

                    // Compute accumulated angle
                    const prevSum = chartData
                      .slice(0, idx)
                      .reduce((acc, curr) => acc + Math.max(0, curr.value), 0);
                    const startAngle = (prevSum / safeTotal) * 360;
                    const strokeDashoffset = -((startAngle / 360) * (2 * Math.PI * r));

                    return (
                      <circle
                        key={idx}
                        cx={cx}
                        cy={cy}
                        r={r}
                        fill="transparent"
                        stroke={PALETTE[idx % PALETTE.length]}
                        strokeWidth="24"
                        strokeDasharray={strokeDasharray}
                        strokeDashoffset={strokeDashoffset}
                      />
                    );
                  })}
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                  <span className="text-[10px] uppercase font-semibold text-slate-400">Total</span>
                  <span className="text-base font-black font-mono text-slate-800">
                    {totalMeasureVal.toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Segments Legend */}
              <div className="space-y-2">
                {chartData.slice(0, 8).map((item, idx) => {
                  const pct =
                    totalMeasureVal > 0
                      ? Math.round((Math.max(0, item.value) / totalMeasureVal) * 100)
                      : 0;
                  return (
                    <div key={idx} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2 truncate max-w-[180px]">
                        <span
                          className="w-2.5 h-2.5 rounded-full shrink-0"
                          style={{ backgroundColor: PALETTE[idx % PALETTE.length] }}
                        />
                        <span className="text-slate-700 truncate">{item.label}</span>
                      </div>
                      <div className="flex items-center gap-2 font-mono text-slate-600">
                        <span>{item.value.toLocaleString()}</span>
                        <span className="text-[11px] font-bold text-slate-400">({pct}%)</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ) : (
          /* Scatter Plot View */
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-slate-500 pb-2 border-b border-slate-100">
              <span className="font-semibold text-slate-700">
                Scatter Correlation: {secondaryMeasure} (X) vs. {selectedMeasure} (Y)
              </span>
              <span className="font-mono text-slate-400">{chartData.length} data points</span>
            </div>

            <div className="w-full h-64 relative pt-4">
              <svg className="w-full h-full overflow-visible" viewBox="0 0 500 200">
                <line x1="40" y1="20" x2="480" y2="20" stroke="#f1f5f9" strokeWidth="1" />
                <line x1="40" y1="100" x2="480" y2="100" stroke="#f1f5f9" strokeWidth="1" />
                <line x1="40" y1="180" x2="480" y2="180" stroke="#cbd5e1" strokeWidth="1.5" />
                <line x1="40" y1="20" x2="40" y2="180" stroke="#cbd5e1" strokeWidth="1.5" />

                {chartData.map((d, i) => {
                  const maxSec = Math.max(...chartData.map((x) => x.secondaryValue), 1);
                  const x = 40 + (d.secondaryValue / maxSec) * 430;
                  const y = 180 - (d.value / maxMeasureVal) * 150;
                  return (
                    <circle
                      key={i}
                      cx={x}
                      cy={y}
                      r="4.5"
                      fill="#4f46e5"
                      fillOpacity="0.7"
                      stroke="#312e81"
                      strokeWidth="1"
                    />
                  );
                })}
              </svg>
            </div>

            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-100">
              <span>X: {secondaryMeasure}</span>
              <span>Y: {selectedMeasure}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export interface QueryVisualizerProps {
  results: Record<string, any>[];
  columns: string[];
  recommendation: VisualizationRecommendation;
  viewMode: 'table' | 'chart';
  onViewModeChange: (mode: 'table' | 'chart') => void;
  onSetPrompt?: (newPrompt: string) => void;
}

export const QueryVisualizer: React.FC<QueryVisualizerProps> = ({
  results,
  columns,
  recommendation,
  viewMode,
  onViewModeChange,
  onSetPrompt,
}) => {
  return (
    <div className="space-y-4">
      <RecommendationBanner
        recommendation={recommendation}
        viewMode={viewMode}
        onApplyRecommendation={(type) => {
          if (type === 'table') {
            onViewModeChange('table');
          } else {
            onViewModeChange('chart');
          }
        }}
        onSetPrompt={onSetPrompt}
      />
      {viewMode === 'chart' && (
        <QueryChart
          results={results}
          columns={columns}
          recommendation={recommendation}
          onSetPrompt={onSetPrompt}
          onSwitchToTable={() => onViewModeChange('table')}
        />
      )}
    </div>
  );
};
