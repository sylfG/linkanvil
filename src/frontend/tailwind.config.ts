import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0D0E17",
        surface: "#13141F",
        card: "#1C1D2E",
        border: "#2A2B3D",
        accent: {
          DEFAULT: "#7C3AED",
          hover: "#6D28D9",
          light: "#8B5CF6",
        },
        muted: "#64748B",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
