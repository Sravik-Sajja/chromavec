import '../styles/login.css'

function Login() {
  const handleLogin = () => {
    window.location.href = 'http://localhost:8000/login'
  }

  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="logo">playlistmatch</h1>
        <p className="tagline">music recommendations based on how your songs actually sound</p>
        <button className="spotify-btn" onClick={handleLogin}>
          Connect Spotify
        </button>
      </div>
    </div>
  )
}

export default Login