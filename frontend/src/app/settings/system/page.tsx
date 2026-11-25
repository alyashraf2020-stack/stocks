import Link from "next/link";
import { opsPanel } from "@/lib/operations";

export default function Page() {
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">تثبيت التطبيق والوصول</h1>
    <article className={opsPanel}><h2 className="text-lg font-bold">ثبّته من البوابة الخاصة</h2>
      <p><bdi>Android</bdi> · افتح التطبيق في Chrome واختار «تثبيت التطبيق» من قائمة المتصفح.</p>
      <p><bdi>iPhone / iPad</bdi> · افتحه في Safari، اضغط «مشاركة» ثم «إضافة إلى الشاشة الرئيسية». افتحه من الأيقونة قبل طلب إذن الإشعارات.</p>
      <p><bdi>Windows / Desktop</bdi> · استخدم زر التثبيت في شريط العنوان أو قائمة Chrome أو Edge لو متاح.</p>
      <Link className="inline-flex min-h-11 items-center text-primary underline" href="/settings/devices">جهّز إشعارات الجهاز</Link>
    </article>
    <article className={opsPanel}><h2 className="text-lg font-bold">الخصوصية والجهاز المشترك</h2>
      <p>صفحة الأوفلاين بتعرض حالة الاتصال فقط. الأسعار والحسابات بتحتاج اتصال بالبوابة.</p>
      <p>لإنهاء الوصول على جهاز مشترك، الغِ الجهاز من الإعدادات، واقفل جلسة التصفح الخاصة بالكامل أو امسح بيانات الموقع وتسجيل دخوله من المتصفح.</p>
      <Link className="inline-flex min-h-11 items-center text-primary underline" href="/system">راجع حالة التشغيل</Link>
    </article>
  </section>;
}
