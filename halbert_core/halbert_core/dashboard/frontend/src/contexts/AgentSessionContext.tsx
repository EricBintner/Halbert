/**
 * Agent Session Context
 * 
 * Provides shared session state that survives component unmounts (tab switches).
 * Based on research6-session-management.md.
 */

import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';

// -----------------------------------------------------------------------------
// Types
// -----------------------------------------------------------------------------

export type AgentState = 
  | 'idle' 
  | 'planning' 
  | 'searching' 
  | 'reading'
  | 'executing' 
  | 'observing' 
  | 'responding'
  | 'awaiting_confirmation' 
  | 'error';

export interface AgentMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  state?: AgentState;
  isStreaming?: boolean;
}

export interface PlanStep {
  step: string;
  tool?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
}

export interface ContextItem {
  id: string;
  source: string;
  label: string;
  count: number;
  tokens?: number;
}

export interface AgentSessionData {
  sessionId: string;
  state: AgentState;
  messages: AgentMessage[];
  plan: PlanStep[];
  confidence: number;
  contextItems: ContextItem[];
  response: string;
  thinking: string;
  isStreaming: boolean;
  error: string | null;
  createdAt: number;
  updatedAt: number;
}

interface AgentSessionContextType {
  // Current session
  activeSessionId: string | null;
  sessions: Map<string, AgentSessionData>;
  
  // Session management
  createSession: () => string;
  getSession: (sessionId: string) => AgentSessionData | undefined;
  setActiveSession: (sessionId: string) => void;
  deleteSession: (sessionId: string) => void;
  
  // Session state updates
  updateSessionState: (sessionId: string, state: AgentState) => void;
  addMessage: (sessionId: string, message: AgentMessage) => void;
  updateResponse: (sessionId: string, response: string) => void;
  appendResponse: (sessionId: string, chunk: string) => void;
  setPlan: (sessionId: string, plan: PlanStep[]) => void;
  setConfidence: (sessionId: string, confidence: number) => void;
  setContextItems: (sessionId: string, items: ContextItem[]) => void;
  setStreaming: (sessionId: string, isStreaming: boolean) => void;
  setError: (sessionId: string, error: string | null) => void;
  resetSession: (sessionId: string) => void;
  
  // Convenience getters for active session
  activeSession: AgentSessionData | null;
}

const AgentSessionContext = createContext<AgentSessionContextType | null>(null);

// -----------------------------------------------------------------------------
// Storage Keys
// -----------------------------------------------------------------------------

const STORAGE_KEY = 'halbert_agent_sessions';
const ACTIVE_SESSION_KEY = 'halbert_active_agent_session';

// -----------------------------------------------------------------------------
// Provider
// -----------------------------------------------------------------------------

export function AgentSessionProvider({ children }: { children: ReactNode }) {
  const [sessions, setSessions] = useState<Map<string, AgentSessionData>>(() => {
    // Load from localStorage on init
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        return new Map(parsed);
      }
    } catch (e) {
      console.warn('Failed to load agent sessions from storage:', e);
    }
    return new Map();
  });
  
  const [activeSessionId, setActiveSessionId] = useState<string | null>(() => {
    return localStorage.getItem(ACTIVE_SESSION_KEY);
  });

  // Persist to localStorage on changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(sessions.entries())));
    } catch (e) {
      console.warn('Failed to save agent sessions to storage:', e);
    }
  }, [sessions]);

  useEffect(() => {
    if (activeSessionId) {
      localStorage.setItem(ACTIVE_SESSION_KEY, activeSessionId);
    } else {
      localStorage.removeItem(ACTIVE_SESSION_KEY);
    }
  }, [activeSessionId]);

  // Create new session
  const createSession = useCallback(() => {
    const sessionId = `agent-${Date.now()}`;
    const newSession: AgentSessionData = {
      sessionId,
      state: 'idle',
      messages: [],
      plan: [],
      confidence: 0,
      contextItems: [],
      response: '',
      thinking: '',
      isStreaming: false,
      error: null,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    
    setSessions(prev => {
      const next = new Map(prev);
      next.set(sessionId, newSession);
      return next;
    });
    
    setActiveSessionId(sessionId);
    return sessionId;
  }, []);

  // Get session by ID
  const getSession = useCallback((sessionId: string) => {
    return sessions.get(sessionId);
  }, [sessions]);

  // Set active session
  const setActiveSession = useCallback((sessionId: string) => {
    if (sessions.has(sessionId)) {
      setActiveSessionId(sessionId);
    }
  }, [sessions]);

  // Delete session
  const deleteSession = useCallback((sessionId: string) => {
    setSessions(prev => {
      const next = new Map(prev);
      next.delete(sessionId);
      return next;
    });
    
    if (activeSessionId === sessionId) {
      // Switch to another session or null
      const remaining = Array.from(sessions.keys()).filter(id => id !== sessionId);
      setActiveSessionId(remaining.length > 0 ? remaining[0] : null);
    }
  }, [activeSessionId, sessions]);

  // Update session state
  const updateSessionState = useCallback((sessionId: string, state: AgentState) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, state, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Add message
  const addMessage = useCallback((sessionId: string, message: AgentMessage) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, {
        ...session,
        messages: [...session.messages, message],
        updatedAt: Date.now(),
      });
      return next;
    });
  }, []);

  // Update response (replace)
  const updateResponse = useCallback((sessionId: string, response: string) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, response, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Append to response (streaming)
  const appendResponse = useCallback((sessionId: string, chunk: string) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, {
        ...session,
        response: session.response + chunk,
        updatedAt: Date.now(),
      });
      return next;
    });
  }, []);

  // Set plan
  const setPlan = useCallback((sessionId: string, plan: PlanStep[]) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, plan, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Set confidence
  const setConfidence = useCallback((sessionId: string, confidence: number) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, confidence, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Set context items
  const setContextItems = useCallback((sessionId: string, items: ContextItem[]) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, contextItems: items, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Set streaming state
  const setStreaming = useCallback((sessionId: string, isStreaming: boolean) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, isStreaming, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Set error
  const setError = useCallback((sessionId: string, error: string | null) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, { ...session, error, updatedAt: Date.now() });
      return next;
    });
  }, []);

  // Reset session (clear response, plan, etc. but keep messages)
  const resetSession = useCallback((sessionId: string) => {
    setSessions(prev => {
      const session = prev.get(sessionId);
      if (!session) return prev;
      
      const next = new Map(prev);
      next.set(sessionId, {
        ...session,
        state: 'idle',
        plan: [],
        confidence: 0,
        contextItems: [],
        response: '',
        thinking: '',
        isStreaming: false,
        error: null,
        updatedAt: Date.now(),
      });
      return next;
    });
  }, []);

  // Active session getter
  const activeSession = activeSessionId ? sessions.get(activeSessionId) || null : null;

  return (
    <AgentSessionContext.Provider value={{
      activeSessionId,
      sessions,
      createSession,
      getSession,
      setActiveSession,
      deleteSession,
      updateSessionState,
      addMessage,
      updateResponse,
      appendResponse,
      setPlan,
      setConfidence,
      setContextItems,
      setStreaming,
      setError,
      resetSession,
      activeSession,
    }}>
      {children}
    </AgentSessionContext.Provider>
  );
}

// -----------------------------------------------------------------------------
// Hook
// -----------------------------------------------------------------------------

export function useAgentSession() {
  const context = useContext(AgentSessionContext);
  if (!context) {
    throw new Error('useAgentSession must be used within an AgentSessionProvider');
  }
  return context;
}
