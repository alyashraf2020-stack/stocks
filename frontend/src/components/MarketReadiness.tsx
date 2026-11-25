"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { label, numberLabel, ops, opsButton, opsField, opsOutline, opsPanel, timeLabel } from "@/lib/operations";

const link = "inline-flex min-h-11 items-center text-primary underline";
const columns = ["day", "available_at", "open", "high", "low", "close", "volume", "tick", "lower_limit", "upper_limit", "opening_bid", "opening_ask"];
const countNames: Record<string, string> = {
  listed: "أسهم مدرجة", with_history: "لها تاريخ", current: "آخر جلسة موجودة", analysis: "صالحة للتحليل",
  stale: "بيانات قديمة", unavailable: "بيانات غير متاحة", paper: "لها حزم تنفيذ يومية",
  backtest_candidates: "مرشحة لاختبار 200 جلسة", missing_identity: "هوية ناقصة", missing_corporate_actions: "مراجعة إجراءات ناقصة",
};
type Report = {valid: boolean; ticker?: string; isin?: string; source?: string; bars?: number; expected?: number; halted?: number;
  actions?: number; missing?: string[]; source_timestamp?: string; partial?: boolean; error?: string; issues?: {field: string; code: string}[]};
type Receipt = {id: number; dataset_id?: string; status: string; duplicate?: boolean; report: Report; created?: number; channel?: string};
type Readiness = {
  counts: Record<string, number>; completed_session?: string; last_import?: number; source_timestamp?: string;
  calendar: {version: string; coverage: string[]}; benchmarks: {ticker: string; kind: string; bars: number; from: string; through: string}[];
  items: {ticker: string; name: string; latest?: string; source?: string; analysis: boolean; paper_dataset: boolean; reasons: string[]}[];
};
const holders: [string, string, string][] = [
  ["ticker","الرمز","text"], ["isin","ISIN","text"], ["source","اسم المزوّد","text"], ["reference","مرجع الترخيص أو التصدير","text"],
  ["listed_on","تاريخ القيد","date"], ["delisted_on","تاريخ الشطب لو موجود","date"],
  ["first_session","بداية تغطية الحزمة","date"], ["last_session","نهاية تغطية الحزمة","date"],
];

export function DataLinks() {
  return <nav className="flex flex-wrap gap-4 text-sm">
    <Link href="/data" className={link}>الجاهزية</Link><Link href="/data/import" className={link}>استيراد حزمة</Link>
    <Link href="/data/providers" className={link}>المزوّدين</Link>
  </nav>;
}

export function MarketOverview() {
  const [data, setData] = useState<Readiness>();
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("all");
  const [limit, setLimit] = useState(30);
  useEffect(() => { ops<Readiness>("data").then(setData).catch((why: Error) => setError(why.message)); }, []);
  const results = data?.items.filter((item) =>
    (item.ticker.includes(query.toUpperCase()) || item.name.includes(query)) &&
    (kind === "all" || (kind === "blocked" && !!item.reasons.length) || (kind === "approved" && item.paper_dataset))) ?? [];
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">جاهزية بيانات السوق</h1><DataLinks/>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {!data && !error && <p role="status">جاري فحص التغطية…</p>}
    {data && <>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">{Object.entries(data.counts).map(([key, value]) =>
        <div key={key} className={opsPanel}><p className="text-sm text-gray-400">{countNames[key] ?? key}</p>
          <p className="text-xl font-bold">{numberLabel(value)}</p></div>)}</div>
      <article className={opsPanel}>
        <h2 className="font-bold">التقويم ومصدر البيانات</h2>
        <p>آخر جلسة <bdi>{data.completed_session ?? "غير متاحة"}</bdi> · تقويم <bdi>{data.calendar.version}</bdi></p>
        <p className="text-sm text-gray-400">التغطية <bdi>{data.calendar.coverage.join(" — ")}</bdi> · آخر استيراد {timeLabel(data.last_import)}
          {" "}· أحدث توقيت مصدر معتمد {timeLabel(data.source_timestamp)}</p>
        <p className="text-amber-300">مفيش مصدر لحظي مرخّص مفعّل. التغطية التاريخية بتتراجع قبل كل اختبار.</p>
        <p className="text-sm">الشموع الخام بتحتاج فحص صلاحية قبل التحليل. التنفيذ والاختبار محتاجين هوية وحزمة أسعار غير معدّلة ومواعيد إتاحة وحدود تداول وإجراءات شركة مراجَعة.</p>
      </article>
      <article className={opsPanel}><h2 className="font-bold">المؤشرات المرجعية</h2>
        {data.benchmarks.map((row, i) => <p key={i} className="text-sm"><bdi>{row.ticker}</bdi> · {row.bars} شمعة · <bdi>{row.from} — {row.through}</bdi></p>)}
        {!data.benchmarks.length && <p className="text-gray-400">مفيش حزم مؤشرات مرجعية معتمدة.</p>}
      </article>
      <article className={opsPanel}><h2 className="font-bold">التغطية لكل سهم</h2>
        <details><summary className="cursor-pointer">البحث والفلاتر</summary>
          <div className="grid gap-3 pt-3 sm:grid-cols-2">
            <label>ابحث بالرمز أو الاسم<input className={opsField} value={query} onChange={(e) => {setQuery(e.target.value); setLimit(30);}}/></label>
            <label>حالة الحزمة<select className={opsField} value={kind} onChange={(e) => {setKind(e.target.value); setLimit(30);}}>
              <option value="all">كل الأسهم</option><option value="blocked">فيه بيانات مطلوبة</option><option value="approved">حزمة معتمدة</option>
            </select></label>
          </div>
        </details>
        {results.slice(0, limit).map((item) => <div className="border-t border-surfaceBorder py-2 text-sm" key={item.ticker}>
          <p className="font-semibold"><bdi>{item.ticker}</bdi> · {item.name}</p>
          <p>{item.latest ?? "غير متاح"} · {item.source ?? "مصدر غير متاح"} · {item.analysis ? "صالح للتحليل" : "مراجعة البيانات مطلوبة"}</p>
          {!!item.reasons.length && <p className="text-gray-400">{item.reasons.map(label).join(" · ")}</p>}
        </div>)}
        {!results.length && <p className="text-gray-400">مفيش أسهم مطابقة.</p>}
        {results.length > limit && <button className={opsOutline} onClick={() => setLimit((value) => value + 30)}>عرض أكتر</button>}
      </article>
    </>}
  </section>;
}

export function ImportWorkspace() {
  const [format, setFormat] = useState<"CSV" | "JSON">("CSV");
  const [kind, setKind] = useState("EQUITY");
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<Report>();
  const [envelope, setEnvelope] = useState<object>();
  const [records, setRecords] = useState<Receipt[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  function refresh() {return ops<Receipt[]>("data/history").then(setRecords);}
  useEffect(() => { void refresh().catch((why: Error) => setError(why.message)); }, []);
  async function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const file = form.get("file");
    if (!(file instanceof File) || !file.size || file.size > 2_000_000) {
      setError("اختار ملف حجمه أقل من 2 ميجابايت."); return;
    }
    setBusy(true); setError(""); setNotice(""); setEnvelope(undefined); setPreview(undefined);
    try {
      const metadata = format === "CSV" ? {
        ...Object.fromEntries(holders.map(([key]) => [key, String(form.get(key) ?? "").trim() || null])),
        kind, exchange: "EGX", currency: "EGP", basis: kind === "EQUITY" ? "UNADJUSTED" : "INDEX_LEVEL",
        rights_confirmed: form.has("rights_confirmed"), actions_reviewed: form.has("actions_reviewed"),
        actions: JSON.parse(String(form.get("actions") || "[]")), suspended: JSON.parse(String(form.get("suspended") || "[]")),
      } : {};
      const body = {format, content: await file.text(), metadata, mapping: format === "CSV" ? mapping : {}};
      const result = await ops<Report>("data/preview", body);
      setPreview(result);
      if (result.valid) setEnvelope(body);
    } catch (why) {setError((why as Error).message);}
    finally {setBusy(false);}
  }
  async function confirmImport() {
    if (!envelope) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await ops<Receipt>("data/import", envelope);
      setPreview(result.report); setNotice(label(result.status)); setEnvelope(undefined);
      await refresh();
    } catch (why) {setError((why as Error).message);}
    finally {setBusy(false);}
  }
  return <section dir="rtl" className="space-y-5">
    <h1 className="text-3xl font-bold">استيراد جلسات مصرح بيها</h1><DataLinks/>
    {error && <p role="alert" className="text-amber-300">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <form className={opsPanel} onSubmit={review} onChange={() => {setEnvelope(undefined); setPreview(undefined);}}>
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-semibold">اختار ملف المزوّد</h2>
        <a className={link} href="/api/v1/data/template.csv">نزّل قالب CSV</a></div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1">الصيغة<select className={opsField} value={format} onChange={(event) => setFormat(event.target.value as "CSV" | "JSON")}>
          <option>CSV</option><option>JSON</option></select></label>
        <label className="space-y-1">الملف<input required type="file" name="file" accept={format === "CSV" ? ".csv,text/csv" : ".json,application/json"} className={opsField}/></label>
      </div>
      {format === "JSON" && <p className="text-sm text-gray-400">استخدم صيغة DatasetUpload من التوثيق الخاص. الملف لازم يضم بيانات الحق في الاستخدام وإجراءات الشركة.</p>}
      {format === "CSV" && <>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label>نوع الأداة<select className={opsField} value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="EQUITY">سهم EGP</option><option value="PRICE_INDEX">مؤشر سعري</option><option value="TOTAL_RETURN_INDEX">مؤشر عائد كلي</option>
          </select></label>
          {holders.map(([key, name, type]) => <label key={key}>{name}<input required={key !== "delisted_on" && (key !== "isin" || kind === "EQUITY")}
            className={opsField} name={key} type={type} dir="ltr"/></label>)}
        </div>
        <details><summary className="cursor-pointer">ربط أعمدة الملف</summary>
          <p className="my-2 text-sm text-gray-400">اترك الاسم فاضي لو نفس اسم العمود في القالب.</p>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{columns.map((column) => <label key={column} className="text-sm">
            <bdi>{column}</bdi><input className={opsField} dir="ltr" value={mapping[column] ?? ""} onChange={(event) =>
              setMapping((old) => { const copy = {...old}; if (event.target.value) copy[column] = event.target.value; else delete copy[column]; return copy; })}/>
          </label>)}</div>
        </details>
        <details><summary className="cursor-pointer">إجراءات الشركة والجلسات الموقوفة</summary>
          <label className="block pt-2 text-sm">قائمة الإجراءات JSON<textarea className={opsField} dir="ltr" name="actions" defaultValue="[]"/></label>
          <label className="block pt-2 text-sm">تواريخ إيقاف التداول JSON<textarea className={opsField} dir="ltr" name="suspended" defaultValue="[]"/></label>
        </details>
        <label className="flex gap-2"><input required type="checkbox" name="rights_confirmed"/> عندي حق تخزين البيانات واستخدامها هنا.</label>
        <label className="flex gap-2"><input required type="checkbox" name="actions_reviewed"/> راجعت إجراءات الشركة ومواعيد الإتاحة والتعليق من المصدر.</label>
      </>}
      <button className={opsButton} disabled={busy}>راجع الملف قبل الحفظ</button>
    </form>
    {preview && <article className={opsPanel}><h2 className="font-bold">نتيجة التحقق</h2>
      {preview.valid ? <>
        <p><bdi>{preview.ticker}</bdi> · <bdi>{preview.isin}</bdi> · {preview.source}</p>
        <p>{preview.bars} من {preview.expected} جلسة · {preview.halted} إيقاف · {preview.actions} إجراءات</p>
        <p>آخر توقيت مصدر {timeLabel(preview.source_timestamp)}</p>
        {!!preview.missing?.length && <p className="break-words text-amber-300">تغطية جزئية · <bdi>{preview.missing.join("، ")}</bdi></p>}
        {envelope && <button className={opsButton} disabled={busy} onClick={() => void confirmImport()}>احفظ الحزمة المراجَعة</button>}
      </> : <>
        <p role="alert" className="text-amber-300">{label(preview.error)}</p>
        {preview.issues?.map((issue) => <p key={issue.field + issue.code} className="text-sm"><bdi>{issue.field}</bdi> · {issue.code}</p>)}
      </>}
    </article>}
    <article className={opsPanel}><h2 className="font-bold">آخر محاولات الاستيراد</h2>
      {!records.length && <p className="text-gray-400">مفيش محاولات محفوظة.</p>}
      {records.map((r) => <p className="text-sm" key={r.id}><bdi>{r.report.ticker}</bdi> · {label(r.status)} · {timeLabel(r.created)} {r.report.error && " · " + label(r.report.error)}</p>)}
    </article>
  </section>;
}
