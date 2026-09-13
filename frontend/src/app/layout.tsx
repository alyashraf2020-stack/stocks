import type { Metadata } from "next";
import "@/styles/globals.css";
import Navbar from "@/components/Navbar";
import DisclaimerBanner from "@/components/DisclaimerBanner";

export const metadata: Metadata = {
  title: "منصة تداول وتحليل أسهم البورصة المصرية | EGX Analysis",
  description: "منصة تحليل فني ودعم قرار لحظي متخصصة حصراً في أسهم البورصة المصرية وفق قواعد إدارة المخاطر الصارمة وسياسة انعدام التأخير.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ar" dir="rtl">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;500;600;700;800;900&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-background text-gray-100 min-h-screen flex flex-col font-arabic">
        <Navbar />
        <DisclaimerBanner />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
          {children}
        </main>
        
        {/* Permanent Footer Disclaimer */}
        <footer className="bg-surface border-t border-surfaceBorder py-6 mt-12 text-center text-xs text-gray-500 space-y-2">
          <p className="font-medium text-gray-400">
            البورصة المصرية (EGX) | منصة دعم القرار والتحليل الفني اللحظي
          </p>
          <p className="max-w-2xl mx-auto text-[11px] text-gray-400 px-4">
            هذه المنصة أداة دعم قرار وليست ضماناً للربح أو بديلاً عن الاستشارة المالية المتخصصة. لا تقدم المنصة أي وعود بأرباح مضمونة أو صفقات رابحة حتمية.
          </p>
          <p className="text-[10px] text-gray-400">
            نطاق العمل: أسهم البورصة المصرية فقط | سياسة انعدام التأخير (Zero Session Lag) | صفقات شرائية فقط (Long-Only)
          </p>
        </footer>
      </body>
    </html>
  );
}