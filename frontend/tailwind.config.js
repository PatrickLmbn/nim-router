export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      colors: {
        brand: {
          orange: '#ff6b35',
          orangeLight: '#ff8c42',
          cyan: '#00d2ff',
          blue: '#3a7bd5',
          green: '#00f5a0',
          magenta: '#f72585',
          purple: '#b15eff',
        },
        dark: {
          bg: '#0f1117',
          card: '#151922',
          cardHover: '#1a1f2c',
          border: 'rgba(255, 255, 255, 0.07)',
          subtext: '#8e9aaf',
        },
        light: {
          bg: '#eef2f7',
          card: '#f8fafc',
          cardHover: '#ffffff',
          border: 'rgba(0, 0, 0, 0.08)',
          subtext: '#64748b',
        }
      },
      boxShadow: {
        'neu-dark': '6px 6px 16px rgba(0, 0, 0, 0.7), -4px -4px 12px rgba(255, 255, 255, 0.025)',
        'neu-dark-sm': '3px 3px 8px rgba(0, 0, 0, 0.6), -2px -2px 6px rgba(255, 255, 255, 0.02)',
        'neu-dark-inset': 'inset 3px 3px 6px rgba(0, 0, 0, 0.8), inset -2px -2px 4px rgba(255, 255, 255, 0.02)',
        'neu-light': '6px 6px 16px #c8d3e0, -6px -6px 16px #ffffff',
        'neu-light-sm': '3px 3px 8px #d0dbe8, -3px -3px 8px #ffffff',
        'neu-light-inset': 'inset 3px 3px 6px #cad6e4, inset -3px -3px 6px #ffffff',
        'glow-orange': '0 0 20px rgba(255, 107, 53, 0.4)',
        'glow-cyan': '0 0 20px rgba(0, 210, 255, 0.4)',
        'glow-magenta': '0 0 20px rgba(247, 37, 133, 0.4)',
      },
      borderRadius: {
        '3xl': '28px',
        '4xl': '36px',
      }
    },
  },
  plugins: [],
}
