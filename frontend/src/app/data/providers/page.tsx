import { DataLinks } from "@/components/MarketReadiness";
import EodhdSettings from "@/components/EodhdSettings";
import { opsPanel } from "@/lib/operations";

const sources = [
  ["EGX / EGID", "المسار الرسمي لطلب تغطية الأسهم والمؤشرات وإجراءات الشركات وحقوق الاستيراد. السعر وشروط التشغيل حسب العرض.", "https://www.egidegypt.com/"],
  ["DirectFN", "بيانات مصر متأخرة وتغذية تجارية. وثّق التأخير والحق في التخزين وحقول الحزمة قبل الربط.", "https://www.directfn.com.eg/delayed.aspx"],
  ["Mubasher", "صفحات أسعار وإفصاحات للمراجعة. طلب إذن صريح للتصدير والتشغيل الآلي.", "https://english.mubasher.info/markets/EGX/stocks/SWDY/announcements/"],
  ["ICE", "تغذية تاريخية وEOD وبث EGX بمستويي أسعار. منتج يحتاج عقد البيانات.", "https://developer.ice.com/fixed-income-data-services/catalog/egyptian-exchange-egx"],
  ["EODHD", "API رسمي للسلاسل اليومية بالجملة أو CSV حسب الخطة. راجع اكتمال حقول التنفيذ وحقوق التخزين.", "https://eodhd.com/exchange/EGX"],
  ["Thndr MCP", "مسار القراءة المصرح بها. الأسعار والبيانات ممكن تتأخر، ومصدر التنفيذ محتاج حقوق وتغطية مستقلة.", "https://docs.thndr.app/how-it-works"],
  ["EGX.news", "المزوّد يعلن ملفات CSV يومية وداخل الجلسة. اطلب توثيق الترخيص والحقول وتوقيت المصدر قبل التشغيل.", "https://egx.news/en/our-data"],
];
export default function Page() {
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">مزوّدين بيانات البورصة</h1><DataLinks/>
    <p className="text-amber-300">المصادر اللحظية المؤهلة للتنفيذ بتحتاج ترخيص وحقول تحقق مستقلة.</p>
    <EodhdSettings />
    <div className="grid gap-3 sm:grid-cols-2">{sources.map(([name, summary, url]) =>
      <article className={opsPanel} key={name}><h2 className="font-bold"><bdi>{name}</bdi></h2>
        <p className="text-sm">{summary}</p><a className="inline-flex min-h-11 items-center text-primary underline" href={url}
          target="_blank" rel="noopener noreferrer">مستندات المصدر</a>
      </article>)}</div>
  </section>;
}
