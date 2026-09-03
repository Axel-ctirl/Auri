/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Bread's own palette: warm crust tones on a cool dark ground. It is
        // deliberately not anyone else's product colours.
        crust: {
          50: "#fdf6ed",
          100: "#f7e6cf",
          200: "#eecfa4",
          300: "#e2b273",
          400: "#d5954a",
          500: "#c07a2f",
          600: "#9d5f26",
          700: "#7a4820",
          800: "#5a361b",
          900: "#3c2413",
        },
        ink: {
          50: "#f4f6f8",
          100: "#e3e7ec",
          200: "#c2cad4",
          300: "#94a1b0",
          400: "#66768a",
          500: "#4a596b",
          600: "#364354",
          700: "#28323f",
          800: "#1b232d",
          900: "#12181f",
          950: "#0b0f14",
        },
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Cascadia Code",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        blink: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.2" } },
      },
      animation: {
        "fade-in": "fade-in 160ms ease-out",
        blink: "blink 1s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
