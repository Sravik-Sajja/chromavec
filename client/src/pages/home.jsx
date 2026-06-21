import { useEffect, useRef, useState } from 'react'
import '../styles/home.css'

function Home() {
  const [playlists, setPlaylists] = useState([])
  const fetched = useRef(false)

  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)

  // per-playlist results: { [playlistId]: { top5, mean } }
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
      .then(data => setPlaylists(data.items))
      .catch(err => console.error(err))
  }, [])

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

    try {
      const res = await fetch('http://localhost:8000/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          track_id: track.id,
          track_name: track.name,
          artist_name: track.artist,
          playlists: playlists.map(p => ({
            playlist_id: p.id,
            track_ids: p.track_ids || [],
          })),
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

  return (
    <div className="home-page">
      <div className="home-header">
        <h1 className="home-logo">chroma<span>vec</span></h1>
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

      {playlists.length > 0 && (
        <div className="playlists">
          {playlists.map(playlist => {
            const isOpen = expanded === playlist.id
            const pr = playlistResults[playlist.id]
            const mean = pr?.mean ?? null
            const top5 = pr?.top5 ?? null

            return (
              <div className={`playlist-card ${isOpen ? 'open' : ''}`} key={playlist.id}>
                <div className="playlist-row" onClick={() => toggleExpand(playlist.id)}>
                  <div className="playlist-info">
                    <span className="playlist-name">{playlist.name}</span>
                    <span className="playlist-track-count">
                      {playlist.total_ingested != null
                        ? `${playlist.total_ingested}/${playlist.items?.total ?? '?'} processed`
                        : ''}
                    </span>
                  </div>

                  <div className="playlist-score">
                    {searching ? (
                      <span className="spinner" />
                    ) : mean !== null ? (
                      <span className="score-pill">{mean}%</span>
                    ) : (
                      <span className="score-pill score-pill-empty">—</span>
                    )}
                    <span className={`chevron ${isOpen ? 'rotated' : ''}`}>▾</span>
                  </div>
                </div>

                <div className="playlist-details">
                  {searching ? (
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
                              <span className="top-track-score">{r.score}%</span>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="empty-state">
                          {selected && !searching ? 'no ingested tracks in this playlist' : 'search a song to see matches'}
                        </p>
                      )}

                      {playlist.recommendations?.length > 0 && (
                        <div className="recommendations">
                          <p className="recommendations-label">you might also like</p>
                          <ul className="top-tracks">
                            {playlist.recommendations.map((r, i) => (
                              <li key={i} className="top-track-item">
                                <div className="top-track-meta">
                                  <span className="top-track-name">{r.name}</span>
                                  <span className="top-track-artist">{r.artist}</span>
                                </div>
                                <span className="top-track-score">{r.score}%</span>
                              </li>
                            ))}
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