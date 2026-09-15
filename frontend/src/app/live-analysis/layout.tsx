import React, { Suspense } from "react";
import ManualEodRecovery from "@/components/ManualEodRecovery";

export default function LiveAnalysisLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Suspense fallback={null}>
        <ManualEodRecovery />
      </Suspense>
      {children}
    </>
  );
}
