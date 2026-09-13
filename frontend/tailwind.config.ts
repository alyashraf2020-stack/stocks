import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#0B0F17",
        surface: "#111827",
        surfaceBorder: "#1F2937",
        surfaceHover: "#1E293B",
        primary: {
          DEFAULT: "#10B981", // Emerald green
          hover: "#059669",
          muted: "rgba(16, 185, 129, 0.15)",
        },
        accent: {
          DEFAULT: "#3B82F6", // Blue
          hover: "#2563EB",
        },
        danger: {
          DEFAULT: "#EF4444", // Rose/Red
          hover: "#DC2626",
          muted: "rgba(239, 68, 68, 0.15)",
        },
        warning: {
          DEFAULT: "#F59E0B", // Amber
          hover: "#D97706",
          muted: "rgba(245, 158, 11, 0.15)",
        }
      },
      fontFamily: {
        arabic: ["Cairo", "Segoe UI", "Tahoma", "sans-serif"],
      }
    },
  },
  plugins: [],
};
export default config;