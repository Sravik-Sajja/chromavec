import { createContext, useContext, useEffect, useRef, useState } from 'react'

const ProfileContext = createContext(null)

export function ProfileProvider({ children }) {
  const [profile, setProfile] = useState(null)
  const [loadingProfile, setLoadingProfile] = useState(true)
  const [profileError, setProfileError] = useState(false)
  const fetched = useRef(false)

  const fetchProfile = () => {
    setLoadingProfile(true)
    setProfileError(false)
    return fetch('http://localhost:8000/me')
      .then(res => {
        if (!res.ok) throw new Error('failed to load profile')
        return res.json()
      })
      .then(data => setProfile(data))
      .catch(() => setProfileError(true))
      .finally(() => setLoadingProfile(false))
  }

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true
    fetchProfile()
  }, [])

  return (
    <ProfileContext.Provider value={{ profile, loadingProfile, profileError, refetchProfile: fetchProfile }}>
      {children}
    </ProfileContext.Provider>
  )
}

export function useProfile() {
  const ctx = useContext(ProfileContext)
  if (!ctx) throw new Error('useProfile must be used within a ProfileProvider')
  return ctx
}