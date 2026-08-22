import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import '../styles/profile.css'
import { useProfile } from '../context/ProfileContext'

// same gradient used on login/home so the soundbars feel consistent app-wide
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

function AmbientVisualizer() {
  const bars = useMemo(() => {
    return Array.from({ length: 80 }, (_, i) => {
      const t = i / 79
      return {
        color: colorAt(t),
        height: 8 + Math.random() * 60,
        duration: (2 + Math.random() * 2.4).toFixed(2),
        delay: (Math.random() * -4).toFixed(2),
      }
    })
  }, [])

  return (
    <div className="ambient-visualizer" aria-hidden="true">
      {bars.map((bar, i) => (
        <span
          key={i}
          className="ambient-bar"
          style={{
            '--color': bar.color,
            '--h': `${bar.height}%`,
            '--duration': `${bar.duration}s`,
            '--delay': `${bar.delay}s`,
          }}
        />
      ))}
    </div>
  )
}

function Profile() {
  const navigate = useNavigate()
  const { profile, loadingProfile: loading, profileError: error } = useProfile()

  return (
    <div className="profile-page">
      <AmbientVisualizer />

      <button className="back-btn" onClick={() => navigate('/home')}>
        ← back
      </button>

      {loading && (
        <div className="loading-row">
          <span className="spinner" /> loading profile…
        </div>
      )}

      {!loading && error && <p className="empty-state">could not load your profile</p>}

      {!loading && !error && profile && (
        <>
          <div className="profile-card">
            {profile.image_url ? (
              <img className="profile-avatar" src={profile.image_url} alt={profile.display_name} />
            ) : (
              <div className="profile-avatar profile-avatar-fallback">
                {profile.display_name?.[0]?.toUpperCase() || '?'}
              </div>
            )}

            <h1 className="profile-name">{profile.display_name || 'Unknown user'}</h1>
            {profile.email && <p className="profile-email">{profile.email}</p>}

            <div className="profile-stats">
              <div className="profile-stat">
                <span className="profile-stat-value">{profile.owned_playlists}</span>
                <span className="profile-stat-label">playlists</span>
              </div>
              {typeof profile.followers === 'number' && (
                <div className="profile-stat">
                  <span className="profile-stat-value">{profile.followers}</span>
                  <span className="profile-stat-label">followers</span>
                </div>
              )}
              {profile.product && (
                <div className="profile-stat">
                  <span className="profile-stat-value">{profile.product}</span>
                  <span className="profile-stat-label">plan</span>
                </div>
              )}
            </div>

            {profile.spotify_url && (
              <a className="profile-spotify-link" href={profile.spotify_url} target="_blank" rel="noreferrer">
                view on spotify
              </a>
            )}
          </div>

          <div className="profile-section-row">
            <div className="profile-section">
              <p className="profile-section-label">top artists</p>
              {profile.top_artists?.length > 0 ? (
                <ul className="profile-taste-list">
                  {profile.top_artists.map((a, i) => (
                    <li key={i} className="profile-taste-item">
                      {a.image_url ? (
                        <img className="profile-taste-thumb" src={a.image_url} alt={a.name} />
                      ) : (
                        <div className="profile-taste-thumb profile-taste-thumb-fallback" />
                      )}
                      <span className="profile-taste-name">{a.name}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state">not enough listening history yet</p>
              )}
            </div>

            <div className="profile-section">
              <p className="profile-section-label">top songs</p>
              {profile.top_tracks?.length > 0 ? (
                <ul className="profile-taste-list">
                  {profile.top_tracks.map((t, i) => (
                    <li key={i} className="profile-taste-item">
                      {t.image_url ? (
                        <img className="profile-taste-thumb profile-taste-thumb-square" src={t.image_url} alt={t.name} />
                      ) : (
                        <div className="profile-taste-thumb profile-taste-thumb-square profile-taste-thumb-fallback" />
                      )}
                      <div className="profile-taste-meta">
                        <span className="profile-taste-name">{t.name}</span>
                        <span className="profile-taste-sub">{t.artist}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-state">not enough listening history yet</p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default Profile