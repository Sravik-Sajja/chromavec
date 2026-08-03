import { useMemo } from 'react'
import '../styles/login.css'

const FEATURES = ['MELODY', 'TONE', 'TEMPO', 'BRIGHTNESS', 'ENERGY']

// spotify-green gradient: deep forest -> spotify green -> bright mint highlight
const GRADIENT_STOPS = [
  { t: 0, c: [20, 110, 64] },
  { t: 0.5, c: [29, 185, 84] },
  { t: 1, c: [87, 255, 168] },
]

function colorAt(t) {
  for (let i = 0; i < GRADIENT_STOPS.length - 1; i++) {
    const a = GRADIENT_STOPS[i]
    const b = GRADIENT_STOPS[i + 1]
    if (t >= a.t && t <= b.t) {
      const local = (t - a.t) / (b.t - a.t)
      const rgb = a.c.map((v, idx) => Math.round(v + (b.c[idx] - v) * local))
      return `rgb(${rgb.join(',')})`
    }
  }
  return `rgb(${GRADIENT_STOPS.at(-1).c.join(',')})`
}

const BAR_COUNT = 64

function Login() {
  // stable per-mount so bars don't reshuffle on re-render
  const bars = useMemo(() => {
    return Array.from({ length: BAR_COUNT }, (_, i) => {
      const t = i / (BAR_COUNT - 1)
      return {
        color: colorAt(t),
        height: 10 + Math.random() * 72,
        duration: (1.4 + Math.random() * 1.8).toFixed(2),
        delay: (Math.random() * -3).toFixed(2),
      }
    })
  }, [])

  const handleLogin = () => {
    window.location.href = 'http://localhost:8000/login'
  }

  return (
    <div className="login-page">
      <div className="visualizer" aria-hidden="true">
        {bars.map((bar, i) => (
          <span
            key={i}
            className="visualizer-bar"
            style={{
              '--color': bar.color,
              '--h': `${bar.height}%`,
              '--duration': `${bar.duration}s`,
              '--delay': `${bar.delay}s`,
            }}
          />
        ))}
      </div>

      <div className="login-card">
        <svg className="mark" viewBox="0 0 48 24" aria-hidden="true">
          <defs>
            <linearGradient id="markGradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#146e40" />
              <stop offset="50%" stopColor="#1db954" />
              <stop offset="100%" stopColor="#57ffa8" />
            </linearGradient>
          </defs>
          <path
            d="M2 12 L8 12 L11 3 L16 21 L20 8 L23 16 L26 12 L46 12"
            fill="none"
            stroke="url(#markGradient)"
            strokeWidth="2.4"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>

        <h1 className="logo">
          playlist<span>match</span>
        </h1>

        <p className="tagline">
          music recommendations based on how your songs actually sound
        </p>

        <div className="features-row">
          {FEATURES.map((f, i) => (
            <span key={f} className="feature-chip">
              {f}
              {i < FEATURES.length - 1 && <span className="feature-dot">·</span>}
            </span>
          ))}
        </div>

        <button className="spotify-btn" onClick={handleLogin}>
          <span className="spotify-btn-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="16" height="16">
              <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="1.6" />
              <path
                d="M6.5 10c4-1.2 7.5-1.2 11 .6M7 13.2c3.3-.9 6-.9 9 .5M7.6 16.2c2.6-.6 4.6-.6 6.8.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </span>
          Connect Spotify
        </button>
      </div>
    </div>
  )
}

export default Login