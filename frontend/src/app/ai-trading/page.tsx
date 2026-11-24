"use client";

import ScannerNavigation from "@/components/ScannerNavigation";

import { useEffect, useState } from "react";
import Link from "next/link";
import AIStockAnalysis from "@/components/AIStockAnalysis";
import { AIStatus, aiLabels, aiRequest } from "@/lib/ai";

export default function AITradingPage() {
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [error, setError] = useState("");
  const readStatus = () =>
    aiRequest<AIStatus>("status")
      .then((s) => {
        setStatus(s);
        setError("");
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    void readStatus();
  }, []);
  return (
    <section dir="rtl" className="mx-auto max-w-5xl space-y-5">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold">مساعد تحليل البورصة</h1>
      <ScannerNavigation />
        <div className="flex gap-5 text-primary underline">
          <Link href="/opportunities">الفرص للمراجعة</Link>
          <Link href="/portfolio">محفظة ثاندر</Link>
        </div>
      </header>
      <article className="rounded-xl border border-surfaceBorder bg-surface p-5 space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-bold">حالة OpenAI والاستخدام</h2>
          <button
            className="text-primary underline text-sm"
            onClick={readStatus}
          >
            تحديث الاستخدام
          </button>
        </div>
        {error && (
          <p role="alert" className="text-amber-300">
            {error}
          </p>
        )}
        {status && (
          <>
            <p>
              {aiLabels[status.status] ?? status.status} ·{" "}
              <bdi>{status.model}</bdi>
            </p>
            {status.usage && (
              <div className="text-sm text-gray-300">
                <p>
                  تكلفة اليوم التقديرية{" "}
                  <bdi>
                    {status.usage.daily_estimated_usd.toFixed(6)} /{" "}
                    {status.daily_limit_usd} USD
                  </bdi>
                </p>
                <p>
                  تكلفة الشهر التقديرية{" "}
                  <bdi>
                    {status.usage.monthly_estimated_usd.toFixed(6)} /{" "}
                    {status.monthly_limit_usd} USD
                  </bdi>
                </p>
                <p>
                  توكنات الشهر حسب ردود OpenAI ·{" "}
                  {status.usage.monthly_input_tokens} إدخال ·{" "}
                  {status.usage.monthly_output_tokens} إخراج
                </p>
              </div>
            )}
          </>
        )}
      </article>
      <AIStockAnalysis />
    </section>
  );
}
