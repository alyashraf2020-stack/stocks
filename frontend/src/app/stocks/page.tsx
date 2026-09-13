"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Search, Filter, Compass, TrendingUp, CheckCircle2, Clock, AlertCircle } from "lucide-react";
import { getStocks, getSectors } from "@/lib/api";
import { Stock } from "@/lib/types";

export default function StocksDirectoryPage() {
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [sectors, setSectors] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSector, setSelectedSector] = useState("");
  const [selectedIndex, setSelectedIndex] = useState("");

  useEffect(() => {
    getSectors()
      .then(setSectors)
      .catch(() => []);
  }, []);

  useEffect(() => {
    setLoading(true);
    getStocks({
      q: searchQuery,
      sector: selectedSector,
      index_name: selectedIndex,
    })
      .then((res) => {
        setStocks(res.items);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [searchQuery, selectedSector, selectedIndex]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-surfaceBorder pb-6">
        <div>
          <h1 className="text-2xl sm:text-3xl font-black text-white flex items-center gap-3">
            <Compass className="w-8 h-8 text-primary" />
            <span>دليل أسهم البورصة المصرية</span>
          </h1>
          <p className="text-xs sm:text-sm text-gray-400 mt-1">
            جميع الأسهم المقيدة في البورصة المصرية (EGX) مع حالة التحديث والتحليل الفني
          </p>
        </div>

        <div className="text-xs text-gray-400 bg-surface border border-surfaceBorder px-4 py-2 rounded-xl">
          إجمالي الأسهم المقيدة: <span className="font-bold text-white num-ltr font-mono">{stocks.length}</span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {/* Search */}
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="ابحث بالرمز، الاسم بالعربي أو الإنجليزي..."
            className="w-full bg-surface border border-surfaceBorder rounded-xl px-4 py-2.5 pl-10 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-primary"
          />
          <Search className="w-4 h-4 text-gray-400 absolute left-3 top-3.5 pointer-events-none" />
        </div>

        {/* Sector Filter */}
        <div className="relative">
          <select
            value={selectedSector}
            onChange={(e) => setSelectedSector(e.target.value)}
            className="w-full bg-surface border border-surfaceBorder rounded-xl px-4 py-2.5 text-sm text-white appearance-none focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="">جميع القطاعات</option>
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <Filter className="w-4 h-4 text-gray-400 absolute left-3 top-3.5 pointer-events-none" />
        </div>

        {/* Index Filter */}
        <div className="relative">
          <select
            value={selectedIndex}
            onChange={(e) => setSelectedIndex(e.target.value)}
            className="w-full bg-surface border border-surfaceBorder rounded-xl px-4 py-2.5 text-sm text-white appearance-none focus:outline-none focus:border-primary cursor-pointer"
          >
            <option value="">جميع المؤشرات والأسهم</option>
            <option value="EGX30">مؤشر EGX30</option>
            <option value="EGX70">مؤشر EGX70</option>
            <option value="EGX100">مؤشر EGX100</option>
            <option value="تميز">سوق الشركات الصغيرة - تميز</option>
          </select>
          <Filter className="w-4 h-4 text-gray-400 absolute left-3 top-3.5 pointer-events-none" />
        </div>
      </div>

      {/* Stocks Table */}
      <div className="bg-surface border border-surfaceBorder rounded-2xl overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-sm text-gray-400">جاري تحميل أسهم البورصة المصرية...</div>
        ) : stocks.length === 0 ? (
          <div className="p-12 text-center text-sm text-gray-400">لا توجد أسهم مطابقة لمعايير البحث</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-right divide-y divide-surfaceBorder">
              <thead className="bg-surfaceHover/50 text-[11px] font-bold text-gray-400 uppercase">
                <tr>
                  <th className="px-5 py-3.5">الرمز</th>
                  <th className="px-5 py-3.5">اسم الشركة</th>
                  <th className="px-5 py-3.5">القطاع</th>
                  <th className="px-5 py-3.5">آخر إغلاق</th>
                  <th className="px-5 py-3.5">آخر جلسة مسجلة</th>
                  <th className="px-5 py-3.5 text-center">حالة البيانات</th>
                  <th className="px-5 py-3.5 text-center">الإجراءات</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surfaceBorder text-xs text-gray-200">
                {stocks.map((stock) => {
                  const isCurrent = stock.sessions_behind === 0;
                  return (
                    <tr key={stock.ticker} className="hover:bg-surfaceHover transition-colors">
                      {/* Ticker */}
                      <td className="px-5 py-4 font-mono font-black text-white text-sm">
                        <Link href={`/stocks/${stock.ticker}`} className="hover:text-primary transition-colors">
                          {stock.ticker}
                        </Link>
                      </td>

                      {/* Arabic & English Name */}
                      <td className="px-5 py-4">
                        <Link href={`/stocks/${stock.ticker}`} className="font-bold text-white hover:text-primary block">
                          {stock.arabic_name}
                        </Link>
                        <span className="text-[11px] text-gray-400">{stock.english_name}</span>
                      </td>

                      {/* Sector */}
                      <td className="px-5 py-4 text-gray-300">
                        <span className="bg-surfaceHover border border-surfaceBorder px-2.5 py-1 rounded-md text-[11px]">
                          {stock.sector}
                        </span>
                      </td>

                      {/* Latest Close */}
                      <td className="px-5 py-4 font-mono font-bold text-white text-sm num-ltr">
                        {stock.latest_close !== null && stock.latest_close !== undefined
                          ? `${stock.latest_close.toFixed(2)} ج.م`
                          : "—"}
                      </td>

                      {/* Session Date */}
                      <td className="px-5 py-4 font-mono text-gray-400 num-ltr">
                        {stock.latest_session_date || "—"}
                      </td>

                      {/* Freshness Badge */}
                      <td className="px-5 py-4 text-center">
                        {isCurrent ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>محدث</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-amber-500/10 text-amber-400 border border-amber-500/30">
                            <Clock className="w-3.5 h-3.5" />
                            <span>غير محدث</span>
                          </span>
                        )}
                      </td>

                      {/* Actions */}
                      <td className="px-5 py-4 text-center">
                        <div className="flex items-center justify-center gap-2">
                          <Link
                            href={`/stocks/${stock.ticker}`}
                            className="text-xs bg-surfaceHover hover:bg-surfaceBorder text-gray-300 hover:text-white px-3 py-1.5 rounded-lg border border-surfaceBorder transition-all"
                          >
                            التفاصيل والرسم
                          </Link>
                          <Link
                            href={`/live-analysis?ticker=${stock.ticker}`}
                            className="text-xs bg-primary hover:bg-primary-hover text-background font-bold px-3 py-1.5 rounded-lg transition-all flex items-center gap-1"
                          >
                            <TrendingUp className="w-3.5 h-3.5" />
                            <span>تحليل لحظي</span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}