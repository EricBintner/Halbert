import { useEffect, useRef, useState, useCallback } from 'react'

export type WebSocketMessage = {
  type: 'system_status' | 'approval_request' | 'job_update' | 'decision' | 'chat_token' | 'chat_complete'
  data: any
}

export type ChatTokenData = {
  request_id: string
  token: string
  done: boolean
}

export type ChatCompleteData = {
  request_id: string
  response: string
  metadata?: Record<string, any>
}

type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

export function useWebSocket(onMessage?: (message: WebSocketMessage) => void) {
  const [status, setStatus] = useState<WebSocketStatus>('disconnected')
  const ws = useRef<WebSocket | null>(null)
  const reconnectTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(() => {
    const wsUrl = `ws://${window.location.host}/ws`
    
    setStatus('connecting')
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
      // Auto-reconnect after 3 seconds
      reconnectTimeout.current = setTimeout(connect, 3000)
    }
  }, [onMessage])

  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current)
      }
      ws.current?.close()
    }
  }, [connect])

  return { status, ws: ws.current }
}

/**
 * Hook specifically for chat streaming via WebSocket.
 * Use this in the chat interface for real-time token streaming.
 */
export function useChatStream(requestId: string | null) {
  const [tokens, setTokens] = useState<string[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [isComplete, setIsComplete] = useState(false)
  const [fullResponse, setFullResponse] = useState<string>('')

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === 'chat_token') {
      const data = message.data as ChatTokenData
      if (data.request_id === requestId) {
        setIsStreaming(true)
        setTokens(prev => [...prev, data.token])
        if (data.done) {
          setIsStreaming(false)
        }
      }
    } else if (message.type === 'chat_complete') {
      const data = message.data as ChatCompleteData
      if (data.request_id === requestId) {
        setFullResponse(data.response)
        setIsComplete(true)
        setIsStreaming(false)
      }
    }
  }, [requestId])

  const { status } = useWebSocket(handleMessage)

  // Reset state when requestId changes
  useEffect(() => {
    setTokens([])
    setIsStreaming(false)
    setIsComplete(false)
    setFullResponse('')
  }, [requestId])

  return {
    tokens,
    streamedText: tokens.join(''),
    fullResponse,
    isStreaming,
    isComplete,
    wsStatus: status
  }
}
