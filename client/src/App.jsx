import { BrowserRouter, Routes, Route, Outlet } from 'react-router-dom'
import Home from './pages/Home'
import Login from './pages/login'
import Profile from './pages/profile'
import { PlaylistsProvider } from './context/PlaylistsContext'
import { ProfileProvider } from './context/ProfileContext'

function AppLayout() {
  return (
    <PlaylistsProvider>
      <ProfileProvider>
        <Outlet />
      </ProfileProvider>
    </PlaylistsProvider>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route element={<AppLayout />}>
          <Route path="/home" element={<Home />} />
          <Route path="/profile" element={<Profile />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App