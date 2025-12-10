import { useEffect, useRef, useState } from 'react'

type WebSocketMessage = {
  type: 'system_status' | 'approval_request' | 'job_update' | 'decision'
  data: any
}

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export function useWebSocket(onMessage?: (message: WebSocketMessage) => void) {
  const [status, setStatus] = useState<WebSocketStatus>('disconnected')
  const ws = useRef<WebSocket | null>(null)

  useEffect(() => {
    const wsUrl = `ws://${window.location.host}/ws`
    
    ws.current = new WebSocket(wsUrl)

    ws.current.onopen = () => {
      setStatus('connected')
      console.log('WebSocket connected')
    }

    ws.current.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data)
        onMessage?.(message)
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    ws.current.onerror = () => {
      setStatus('error')
    }

    ws.current.onclose = () => {
      setStatus('disconnected')
      console.log('WebSocket disconnected')
    }

    return () => {
      ws.current?.close()
    }
  }, [onMessage])

  return { status, ws: ws.current }
}
