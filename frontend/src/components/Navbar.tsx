"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { TrendingUp, BarChart3, Clock, Compass } from "lucide-react";
import { getMarketStatus } from "@/lib/api";
import { MarketStatus } from "@/lib/types";

export default function Navbar() {
  const pathname = usePathname();
  const [marketStatus, setMarketStatus] = useState<MarketStatus | null>(null);

  useEffect(() => {
    getMarketStatus()
      .then(setMarketStatus)
      .catch(() => null);
  }, []);

  const navLinks = [
    { href: "/", label: "اليوم", icon: Clock },
    { href: "/stocks", label: "الأسهم", icon: Compass },
    { href: "/live-analysis", label: "تحليل السعر الحالي", icon: TrendingUp },
  ];

  return (
    <header className="bg-surface/95 backdrop-blur sticky top-0 z-50 border-b border-surfaceBorder">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Platform Name */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-primary/10 border border-primary/30 flex items-center justify-center text-primary font-bold">
              EGX
            </div>
            <div>
              <Link href="/" className="text-lg font-bold text-white hover:text-primary transition-colors">
                البورصة المصرية | <span className="text-primary font-medium">التحليل الفني</span>
              </Link>
              <p className="text-[11px] text-gray-400">منصة دعم القرار الفني لأسهم EGX</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1 sm:gap-2">
            {navLinks.map((link) => {
              const Icon = link.icon;
              const isActive = pathname === link.href;
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-primary text-background font-bold shadow-sm"
                      : "text-gray-300 hover:text-white hover:bg-surfaceHover"
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{link.label}</span>
                </Link>
              );
            })}
          </nav>

          {/* Dynamic Market Status Pill */}
          <div className="hidden md:flex items-center gap-2 text-xs">
            {marketStatus ? (
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-surfaceHover border border-surfaceBorder">
                <span
                  className={`w-2 h-2 rounded-full ${
                    marketStatus.is_open_now ? "bg-primary animate-pulse" : "bg-gray-500"
                  }`}
                />
                <span className="text-gray-300">
                  {marketStatus.is_open_now ? "السوق مفتوح" : "السوق مغلق"}
                </span>
                <span className="text-gray-500">|</span>
                <span className="text-gray-400 num-ltr text-[11px]">
                  جلسة {marketStatus.expected_latest_completed_session}
                </span>
              </div>
            ) : (
              <div className="text-gray-500 text-xs">تحميل حالة السوق...</div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}