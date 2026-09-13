"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  TrendingUp,
  Compass,
  ShieldCheck,
  Zap,
  ArrowLeft,
  Clock,
  Activity,
  CheckCircle2,
  Building2
} from "lucide-react";
import { getMarketStatus } from "@/lib/api";
import { MarketStatus, Stock } from "@/lib/types";
import StockSearchInput from "@/components/StockSearchInput";

export default function HomePage() {
  const router = useRouter();
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);

  useEffect(() => {
    getMarketStatus()
      .then(setMarketStatus)
      .catch(() => null);
  }, []);

  const handleStockSelect = (stock: Stock) => {
    router.push(`/live-analysis?ticker=${stock.ticker}`);
  };

  return (
    <div className="space-y-10">
      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-b from-surface to-surface/60 border border-surfaceBorder p-8 md:p-12 text-center space-y-6">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-primary/10 border border-primary/20 text-xs font-bold text-primary">
          <Zap className="w-3.5 h-3.5" />
          <span>منصة اتخاذ القرار اللحظي لأسهم البورصة المصرية</span>
        </div>

        <h1 className="text-3xl sm:text-5xl font-black text-white tracking-tight leading-tight max-w-3xl mx-auto">
          تحليل السعر اللحظي وقرار التداول <span className="text-primary">بكل دقة وشفافية</span>
        </h1>

        <p className="text-gray-400 text-sm sm:text-base max-w-2xl mx-auto leading-relaxed">
          قارن السعر اللحظي المباشر من شاشتك مع التحليل الفني المعتمد لنهاية اليوم (EOD) لأسهم البورصة المصرية، مع خطة دخول وخروج دقيقة وإدارة مخاطر صارمة.
        </p>

        {/* Quick Search & Analyze Input */}
        <div className="max-w-xl mx-auto pt-2">
          <StockSearchInput
            onSelect={handleStockSelect}
            placeholder="اختر سهماً مصرياً للتحليل الفوري (مثال: COMI, السويدي, ABUK)..."
          />
        </div>

        {/* CTA Buttons */}
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4">
          <Link
            href="/live-analysis"
            className="flex items-center gap-2 bg-primary hover:bg-primary-hover text-background font-black px-6 py-3 rounded-xl transition-all shadow-lg hover:shadow-primary/20"
          >
            <TrendingUp className="w-5 h-5" />
            <span>حلل سهم الآن (أدخل السعر اللحظي)</span>
          </Link>
          <Link
            href="/stocks"
            className="flex items-center gap-2 bg-surfaceHover hover:bg-surfaceBorder border border-surfaceBorder text-white font-bold px-6 py-3 rounded-xl transition-all"
          >
            <Compass className="w-5 h-5" />
            <span>دليل كل أسهم البورصة</span>
          </Link>
        </div>
      </div>

      {/* Dynamic Market Status Bar */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-surface border border-surfaceBorder rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center text-primary">
            <Activity className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-gray-400 block">حالة السوق اللحظية</span>
            <span className="text-base font-bold text-white">
              {marketStatus ? (marketStatus.is_open_now ? "السوق مفتوح حالياً" : "السوق مغلق") : "—"}
            </span>
          </div>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-accent/10 border border-accent/20 flex items-center justify-center text-accent">
            <Clock className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-gray-400 block">آخر جلسة رسمية مكتملة</span>
            <span className="text-base font-bold text-white num-ltr">
              {marketStatus ? marketStatus.expected_latest_completed_session : "—"}
            </span>
          </div>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400">
            <Building2 className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-gray-400 block">الأسهم المقيدة في البورصة</span>
            <span className="text-base font-bold text-white num-ltr">
              {marketStatus ? marketStatus.total_listed_equities : "176"} سهم
            </span>
          </div>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-2xl p-5 flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
            <ShieldCheck className="w-6 h-6" />
          </div>
          <div>
            <span className="text-xs text-gray-400 block">سياسة انعدام التأخير</span>
            <span className="text-base font-bold text-emerald-400">Zero Session Lag</span>
          </div>
        </div>
      </div>

      {/* 3 Core Value Pillars */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
        <div className="bg-surface border border-surfaceBorder rounded-2xl p-6 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/20 flex items-center justify-center text-primary font-bold">
            01
          </div>
          <h3 className="text-lg font-bold text-white">تحليل السعر اللحظي اليدوي</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            أدخل السعر الحالي للسهم مباشرة من تطبيق الوسيط، وسيقوم النظام بمقارنته مع منطقة الدخول ووقف الخسارة المحددة فنياً لمنحك قراراً واضحاً: أدخل الآن، انتظر، أو لا تدخل.
          </p>
          <Link href="/live-analysis" className="inline-flex items-center gap-1.5 text-xs text-primary font-bold hover:underline">
            <span>ابدأ التحليل اللحظي</span>
            <ArrowLeft className="w-3.5 h-3.5" />
          </Link>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-2xl p-6 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-accent/10 border border-accent/20 flex items-center justify-center text-accent font-bold">
            02
          </div>
          <h3 className="text-lg font-bold text-white">إدارة مخاطر صارمة ومحكمة</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            حساب دقيق لعدد الأسهم بناءً على رأس مالك بحيث لا تتجاوز المخاطرة 1.5% من المحفظة ولا يتجاوز تخصيص السهم 20%، مع 3 أهداف ربحية شفافة بمضاعفات R.
          </p>
          <span className="inline-flex items-center gap-1.5 text-xs text-gray-400">
            <CheckCircle2 className="w-3.5 h-3.5 text-accent" />
            <span>حماية رأس المال أولاً</span>
          </span>
        </div>

        <div className="bg-surface border border-surfaceBorder rounded-2xl p-6 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 font-bold">
            03
          </div>
          <h3 className="text-lg font-bold text-white">بيانات حقيقية خالية من التزييف</h3>
          <p className="text-xs text-gray-400 leading-relaxed">
            المنصة ترفض تماماً تزييف البيانات أو اصطناع شموع وهمية. إن لم تكن بيانات آخر جلسة مكتملة متوفرة، يتوقف النظام بأمان لحمايتك تحت شعار: بيانات غير محدثة.
          </p>
          <Link href="/stocks" className="inline-flex items-center gap-1.5 text-xs text-purple-400 font-bold hover:underline">
            <span>استعرض دليل الأسهم</span>
            <ArrowLeft className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>
    </div>
  );
}