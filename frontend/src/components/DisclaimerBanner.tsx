import React from "react";
import { AlertCircle } from "lucide-react";

export default function DisclaimerBanner() {
  return (
    <div className="bg-surface border-y border-surfaceBorder px-4 py-2.5 text-xs text-gray-400 flex items-center justify-center gap-2">
      <AlertCircle className="w-4 h-4 text-warning flex-shrink-0" />
      <span>
        <strong className="text-gray-300">تنويه وإخلاء مسؤولية:</strong> هذه المنصة أداة دعم قرار وليست ضماناً للربح أو بديلاً عن الاستشارة المالية المتخصصة.
      </span>
    </div>
  );
}