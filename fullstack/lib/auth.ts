// Authentication configuration placeholder
// In production, configure with better-auth or NextAuth

export interface Session {
  user: {
    id: string
    email: string
    name: string
    image?: string
  }
  expires: string
}

export interface User {
  id: string
  email: string
  name: string
  image?: string
}

// Mock auth functions for development
export function getSession(): Promise<Session | null> {
  return Promise.resolve(null)
}

export function getCurrentUser(): Promise<User | null> {
  return Promise.resolve(null)
}
