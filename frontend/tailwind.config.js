/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        void: '#05060f',
        surface: '#0b0d1a',
        line: '#1e2235',
        electric: '#6366f1',
        violet: '#8b5cf6',
        cyan: '#22d3ee',
        ink: '#e8eaf6',
        muted: '#9aa3c7',
      },
      fontFamily: {
        sans: [
          'Inter',
          'ui-sans-serif',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'Helvetica Neue',
          'Arial',
          'sans-serif',
        ],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Consolas', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 0 0 rgba(232, 234, 246, 0.04) inset, 0 24px 60px -32px rgba(99, 102, 241, 0.55)',
        glow: '0 0 0 1px rgba(99, 102, 241, 0.35), 0 18px 50px -20px rgba(139, 92, 246, 0.65)',
      },
      backgroundImage: {
        'brand-gradient': 'linear-gradient(90deg, #6366f1 0%, #8b5cf6 50%, #22d3ee 100%)',
      },
      keyframes: {
        breathe: {
          '0%, 100%': { opacity: '0.45' },
          '50%': { opacity: '1' },
        },
      },
      animation: {
        breathe: 'breathe 2.4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
