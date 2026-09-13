"use client";

import React, { useState, useMemo } from "react";
import { CandleBar } from "@/lib/types";

interface InteractiveCandleChartProps {
  bars: CandleBar[];
  selectedRange: string;
  onRangeChange: (range: string) => void;
  loading?: boolean;
}

export default function InteractiveCandleChart({
  bars,
  selectedRange,
  onRangeChange,
  loading = false,
}: InteractiveCandleChartProps) {
  // Indicator Toggles
  const [showSMA20, setShowSMA20] = useState(true);
  const [showSMA50, setShowSMA50] = useState(true);
  const [showBB, setShowBB] = useState(false);
  const [subPane, setSubPane] = useState<"RSI" | "MACD" | "ATR" | "NONE">("RSI");

  // Hover state for tooltip & synchronized crosshair
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const ranges = ["1W", "1M", "3M", "6M", "1Y"];

  // SVG Dimensions
  const width = 800;
  const priceHeight = 320;
  const subHeight = subPane !== "NONE" ? 110 : 0;
  const totalHeight = priceHeight + subHeight + 35; // +35 for x-axis dates

  const padding = { top: 20, right: 65, bottom: 25, left: 15 };
  const innerWidth = width - padding.left - padding.right;
  const slotWidth = innerWidth / Math.max(1, bars.length);

  // Compute price domain
  const { minPrice, maxPrice, barWidth } = useMemo(() => {
    if (!bars || bars.length === 0) {
      return { minPrice: 0, maxPrice: 100, barWidth: 6 };
    }

    let min = Infinity;
    let max = -Infinity;

    bars.forEach((b) => {
      if (b.low < min) min = b.low;
      if (b.high > max) max = b.high;
      if (showSMA20 && b.sma_20 && b.sma_20 < min) min = b.sma_20;
      if (showSMA20 && b.sma_20 && b.sma_20 > max) max = b.sma_20;
      if (showSMA50 && b.sma_50 && b.sma_50 < min) min = b.sma_50;
      if (showSMA50 && b.sma_50 && b.sma_50 > max) max = b.sma_50;
      if (showBB && b.bb_lower && b.bb_lower < min) min = b.bb_lower;
      if (showBB && b.bb_upper && b.bb_upper > max) max = b.bb_upper;
    });

    const priceBuffer = (max - min) * 0.05 || 1.0;
    const bWidth =
      bars.length <= 10
        ? Math.min(26, Math.max(14, slotWidth * 0.22))
        : Math.max(2, Math.min(18, slotWidth * 0.7));

    return {
      minPrice: Math.max(0.01, min - priceBuffer),
      maxPrice: max + priceBuffer,
      barWidth: bWidth,
    };
  }, [bars, showSMA20, showSMA50, showBB, slotWidth]);

  // Coordinate projection helpers
  const getX = (index: number) => {
    return padding.left + (index + 0.5) * slotWidth;
  };

  const getY = (price: number) => {
    const ratio = (price - minPrice) / (maxPrice - minPrice || 1);
    return padding.top + (priceHeight - padding.top - padding.bottom) * (1 - ratio);
  };

  // Sub-pane projection
  const getSubY = (val: number, minVal: number, maxVal: number) => {
    const subTop = priceHeight + 10;
    const subInnerHeight = subHeight - 20;
    const ratio = (val - minVal) / (maxVal - minVal || 1);
    return subTop + subInnerHeight * (1 - ratio);
  };

  const hoveredBar = hoverIndex !== null && bars[hoverIndex] ? bars[hoverIndex] : bars[bars.length - 1];

  // Helper paths for line overlays
  const createLinePath = (getter: (b: CandleBar) => number | null | undefined) => {
    let d = "";
    bars.forEach((b, idx) => {
      const val = getter(b);
      if (val !== null && val !== undefined) {
        const x = getX(idx);
        const y = getY(val);
        d += d === "" ? `M ${x} ${y}` : ` L ${x} ${y}`;
      }
    });
    return d;
  };

  // Price ticks
  const priceTicks = useMemo(() => {
    const count = 5;
    const step = (maxPrice - minPrice) / (count - 1);
    return Array.from({ length: count }, (_, i) => minPrice + i * step);
  }, [minPrice, maxPrice]);

  return (
    <div className="bg-surface border border-surfaceBorder rounded-2xl p-4 sm:p-6 space-y-4">
      {/* Top Header: Indicator Controls & Range Selector */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surfaceBorder pb-4">
        {/* Indicators Toolbar */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-400 font-bold ml-1">المؤشرات:</span>
          
          <button
            type="button"
            onClick={() => setShowSMA20(!showSMA20)}
            className={`px-2.5 py-1 rounded-md border font-mono transition-all ${
              showSMA20
                ? "bg-amber-500/20 border-amber-500/50 text-amber-300 font-bold"
                : "bg-surfaceHover border-surfaceBorder text-gray-400"
            }`}
          >
            SMA 20
          </button>

          <button
            type="button"
            onClick={() => setShowSMA50(!showSMA50)}
            className={`px-2.5 py-1 rounded-md border font-mono transition-all ${
              showSMA50
                ? "bg-blue-500/20 border-blue-500/50 text-blue-300 font-bold"
                : "bg-surfaceHover border-surfaceBorder text-gray-400"
            }`}
          >
            SMA 50
          </button>

          <button
            type="button"
            onClick={() => setShowBB(!showBB)}
            className={`px-2.5 py-1 rounded-md border font-mono transition-all ${
              showBB
                ? "bg-purple-500/20 border-purple-500/50 text-purple-300 font-bold"
                : "bg-surfaceHover border-surfaceBorder text-gray-400"
            }`}
          >
            Bollinger (20,2)
          </button>

          <div className="h-4 w-px bg-surfaceBorder mx-1" />

          {/* Sub-pane selector */}
          <span className="text-gray-400 font-bold ml-1">النافذة السفلية:</span>
          {(["RSI", "MACD", "ATR", "NONE"] as const).map((pane) => (
            <button
              key={pane}
              type="button"
              onClick={() => setSubPane(pane)}
              className={`px-2 py-1 rounded-md border font-mono text-[11px] transition-all ${
                subPane === pane
                  ? "bg-primary text-background font-bold border-primary"
                  : "bg-surfaceHover border-surfaceBorder text-gray-400 hover:text-white"
              }`}
            >
              {pane === "NONE" ? "إخفاء" : pane}
            </button>
          ))}
        </div>

        {/* Range Buttons (1W, 1M, 3M, 6M, 1Y) */}
        <div className="flex items-center gap-1 bg-surfaceHover p-1 rounded-lg border border-surfaceBorder">
          {ranges.map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => onRangeChange(r)}
              className={`px-3 py-1 rounded text-xs font-bold font-mono transition-all ${
                selectedRange === r
                  ? "bg-primary text-background shadow"
                  : "text-gray-400 hover:text-white"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {/* Synchronized Inspection Tooltip Bar */}
      {hoveredBar && (
        <div className="bg-surfaceHover/80 border border-surfaceBorder rounded-lg px-3 py-2 text-xs flex flex-wrap items-center gap-4 text-gray-300">
          <div>
            <span className="text-gray-500 ml-1">التاريخ:</span>
            <span className="font-mono text-white num-ltr">{hoveredBar.session_date}</span>
          </div>
          <div>
            <span className="text-gray-500 ml-1">افتتاح:</span>
            <span className="font-mono text-white num-ltr">{hoveredBar.open.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-gray-500 ml-1">أعلى:</span>
            <span className="font-mono text-emerald-400 num-ltr">{hoveredBar.high.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-gray-500 ml-1">أدنى:</span>
            <span className="font-mono text-rose-400 num-ltr">{hoveredBar.low.toFixed(2)}</span>
          </div>
          <div>
            <span className="text-gray-500 ml-1">إغلاق:</span>
            <span className="font-mono font-bold text-white num-ltr">{hoveredBar.close.toFixed(2)} ج.م</span>
          </div>
          <div>
            <span className="text-gray-500 ml-1">الحجم:</span>
            <span className="font-mono text-gray-300 num-ltr">{hoveredBar.volume.toLocaleString()}</span>
          </div>
          {hoveredBar.sma_20 && (
            <div className="text-amber-400 font-mono">
              SMA20: {hoveredBar.sma_20.toFixed(2)}
            </div>
          )}
          {hoveredBar.sma_50 && (
            <div className="text-blue-400 font-mono">
              SMA50: {hoveredBar.sma_50.toFixed(2)}
            </div>
          )}
          {subPane === "RSI" && hoveredBar.rsi_14 !== null && hoveredBar.rsi_14 !== undefined && (
            <div className="text-purple-400 font-mono">
              RSI14: {hoveredBar.rsi_14.toFixed(1)}
            </div>
          )}
        </div>
      )}

      {/* Interactive Candlestick SVG */}
      <div className="relative w-full overflow-hidden">
        {loading && (
          <div className="absolute inset-0 bg-background/60 backdrop-blur-xs flex items-center justify-center z-20 text-xs text-gray-300">
            جاري تحديث بيانات الرسم البياني...
          </div>
        )}

        <svg
          viewBox={`0 0 ${width} ${totalHeight}`}
          className="w-full h-auto select-none overflow-visible"
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* Price Grid Lines */}
          {priceTicks.map((pt, i) => {
            const y = getY(pt);
            return (
              <g key={i}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={width - padding.right}
                  y2={y}
                  stroke="#1F2937"
                  strokeDasharray="3 3"
                />
                <text
                  x={width - padding.right + 8}
                  y={y + 4}
                  fill="#9CA3AF"
                  fontSize="10"
                  fontFamily="monospace"
                >
                  {pt.toFixed(2)}
                </text>
              </g>
            );
          })}

          {/* Bollinger Bands Shaded Area & Lines */}
          {showBB && (
            <>
              <path
                d={createLinePath((b) => b.bb_upper)}
                fill="none"
                stroke="#A855F7"
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.7"
              />
              <path
                d={createLinePath((b) => b.bb_lower)}
                fill="none"
                stroke="#A855F7"
                strokeWidth="1"
                strokeDasharray="2 2"
                opacity="0.7"
              />
            </>
          )}

          {/* SMA 20 Overlay */}
          {showSMA20 && (
            <path
              d={createLinePath((b) => b.sma_20)}
              fill="none"
              stroke="#F59E0B"
              strokeWidth="1.5"
            />
          )}

          {/* SMA 50 Overlay */}
          {showSMA50 && (
            <path
              d={createLinePath((b) => b.sma_50)}
              fill="none"
              stroke="#3B82F6"
              strokeWidth="1.5"
            />
          )}

          {/* Candlesticks Rendering */}
          {bars.map((bar, idx) => {
            const x = getX(idx);
            const isUp = bar.close >= bar.open;
            const color = isUp ? "#10B981" : "#EF4444";

            const yHigh = getY(bar.high);
            const yLow = getY(bar.low);
            const yOpen = getY(bar.open);
            const yClose = getY(bar.close);

            const candleTop = Math.min(yOpen, yClose);
            const candleHeight = Math.max(1.5, Math.abs(yClose - yOpen));

            return (
              <g
                key={idx}
                onMouseEnter={() => setHoverIndex(idx)}
                className="cursor-crosshair"
              >
                {/* Full column hit-box for instant responsive hover */}
                <rect
                  x={padding.left + idx * slotWidth}
                  y={padding.top}
                  width={slotWidth}
                  height={priceHeight + subHeight - padding.top}
                  fill="transparent"
                  className="pointer-events-auto"
                />
                {/* Wick */}
                <line
                  x1={x}
                  y1={yHigh}
                  x2={x}
                  y2={yLow}
                  stroke={color}
                  strokeWidth={bars.length <= 10 ? "1.5" : "1"}
                />
                {/* Body */}
                <rect
                  x={x - barWidth / 2}
                  y={candleTop}
                  width={barWidth}
                  height={candleHeight}
                  fill={color}
                  rx="0.5"
                />
              </g>
            );
          })}

          {/* Sub-Pane: RSI, MACD, or ATR */}
          {subPane !== "NONE" && (
            <g transform={`translate(0, 0)`}>
              {/* Divider line */}
              <line
                x1={padding.left}
                y1={priceHeight}
                x2={width - padding.right}
                y2={priceHeight}
                stroke="#374151"
                strokeWidth="1"
              />

              {subPane === "RSI" && (
                <>
                  {/* RSI bounds 70 & 30 */}
                  <line
                    x1={padding.left}
                    y1={getSubY(70, 0, 100)}
                    x2={width - padding.right}
                    y2={getSubY(70, 0, 100)}
                    stroke="#4B5563"
                    strokeDasharray="2 2"
                  />
                  <line
                    x1={padding.left}
                    y1={getSubY(30, 0, 100)}
                    x2={width - padding.right}
                    y2={getSubY(30, 0, 100)}
                    stroke="#4B5563"
                    strokeDasharray="2 2"
                  />
                  <text
                    x={width - padding.right + 8}
                    y={getSubY(70, 0, 100) + 3}
                    fill="#9CA3AF"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    70
                  </text>
                  <text
                    x={width - padding.right + 8}
                    y={getSubY(30, 0, 100) + 3}
                    fill="#9CA3AF"
                    fontSize="9"
                    fontFamily="monospace"
                  >
                    30
                  </text>

                  {/* RSI Curve */}
                  <path
                    d={(() => {
                      let d = "";
                      bars.forEach((b, idx) => {
                        if (b.rsi_14 !== null && b.rsi_14 !== undefined) {
                          const x = getX(idx);
                          const y = getSubY(b.rsi_14, 0, 100);
                          d += d === "" ? `M ${x} ${y}` : ` L ${x} ${y}`;
                        }
                      });
                      return d;
                    })()}
                    fill="none"
                    stroke="#C084FC"
                    strokeWidth="1.5"
                  />
                </>
              )}

              {subPane === "MACD" && (
                <>
                  {/* MACD Zero Line */}
                  <line
                    x1={padding.left}
                    y1={getSubY(0, -3, 3)}
                    x2={width - padding.right}
                    y2={getSubY(0, -3, 3)}
                    stroke="#4B5563"
                    strokeDasharray="2 2"
                  />
                  {/* MACD Hist bars */}
                  {bars.map((b, idx) => {
                    if (b.macd_hist === null || b.macd_hist === undefined) return null;
                    const x = getX(idx);
                    const zeroY = getSubY(0, -3, 3);
                    const valY = getSubY(b.macd_hist, -3, 3);
                    const h = Math.abs(valY - zeroY);
                    const y = b.macd_hist >= 0 ? valY : zeroY;
                    const col = b.macd_hist >= 0 ? "#10B981" : "#EF4444";
                    return (
                      <rect
                        key={idx}
                        x={x - barWidth / 2}
                        y={y}
                        width={barWidth}
                        height={Math.max(1, h)}
                        fill={col}
                        opacity="0.8"
                      />
                    );
                  })}
                </>
              )}

              {subPane === "ATR" && (
                <path
                  d={(() => {
                    const atrs = bars.map((b) => b.atr_14).filter((v): v is number => v !== null && v !== undefined);
                    const minA = Math.min(...atrs, 0);
                    const maxA = Math.max(...atrs, 5);
                    let d = "";
                    bars.forEach((b, idx) => {
                      if (b.atr_14 !== null && b.atr_14 !== undefined) {
                        const x = getX(idx);
                        const y = getSubY(b.atr_14, minA, maxA);
                        d += d === "" ? `M ${x} ${y}` : ` L ${x} ${y}`;
                      }
                    });
                    return d;
                  })()}
                  fill="none"
                  stroke="#F59E0B"
                  strokeWidth="1.5"
                />
              )}
            </g>
          )}

          {/* Synchronized Crosshair on Hover */}
          {hoverIndex !== null && (
            <g className="pointer-events-none">
              <line
                x1={getX(hoverIndex)}
                y1={padding.top}
                x2={getX(hoverIndex)}
                y2={priceHeight + subHeight}
                stroke="#6B7280"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
              <line
                x1={padding.left}
                y1={getY(bars[hoverIndex].close)}
                x2={width - padding.right}
                y2={getY(bars[hoverIndex].close)}
                stroke="#6B7280"
                strokeWidth="1"
                strokeDasharray="3 3"
              />
            </g>
          )}

          {/* Date Ticks on X Axis */}
          {bars.length > 0 && (
            <g className="text-[10px]" fontFamily="monospace">
              {bars.length <= 5 ? (
                bars.map((b, idx) => (
                  <text
                    key={idx}
                    x={getX(idx)}
                    y={totalHeight - 5}
                    textAnchor="middle"
                    fill={hoverIndex === idx ? "#38BDF8" : "#9CA3AF"}
                    fontWeight={hoverIndex === idx ? "bold" : "normal"}
                  >
                    {b.session_date}
                  </text>
                ))
              ) : (
                <>
                  <text x={getX(0)} y={totalHeight - 5} textAnchor="start" fill="#9CA3AF">
                    {bars[0].session_date}
                  </text>
                  {bars.length > 2 && (
                    <text x={getX(Math.floor(bars.length / 2))} y={totalHeight - 5} textAnchor="middle" fill="#9CA3AF">
                      {bars[Math.floor(bars.length / 2)].session_date}
                    </text>
                  )}
                  <text x={getX(bars.length - 1)} y={totalHeight - 5} textAnchor="end" fill="#9CA3AF">
                    {bars[bars.length - 1].session_date}
                  </text>
                </>
              )}
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}