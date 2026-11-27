import coreWebVitals from "eslint-config-next/core-web-vitals";

export default [
  ...coreWebVitals,
  {
    files: ["src/app/layout.tsx"],
    // This is the shared App Router layout. The rule expects a Pages Router _document.
    rules: { "@next/next/no-page-custom-font": "off" },
  },
  {
    files: [
      "src/app/{live-analysis,opportunities,sharia,stocks}/page.tsx",
      "src/app/stocks/*/page.tsx",
      "src/components/{CompanyProfileCard,DeliverySettings,ManualEodRecovery,MobileNavigation,OrderReview,PaperDashboard,StockSearchInput}.tsx",
    ],
    // Preserve the existing loading/form resets in effects. Hooks correctness
    // rules stay active, and new files use the default compiler recommendations.
    rules: { "react-hooks/set-state-in-effect": "off" },
  },
];
