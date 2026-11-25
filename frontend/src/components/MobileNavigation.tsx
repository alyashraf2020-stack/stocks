"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Bell, ChartNoAxesColumnIncreasing, House, Menu, Wallet, X } from "lucide-react";

export const modules = [
  ["/", "الرئيسية"], ["/ai-trading", "مساعد التحليل"], ["/opportunities", "الفرص"],
  ["/stocks", "الأسهم"], ["/plans", "خطط الأسهم"], ["/live-analysis", "تحليل السعر المدخل"],
  ["/portfolio", "محفظة ثاندر"], ["/scanner", "ماسح السوق"], ["/watchlist", "قائمة المتابعة"],
  ["/risk", "إدارة المخاطر"], ["/sharia", "الفحص الشرعي"], ["/paper-trading", "التداول الافتراضي"],
  ["/backtesting", "الاختبار التاريخي"], ["/notifications", "التنبيهات"], ["/data", "جاهزية البيانات"],
  ["/system", "حالة التشغيل"], ["/settings/integrations", "ربط ثاندر"], ["/settings/scanner", "إعدادات الماسح"],
  ["/settings/notifications", "إعدادات التنبيهات"], ["/settings/devices", "الأجهزة"],
  ["/settings/system", "تثبيت التطبيق والوصول"],
];

const main = [
  { href: "/", title: "الرئيسية", icon: House },
  { href: "/opportunities", title: "الفرص", icon: ChartNoAxesColumnIncreasing },
  { href: "/portfolio", title: "المحفظة", icon: Wallet },
  { href: "/notifications", title: "التنبيهات", icon: Bell },
];

export default function MobileNavigation() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [pathname]);
  useEffect(() => {
    const close = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  return <div className="fixed inset-x-0 bottom-0 z-50 md:hidden">
    {open && <div id="mobile-module-list" className="max-h-[64dvh] overflow-y-auto border-t border-surfaceBorder bg-surface p-3 shadow-xl">
      <div className="grid grid-cols-2 gap-2">
        {modules.map(([href, title]) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}
          className="flex min-h-11 items-center rounded-lg bg-surfaceHover px-3 py-2 text-sm text-gray-100"
          onClick={() => setOpen(false)}>{title}</Link>)}
      </div>
    </div>}
    <nav aria-label="القائمة السريعة" className="grid grid-cols-5 border-t border-surfaceBorder bg-surface pb-[env(safe-area-inset-bottom)]">
      {main.map(({href, title, icon: Icon}) => <Link key={href} href={href} aria-current={pathname === href ? "page" : undefined}
        className={"flex min-h-14 flex-col items-center justify-center gap-1 p-1 text-xs " + (pathname === href ? "text-primary" : "text-gray-300")}>
        <Icon size={19} aria-hidden="true"/>{title}
      </Link>)}
      <button aria-expanded={open} aria-controls="mobile-module-list" className="flex min-h-14 flex-col items-center justify-center gap-1 text-xs text-gray-300"
        onClick={() => setOpen((value) => !value)}>
        {open ? <X size={19} aria-hidden="true"/> : <Menu size={19} aria-hidden="true"/>}المزيد
      </button>
    </nav>
  </div>;
}
