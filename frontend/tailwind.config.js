/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sky: '#5C94FC',
        panel: '#FFF8E7',
        ink: '#232323',
        brick: '#8B5A2B',
        primary: '#E7402D',
        success: '#2FA84F',
        warn: '#F7B32B',
        danger: '#C0392B',
        info: '#3E7BFA',
      },
      fontFamily: {
        display: ['"Press Start 2P"', 'monospace'],
        heading: ['"Pixelify Sans"', 'sans-serif'],
        body: ['Nunito', 'sans-serif'],
      },
      boxShadow: {
        block: '4px 4px 0px 0px rgba(35, 35, 35, 0.2)',
        hover: '5px 5px 0px 0px rgba(35, 35, 35, 0.25)',
      },
      borderRadius: {
        DEFAULT: '6px',
      }
    },
  },
  plugins: [],
}