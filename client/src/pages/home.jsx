import { useEffect, useRef, useState } from 'react'
import '../styles/home.css'

function Home() {
  const [playlists, setPlaylists] = useState([])
  const fetched = useRef(false)

  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [showDropdown, setShowDropdown] = useState(false)

  const [results, setResults] = useState(null)
  const [mean, setMean] = useState(null)
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState(null)

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
      if (
        searchRef.current &&
        !searchRef.current.contains(event.target)
      ) {
        setShowDropdown(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)

    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  const handleSelect = async (track) => {
    setQuery(`${track.name} — ${track.artist}`)
    setShowDropdown(false)
    setSelected(track)
    setResults(null)
    setMean(null)
    setLoading(true)

    try {
      const res = await fetch('http://localhost:8000/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_name: track.name, artist_name: track.artist })
      })
      const data = await res.json()
      
      setResults(data.top5)
      setMean(data.mean)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="home-page">
      <h1>home</h1>

      <div className="search-container" ref={searchRef}>
        <input
          className="search-input"
          placeholder="search a song..."
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
                {track.name} — {track.artist}
              </div>
            ))}
          </div>
        )}
      </div>

      {loading && <p>analyzing track...</p>}

      {results && (
        <div className="results">
          <h2>closest matches</h2>
          {results.map((r, i) => (
            <p key={i}>{r.name} — {r.artist} ({r.score}%)</p>
          ))}
        </div>
      )}
      {mean && (
        <div className="mean-score">
          <h2>mean similarity</h2>
          <p>{mean}%</p>
        </div>
      )}

      <div className="playlists">
        {playlists.map(playlist => (
          <p key={playlist.id}>{playlist.name}</p>
        ))}
      </div>
    </div>
  )
}

export default Home