import { useEffect, useMemo, useRef, useState } from 'react'
import '../styles/home.css'

// progress-bar gradient (playlist match meter): dark green -> spotify green -> bright mint highlight
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

// per-song label gradient: washed-out/white = weak match -> spotify green = strong match
const LABEL_GRADIENT_STOPS = [
  { t: 0, c: [225, 228, 226] },
  { t: 1, c: [29, 185, 84] },
]

function labelColorAt(t) {
  for (let i = 0; i < LABEL_GRADIENT_STOPS.length - 1; i++) {
    const a = LABEL_GRADIENT_STOPS[i]
    const b = LABEL_GRADIENT_STOPS[i + 1]
    if (t >= a.t && t <= b.t) {
      const local = (t - a.t) / (b.t - a.t)
      const rgb = a.c.map((v, idx) => Math.round(v + (b.c[idx] - v) * local))
      return `rgb(${rgb.join(',')})`
    }
  }
  return `rgb(${LABEL_GRADIENT_STOPS.at(-1).c.join(',')})`
}

function ScoreMeter({ score, size = 'default' }) {
  if (score === null || score === undefined) {
    return (
      <div className={`score-meter score-meter-empty score-meter-${size}`}>
        <div className="meter-track" />
        <span className="meter-value">—</span>
      </div>
    )
  }
  const clamped = Math.max(0, Math.min(100, score))
  return (
    <div className={`score-meter score-meter-${size}`}>
      <div className="meter-track">
        <div
          className="meter-fill"
          style={{ width: `${clamped}%`, background: colorAt(clamped / 100) }}
        />
      </div>
      <span className="meter-value">{score}%</span>
    </div>
  )
}

function ScoreLabel({ score }) {
  if (score === null || score === undefined) {
    return <span className="score-label score-label-empty">—</span>
  }
  const clamped = Math.max(0, Math.min(100, score))
  return (
    <span className="score-label" style={{ color: labelColorAt(clamped / 100) }}>
      {score}%
    </span>
  )
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

function Home() {
  const [playlists, setPlaylists] = useState([])
  const [playlistMeta, setPlaylistMeta] = useState({}) // { [id]: { total_ingested, recommendations, track_ids } }
  const [loadingPlaylists, setLoadingPlaylists] = useState(true)
  const fetched = useRef(false)

  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)

  const [playlistResults, setPlaylistResults] = useState({})
  const [selected, setSelected] = useState(null)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const searchRef = useRef(null)

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true

    fetch('http://localhost:8000/playlists')
      .then(res => res.json())
      .then(data => {
        setPlaylists(data.items)

        // playlists whose snapshot was already cached come back with a
        // ready-to-use result instead of a job_id — seed those in directly
        // since there's no Celery job to poll for them
        const seeded = {}
        data.items.forEach(p => {
          if (p.result) seeded[p.id] = p.result
        })
        if (Object.keys(seeded).length > 0) {
          setPlaylistMeta(prev => ({ ...prev, ...seeded }))
        }
      })
      .catch(err => console.error(err))
      .finally(() => setLoadingPlaylists(false))
  }, [])

  const playlistMetaRef = useRef({})
  useEffect(() => {
    playlistMetaRef.current = playlistMeta
  }, [playlistMeta])

  const pollIntervalRef = useRef(null)

  useEffect(() => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)

    const tick = async () => {
      const pending = playlists.filter(
        p => p.job_id && !playlistMetaRef.current[p.id]
      )
      if (pending.length === 0) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
        return
      }

      const jobIdToPlaylistId = {}
      pending.forEach(p => { jobIdToPlaylistId[p.job_id] = p.id })

      try {
        const jobIds = pending.map(p => p.job_id).join(',')
        const res = await fetch(`http://localhost:8000/playlists/status?job_ids=${jobIds}`)
        const data = await res.json()

        const updates = {}
        Object.entries(data.items).forEach(([jobId, status]) => {
          const playlistId = jobIdToPlaylistId[jobId]
          if (!playlistId) return
          if (status.state === 'done') {
            updates[playlistId] = status.result
          } else if (status.state === 'error') {
            console.error(`Job failed for playlist ${playlistId}`)
          }
        })

        if (Object.keys(updates).length > 0) {
          setPlaylistMeta(prev => ({ ...prev, ...updates }))
        }
      } catch (err) {
        console.error('Polling error:', err)
      }
    }

    const hasPending = playlists.some(
      p => p.job_id && !playlistMetaRef.current[p.id]
    )
    if (hasPending) {
      pollIntervalRef.current = setInterval(tick, 3000)
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
    }
  }, [playlists])

  // debounced autocomplete
  const justSelected = useRef(false)

  useEffect(() => {
    if (justSelected.current) {
      justSelected.current = false
      return
    }
    if (!query.trim()) {
      setSuggestions([])
      return
    }
    const timeout = setTimeout(() => {
      fetch(`http://localhost:8000/track-search?q=${encodeURIComponent(query)}`)
        .then(res => res.json())
        .then(data => {
          setSuggestions(data.items)
          setShowDropdown(true)
        })
        .catch(err => console.error(err))
    }, 300)

    return () => clearTimeout(timeout)
  }, [query])

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setShowDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSelect = async (track) => {
    justSelected.current = true
    setQuery(`${track.name} — ${track.artist}`)
    setShowDropdown(false)
    setSelected(track)
    setExpanded(null)
    setPlaylistResults({})
    setSearchError(false)
    setSearching(true)

    const readyPlaylists = playlists
      .filter(p => playlistMeta[p.id])
      .map(p => ({
        playlist_id: p.id,
        track_ids: playlistMeta[p.id].track_ids,
      }))

    try {
      const res = await fetch('http://localhost:8000/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          track_id: track.id,
          track_name: track.name,
          artist_name: track.artist,
          album_name: track.album ?? null,
          duration_ms: track.duration_ms ?? null,
          playlists: readyPlaylists,
        }),
      })

      if (!res.ok) {
        throw new Error(`search failed with status ${res.status}`)
      }

      const data = await res.json()
      setPlaylistResults(data.results || {})
    } catch (err) {
      console.error(err)
      setSearchError(true)
      setPlaylistResults({})
    } finally {
      setSearching(false)
    }
  }

  const toggleExpand = (playlistId) => {
    setExpanded(prev => (prev === playlistId ? null : playlistId))
  }

  const [addStatus, setAddStatus] = useState({}) // { [`${playlistId}-${trackId}`]: 'adding'|'added'|'error' }

  const handleAddToPlaylist = async (playlistId, track) => {
    const key = `${playlistId}-${track.id}`
    setAddStatus(prev => ({ ...prev, [key]: 'adding' }))
    try {
      const res = await fetch(`http://localhost:8000/playlists/${playlistId}/tracks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: track.id }),
      })
      if (!res.ok) throw new Error('add failed')
      setAddStatus(prev => ({ ...prev, [key]: 'added' }))

      // keep local state consistent so the button reflects reality
      // without needing a full playlists refetch
      setPlaylistMeta(prev => ({
        ...prev,
        [playlistId]: {
          ...prev[playlistId],
          track_ids: [...(prev[playlistId]?.track_ids || []), track.id],
        },
      }))
    } catch (err) {
      console.error(err)
      setAddStatus(prev => ({ ...prev, [key]: 'error' }))
    }
  }

  // once a track is selected, rank playlists by match score so the best
  // fit surfaces first — playlists without a score yet (still processing,
  // or search in flight) fall to the bottom in their original order
  const rankedPlaylists = useMemo(() => {
    if (!selected) return playlists.map(p => ({ playlist: p, mean: null }))

    const withScore = []
    const withoutScore = []
    playlists.forEach(p => {
      const mean = playlistResults[p.id]?.mean
      if (typeof mean === 'number') {
        withScore.push({ playlist: p, mean })
      } else {
        withoutScore.push({ playlist: p, mean: null })
      }
    })
    withScore.sort((a, b) => b.mean - a.mean)
    return [...withScore, ...withoutScore]
  }, [playlists, playlistResults, selected])

  return (
    <div className="home-page">
      <AmbientVisualizer />

      <div className="home-header">
        <h1 className="home-logo">playlist<span>match</span></h1>
      </div>

      {loadingPlaylists && (
        <div className="loading-row">
          <span className="spinner" />
          loading playlists…
        </div>
      )}

      {!loadingPlaylists && (
        <div className="search-container" ref={searchRef}>
          <input
            className="search-input"
            placeholder="search for a song..."
            value={query}
            onChange={e => {
              setQuery(e.target.value)
              setSelected(null)
              setPlaylistResults({})
              setSearchError(false)
            }}
            onFocus={() => suggestions.length > 0 && setShowDropdown(true)}
          />

          {showDropdown && suggestions.length > 0 && (
            <div className="search-dropdown">
              {suggestions.map(track => (
                <div
                  key={track.id}
                  className="search-dropdown-item"
                  onClick={() => handleSelect(track)}
                >
                  <span className="track-name">{track.name}</span>
                  <span className="track-artist">{track.artist}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {selected && (
        <div className="selected-track">
          {searching && <span className="spinner" />}
          {searching ? (
            <>analyzing <strong>{selected.name}</strong> by {selected.artist}</>
          ) : searchError ? (
            <span className="search-error-text">could not analyze that track</span>
          ) : (
            <>results for <strong>{selected.name}</strong> by {selected.artist}</>
          )}
        </div>
      )}

      {!loadingPlaylists && playlists.length === 0 && (
        <p className="empty-state empty-state-standalone">no playlists found</p>
      )}

      {playlists.length > 0 && (
        <div className="playlist-leaderboard">
          {rankedPlaylists.map(({ playlist, mean }, rank) => {
            const isOpen = expanded === playlist.id
            const meta = playlistMeta[playlist.id] // undefined until job done (or seeded from cache)
            const pr = playlistResults[playlist.id]
            const top5 = pr?.top5 ?? null
            const isProcessing = !meta
            const isBestMatch = selected && !searching && rank === 0 && mean !== null

            return (
              <div
                className={`playlist-card ${isOpen ? 'open' : ''} ${isBestMatch ? 'best-match' : ''}`}
                key={playlist.id}
              >
                <div className="playlist-row" onClick={() => toggleExpand(playlist.id)}>
                  <div className="playlist-rank">
                    {selected && !searching && mean !== null ? (
                      <span className="rank-number">{rank + 1}</span>
                    ) : (
                      <span className="rank-number rank-number-empty">·</span>
                    )}
                  </div>

                  <div className="playlist-info">
                    <div className="playlist-name-row">
                      <span className="playlist-name">{playlist.name}</span>
                      {isBestMatch && <span className="best-match-tag">best match</span>}
                    </div>
                    <span className="playlist-track-count">
                      {isProcessing
                        ? <span className="spinner" style={{ display: 'inline-block' }} />
                        : `${meta.total_ingested}/${playlist.total_tracks} processed`}
                    </span>
                  </div>

                  <div className="playlist-score">
                    {searching ? (
                      <span className="spinner" />
                    ) : (
                      <ScoreMeter score={mean} />
                    )}

                    {selected && !searching && mean !== null && (() => {
                      const key = `${playlist.id}-${selected.id}`
                      const alreadyInPlaylist = meta?.track_ids?.includes(selected.id)
                      const status = alreadyInPlaylist ? 'already' : (addStatus[key] || 'idle')
                      return (
                        <button
                          className={`add-track-btn ${status}`}
                          disabled={status === 'adding' || status === 'added' || status === 'already'}
                          onClick={(e) => {
                            e.stopPropagation() // don't toggle the playlist card open/closed
                            handleAddToPlaylist(playlist.id, selected)
                          }}
                          title={
                            status === 'already' ? 'Already in playlist'
                            : status === 'added' ? 'Added'
                            : status === 'error' ? 'Failed — click to retry'
                            : `Add ${selected.name} to this playlist`
                          }
                        >
                          {status === 'already' || status === 'added' ? '✓'
                            : status === 'adding' ? '…'
                            : status === 'error' ? '!'
                            : '+'}
                        </button>
                      )
                    })()}
                    <span className={`chevron ${isOpen ? 'rotated' : ''}`}>▾</span>
                  </div>
                </div>

                <div className="playlist-details">
                  {isProcessing ? (
                    <p className="empty-state">still listening…</p>
                  ) : searching ? (
                    <p className="empty-state">analyzing…</p>
                  ) : (
                    <>
                      {top5 && top5.length > 0 ? (
                        <ul className="top-tracks">
                          {top5.map((r, i) => (
                            <li key={i} className="top-track-item">
                              <span className="top-track-rank">{i + 1}</span>
                              <div className="top-track-meta">
                                <span className="top-track-name">{r.name}</span>
                                <span className="top-track-artist">{r.artist}</span>
                              </div>
                              <ScoreLabel score={r.score} />
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="empty-state">
                          {selected ? 'no ingested tracks in this playlist' : 'search a song to see matches'}
                        </p>
                      )}

                      {meta?.recommendations?.length > 0 && (
                        <div className="recommendations">
                          <p className="recommendations-label">you might also like</p>
                          <ul className="top-tracks">
                            {meta.recommendations.map((r, i) => {
                              const key = `${playlist.id}-${r.id}`
                              const alreadyInPlaylist = meta.track_ids?.includes(r.id)
                              const status = alreadyInPlaylist ? 'already' : (addStatus[key] || 'idle')

                              return (
                                <li key={i} className="top-track-item recommendation-item">
                                  <span className="top-track-rank" />
                                  <div className="top-track-meta">
                                    <span className="top-track-name">{r.name}</span>
                                    <span className="top-track-artist">{r.artist}</span>
                                  </div>
                                  <ScoreLabel score={r.score} />
                                  <button
                                    className={`add-track-btn ${status}`}
                                    disabled={status === 'adding' || status === 'added' || status === 'already'}
                                    onClick={() => handleAddToPlaylist(playlist.id, r)}
                                    title={
                                      status === 'already' ? 'Already in playlist'
                                      : status === 'added' ? 'Added'
                                      : status === 'error' ? 'Failed — click to retry'
                                      : 'Add to playlist'
                                    }
                                  >
                                    {status === 'already' || status === 'added' ? '✓'
                                      : status === 'adding' ? '…'
                                      : status === 'error' ? '!'
                                      : '+'}
                                  </button>
                                </li>
                              )
                            })}
                          </ul>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default Home