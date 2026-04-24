/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./app/static/**/*.html",
    "./app/static/**/*.js",
    "./app/**/*.py",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          blue: "#2b7fff",
          red: "#dc2626",
          navy: "#102a43",
          sky: "#eff6ff",
        },
      },
      boxShadow: {
        soft: "0 20px 55px rgba(16, 42, 67, 0.10)",
        glow: "0 10px 28px rgba(43, 127, 255, 0.12)",
      },
      fontFamily: {
        sans: ["Outfit", "ui-sans-serif", "system-ui", "sans-serif"],
        serif: ["Fraunces", "ui-serif", "Georgia", "serif"],
      },
    },
  },
  plugins: [],
};
