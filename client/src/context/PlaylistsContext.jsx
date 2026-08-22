import { createContext, useContext, useEffect, useRef, useState } from 'react'

const PlaylistsContext = createContext(null)

export function PlaylistsProvider({ children }) {
  const [playlists, setPlaylists] = useState([])
  const [playlistMeta, setPlaylistMeta] = useState({}) // { [id]: { total_ingested, recommendations, track_ids } }
  const [loadingPlaylists, setLoadingPlaylists] = useState(true)
  const fetched = useRef(false)

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true

    fetch('http://localhost:8000/playlists')
      .then(res => res.json())
      .then(data => {
        setPlaylists(data.items)

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

  return (
    <PlaylistsContext.Provider value={{ playlists, playlistMeta, setPlaylistMeta, loadingPlaylists }}>
      {children}
    </PlaylistsContext.Provider>
  )
}

export function usePlaylists() {
  const ctx = useContext(PlaylistsContext)
  if (!ctx) throw new Error('usePlaylists must be used within a PlaylistsProvider')
  return ctx
}