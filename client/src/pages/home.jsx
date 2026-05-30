import { useEffect, useState } from 'react'

function Home() {
  const [playlists, setPlaylists] = useState([])

  useEffect(() => {
    fetch('http://localhost:8000/playlists')
      .then(res => res.json())
      .then(data => setPlaylists(data.items))
      .catch(err => console.error(err))
  }, [])

  return (
    <div>
      <h1>home</h1>
      {playlists.map(playlist => (
        <p key={playlist.id}>{playlist.name}</p>
      ))}
    </div>
  )
}

export default Home