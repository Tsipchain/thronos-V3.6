/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#003366',
        accent: '#FFD700'
      },
      fontFamily: {
        sans: ['system-ui', 'sans-serif']
      }
    },
  },
  plugins: [],
}
