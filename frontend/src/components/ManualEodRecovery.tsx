"use client";

import React, { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { AlertTriangle, CheckCircle2, Database } from "lucide-react";
import { getStockDetail, submitManualEod } from "@/lib/api";
import { Stock } from "@/lib/types";

function cleanTicker(value: string | null): string | null {
  if (!value) return null;
  const ticker = value.trim().toUpperCase();
  return /^[A-Z0-9]{2,10}$/.test(ticker) ? ticker : null;
}

export default function ManualEodRecovery() {
  const searchParams = useSearchParams();
  const ticker = cleanTicker(searchParams.get("ticker"));
  const [stock, setStock] = useState<Stock | null>(null);
  const [open, setOpen] = useState("");
  const [high, setHigh] = useState("");
  const [low, setLow] = useState("");
  const [close, setClose] = useState("");
  const [volume, setVolume] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    setStock(null);
    setError(null);
    setSuccess(null);
    setOpen("");
    setHigh("");
    setLow("");
    setClose("");
    setVolume("");

    if (!ticker) return;
    getStockDetail(ticker)
      .then(setStock)
      .catch(() => setStock(null));
  }, [ticker]);

  if (!ticker || !stock || stock.sessions_behind == null || stock.sessions_behind <= 0) {
    return null;
  }

  const expectedSession = stock.expected_session_date;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!expectedSession) {
      setError("تعذر تحديد تاريخ الجلسة المتوقعة.");
      return;
    }

    const o = Number(open);
    const h = Number(high);
    const l = Number(low);
    const c = Number(close);
    const v = Number(volume);

    if (![o, h, l, c].every((x) => Number.isFinite(x) && x > 0) || !Number.isFinite(v) || v < 0) {
      setError("أدخل قيم Open / High / Low / Close موجبة وحجم تداول صحيح.");
      return;
    }
    if (l > o || l > c || h < o || h < c || h < l) {
      setError("القيم غير منطقية: يجب أن يكون Low أقل من Open وClose، وHigh أعلى منهما.");
      return;
    }

    setSaving(true);
    try {
      const res = await submitManualEod({
        ticker,
        session_date: expectedSession,
        open: o,
        high: h,
        low: l,
        close: c,
        volume: v,
      });
      setSuccess(res.message_ar);
      window.setTimeout(() => window.location.reload(), 900);
    } catch (err: any) {
      setError(err?.message || "تعذر حفظ بيانات الجلسة.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-4xl mx-auto mb-6">
      <div className="bg-amber-500/10 border border-amber-500/30 rounded-2xl p-5 sm:p-6 shadow-xl">
        <div className="flex items-start gap-3 mb-4">
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
          <div className="space-y-1">
            <h2 className="text-sm sm:text-base font-black text-amber-300">المصدر العام متأخر — أدخل شمعة الجلسة المكتملة مرة واحدة</h2>
            <p className="text-xs text-gray-300 leading-relaxed">
              آخر جلسة متاحة تلقائيًا هي <strong className="font-mono num-ltr">{stock.latest_session_date || "—"}</strong>، بينما الجلسة المطلوبة هي <strong className="font-mono num-ltr text-white">{expectedSession || "—"}</strong>. أدخل بيانات OHLCV من تطبيق الوسيط، وبعد الحفظ سيعود التحليل للعمل بدون استخدام السعر اللحظي كإغلاق.
            </p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <label className="space-y-1">
              <span className="text-[11px] text-gray-400">Open</span>
              <input type="number" step="0.01" min="0.01" value={open} onChange={(e) => setOpen(e.target.value)} required className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-gray-400">High</span>
              <input type="number" step="0.01" min="0.01" value={high} onChange={(e) => setHigh(e.target.value)} required className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-gray-400">Low</span>
              <input type="number" step="0.01" min="0.01" value={low} onChange={(e) => setLow(e.target.value)} required className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono" />
            </label>
            <label className="space-y-1">
              <span className="text-[11px] text-gray-400">Close</span>
              <input type="number" step="0.01" min="0.01" value={close} onChange={(e) => setClose(e.target.value)} required className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono" />
            </label>
            <label className="space-y-1 col-span-2 sm:col-span-1">
              <span className="text-[11px] text-gray-400">Volume</span>
              <input type="number" step="1" min="0" value={volume} onChange={(e) => setVolume(e.target.value)} required className="w-full bg-surface border border-surfaceBorder rounded-lg px-3 py-2 text-sm text-white font-mono" />
            </label>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="text-[11px] text-gray-500 flex items-center gap-1.5">
              <Database className="w-3.5 h-3.5" />
              <span>سيُحفظ المصدر باسم USER_VERIFIED_EOD ولن يتم اختلاق أي قيمة.</span>
            </div>
            <button type="submit" disabled={saving} className="bg-amber-400 hover:bg-amber-300 disabled:opacity-50 text-black font-black text-sm px-5 py-2.5 rounded-xl transition-colors">
              {saving ? "جاري التحقق والحفظ..." : "حفظ الجلسة وإعادة التحليل"}
            </button>
          </div>

          {error && <div className="text-xs text-rose-300 bg-rose-500/10 border border-rose-500/30 rounded-lg p-3">{error}</div>}
          {success && <div className="text-xs text-emerald-300 bg-emerald-500/10 border border-emerald-500/30 rounded-lg p-3 flex items-center gap-2"><CheckCircle2 className="w-4 h-4" />{success}</div>}
        </form>
      </div>
    </div>
  );
}
