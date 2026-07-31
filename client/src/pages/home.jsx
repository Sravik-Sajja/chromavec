import { useEffect, useRef, useState } from 'react'
import '../styles/home.css'

function scoreColor(pct) {
  const clamped = Math.max(0, Math.min(100, pct))
  const RED_MAX = 25
  const GREEN_MIN = 80
  let r, g
  if (clamped <= RED_MAX) {
    r = 220; g = 60
  } else if (clamped >= GREEN_MIN) {
    r = 40; g = 185
  } else {
    const t = (clamped - RED_MAX) / (GREEN_MIN - RED_MAX)
    if (t < 0.5) {
      const s = t / 0.5
      r = 220
      g = Math.round(60 + s * (200 - 60))
    } else {
      const s = (t - 0.5) / 0.5
      r = Math.round(220 - s * (220 - 40))
      g = Math.round(200 + s * (185 - 200))
    }
  }
  return {
    color: `rgb(${r},${g},30)`,
    background: `rgba(${r},${g},30,0.12)`,
    borderColor: `rgba(${r},${g},30,0.35)`,
  }
}

function Home() {
  const [playlists, setPlaylists] = useState([])
  const [playlistMeta, setPlaylistMeta] = useState({}) // { [id]: { total_ingested, recommendations, track_ids } }
  const [loadingPlaylists, setLoadingPlaylists] = useState(true)
  const fetched = useRef(false)
  const pollingRefs = useRef({}) // track active intervals so we can clear them

  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)

  const [playlistResults, setPlaylistResults] = useState({})
  const [selected, setSelected] = useState(null)
  const [searching, setSearching] = useState(false)
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

  // start polling for each playlist once we have job_ids
  useEffect(() => {
    playlists.forEach(p => {
      if (!p.job_id) return
      if (pollingRefs.current[p.id]) return // already polling

      const interval = setInterval(async () => {
        try {
          const res = await fetch(`http://localhost:8000/playlists/status/${p.job_id}`)
          const data = await res.json()

          if (data.state === 'done') {
            clearInterval(pollingRefs.current[p.id])
            delete pollingRefs.current[p.id]
            setPlaylistMeta(prev => ({
              ...prev,
              [p.id]: data.result, // { total_ingested, recommendations, track_ids }
            }))
          } else if (data.state === 'error') {
            clearInterval(pollingRefs.current[p.id])
            delete pollingRefs.current[p.id]
            console.error(`Job failed for playlist ${p.name}`)
          }
        } catch (err) {
          console.error(`Polling error for ${p.name}:`, err)
        }
      }, 3000)

      pollingRefs.current[p.id] = interval
    })

    // cleanup on unmount
    return () => {
      Object.values(pollingRefs.current).forEach(clearInterval)
    }
  }, [playlists])

  // debounced autocomplete
  useEffect(() => {
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
    setQuery(`${track.name} — ${track.artist}`)
    setShowDropdown(false)
    setSelected(track)
    setExpanded(null)
    setPlaylistResults({})
    setSearching(true)

    // only search playlists that have finished processing
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
      const data = await res.json()
      setPlaylistResults(data.results)
    } catch (err) {
      console.error(err)
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

  return (
    <div className="home-page">
      <div className="home-header">
        <h1 className="home-logo">playlist<span>match</span></h1>
        <p className="home-subtitle">find out which of your playlists a song actually fits</p>
      </div>

      <div className="search-container" ref={searchRef}>
        <input
          className="search-input"
          placeholder="search for a song..."
          value={query}
          onChange={e => {
            setQuery(e.target.value)
            setSelected(null)
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

      {selected && (
        <div className="selected-track">
          {searching && <span className="spinner" />}
          {searching ? 'analyzing' : 'results for'} <strong>{selected.name}</strong> by {selected.artist}
        </div>
      )}

      {loadingPlaylists && (
        <div className="loading-row">
          <span className="spinner" />
          loading playlists…
        </div>
      )}

      {!loadingPlaylists && playlists.length === 0 && (
        <p className="empty-state">no playlists found</p>
      )}

      {playlists.length > 0 && (
        <div className="playlists">
          {playlists.map(playlist => {
            const isOpen = expanded === playlist.id
            const meta = playlistMeta[playlist.id] // undefined until job done (or seeded from cache)
            const pr = playlistResults[playlist.id]
            const mean = pr?.mean ?? null
            const top5 = pr?.top5 ?? null
            const isProcessing = !meta

            return (
              <div className={`playlist-card ${isOpen ? 'open' : ''}`} key={playlist.id}>
                <div className="playlist-row" onClick={() => toggleExpand(playlist.id)}>
                  <div className="playlist-info">
                    <span className="playlist-name">{playlist.name}</span>
                    <span className="playlist-track-count">
                      {isProcessing
                        ? <span className="spinner" style={{ display: 'inline-block' }} />
                        : `${meta.total_ingested}/${playlist.total_tracks} processed`}
                    </span>
                  </div>

                  <div className="playlist-score">
                    {searching ? (
                      <span className="spinner" />
                    ) : mean !== null ? (
                      <>
                        <span className="score-pill" style={scoreColor(mean)}>{mean}%</span>
                        {selected && (() => {
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
                      </>
                    ) : (
                      <span className="score-pill score-pill-empty">—</span>
                    )}
                    <span className={`chevron ${isOpen ? 'rotated' : ''}`}>▾</span>
                  </div>
                </div>

                <div className="playlist-details">
                  {isProcessing ? (
                    <p className="empty-state">processing tracks…</p>
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
                              <span className="top-track-score" style={{ color: scoreColor(r.score).color }}>{r.score}%</span>
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
                                <li key={i} className="top-track-item">
                                  <span className="top-track-rank" />
                                  <div className="top-track-meta">
                                    <span className="top-track-name">{r.name}</span>
                                    <span className="top-track-artist">{r.artist}</span>
                                  </div>
                                  <span className="top-track-score" style={{ color: scoreColor(r.score).color }}>
                                    {r.score}%
                                  </span>
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