// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import { AuthGate } from './components/AuthGate'
import { installAuthFetch } from './lib/apiBase'
import './index.css'

// SEC-1: attach this session's credential to every backend request, before the
// first component mounts and therefore before the first fetch. In a browser
// this is a no-op — the session cookie from /auth/enter carries the credential
// instead.
installAuthFetch()

// AuthGate wraps App rather than sitting inside it: App's very first act is to
// fetch the onboarding status, which is itself an authenticated route. Gating
// below that point would just move the wall of errors one screen later.
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AuthGate>
      <App />
    </AuthGate>
  </React.StrictMode>,
)
