import Link from "next/link";

export default function ScannerNavigation() {
  return (
    <nav aria-label="المتابعة الآلية" className="flex flex-wrap gap-x-5 gap-y-2 text-sm text-primary">
      <Link href="/scanner" className="underline">ماسح السوق</Link>
      <Link href="/watchlist" className="underline">قائمة المتابعة</Link>
      <Link href="/notifications" className="underline">التنبيهات</Link>
      <Link href="/settings/scanner" className="underline">إعدادات الماسح</Link>
    </nav>
  );
}
