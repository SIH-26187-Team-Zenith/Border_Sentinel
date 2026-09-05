// src/api/auth.js
// Matches backend/app/api/routes/auth.py exactly:
//   POST /auth/login  {email, password} -> {access_token, token_type}
//   GET  /auth/me                       -> {id, email, role}
import { api } from './client'

export function login(email, password) {
  return api.post('/auth/login', { email, password })
}

export function fetchMe() {
  return api.get('/auth/me')
}
