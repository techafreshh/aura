/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // Aura-specific
        aura: {
          bg: "#09090b",
          "bg-2": "#0c0c0f",
          surface: "rgba(255,255,255,0.03)",
          "surface-2": "rgba(255,255,255,0.05)",
          border: "#27272a",
          "border-soft": "rgba(255,255,255,0.06)",
          fg: "#fafafa",
          "fg-2": "#e4e4e7",
          muted: "#a1a1aa",
          "muted-2": "#71717a",
          accent: "#6366f1",
          "accent-2": "#818cf8",
          "accent-3": "#a5b4fc",
          "accent-deep": "#4338ca",
          success: "#10b981",
          danger: "#ef4444",
          warn: "#f59e0b",
        },
      },
      fontFamily: {
        display: ["Inter", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        body: ["Inter", "-apple-system", "BlinkMacSystemFont", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "breathe": {
          "0%, 100%": { transform: "scale(1)" },
          "50%": { transform: "scale(1.025)" },
        },
        "pulse-glow": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.85" },
          "50%": { transform: "scale(1.06)", opacity: "1" },
        },
        "ring-expand": {
          "0%": { transform: "scale(0.55)", opacity: "0" },
          "20%": { opacity: "0.7" },
          "100%": { transform: "scale(1.25)", opacity: "0" },
        },
        "swirl": {
          "to": { transform: "rotate(360deg)" },
        },
      },
      animation: {
        "breathe": "breathe 5s ease-in-out infinite",
        "pulse-glow": "pulse-glow 5s ease-in-out infinite",
        "ring-expand": "ring-expand 5.6s ease-out infinite",
        "swirl": "swirl 14s linear infinite",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}
