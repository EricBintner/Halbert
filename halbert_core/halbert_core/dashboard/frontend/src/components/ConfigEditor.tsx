/**
 * ConfigEditor - Full-screen config file editor overlay
 * 
 * Features:
 * - Monaco Editor for syntax-highlighted editing
 * - Integrated chat panel for AI assistance
 * - Backup management
 * - Session persistence
 */

import { useState, useEffect, useRef, Suspense, lazy } from 'react';
import { Save, History, ArrowLeft, AlertCircle, Check, Loader2 } from 'lucide-react';
import { Button } from './ui/button';
// Sheet components available if needed
// import { Sheet, SheetContent, SheetHeader, SheetTitle } from './ui/sheet';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

// Lazy load Monaco to reduce initial bundle size
const Editor = lazy(() => import('@monaco-editor/react'));

const API_BASE = '/api';

interface Backup {
  id: string;
  file_path: string;
  timestamp: number;
  label: string;
  size: number;
}

interface EditorSession {
  id: string;
  file_path: string;
  original_content: string;
  current_content: string;
  chat_history: any[];
  created_at: number;
  updated_at: number;
  status: string;
}

interface ConfigEditorProps {
  filePath: string;
  onClose: () => void;
}

export function ConfigEditor({ filePath, onClose }: ConfigEditorProps) {
  // Editor state
  const [content, setContent] = useState<string>('');
  const [originalContent, setOriginalContent] = useState<string>('');
  const [language, setLanguage] = useState<string>('plaintext');
  const [isDirty, setIsDirty] = useState(false);
  const [needsSudo, setNeedsSudo] = useState(false);
  
  // UI state
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  
  // Backups
  const [backups, setBackups] = useState<Backup[]>([]);
  const [_showBackups, setShowBackups] = useState(false);
  
  // Editor ref
  const editorRef = useRef<any>(null);
  
  // Load file on mount - properly sequence file and session loading
  useEffect(() => {
    const initEditor = async () => {
      await loadFile();
      loadBackups();
      // Load session after file so we can restore unsaved changes
      await loadSessionAndRestore();
    };
    initEditor();
  }, [filePath]);
  
  // Set config context for chat integration (Phase 18)
  useEffect(() => {
    // Create a stable reference to get current content
    const getContent = () => content;
    
    // Dispatch event to set config context
    window.dispatchEvent(new CustomEvent('halbert:set-config-context', {
      detail: { filePath, getContent }
    }));
    
    // Cleanup: clear config context when unmounting
    return () => {
      window.dispatchEvent(new CustomEvent('halbert:clear-config-context'));
    };
  }, [filePath]);
  
  // Update the getContent callback when content changes
  useEffect(() => {
    const getContent = () => content;
    window.dispatchEvent(new CustomEvent('halbert:set-config-context', {
      detail: { filePath, getContent }
    }));
  }, [content, filePath]);
  
  // Listen for apply-edit events from chat (Phase 18)
  useEffect(() => {
    const handleApplyEdit = (e: CustomEvent<{ search: string; replace: string }>) => {
      const { search, replace } = e.detail;
      
      // Apply the edit to the content
      if (content.includes(search)) {
        const newContent = content.replace(search, replace);
        setContent(newContent);
        setSuccessMessage('Edit applied successfully');
        setTimeout(() => setSuccessMessage(null), 3000);
      } else {
        setError('Could not find the text to replace. The file may have changed.');
        setTimeout(() => setError(null), 5000);
      }
    };
    
    window.addEventListener('halbert:apply-edit', handleApplyEdit as EventListener);
    return () => {
      window.removeEventListener('halbert:apply-edit', handleApplyEdit as EventListener);
    };
  }, [content]);
  
  // Auto-save session every 30 seconds
  useEffect(() => {
    if (!loading && content) {
      const interval = setInterval(() => {
        if (isDirty) {
          saveSession();
        }
      }, 30000);
      return () => clearInterval(interval);
    }
  }, [loading, content, isDirty]);
  
  // Track dirty state
  useEffect(() => {
    setIsDirty(content !== originalContent);
  }, [content, originalContent]);
  
  // Warn about unsaved changes before leaving
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (isDirty) {
        e.preventDefault();
        e.returnValue = 'You have unsaved changes. Are you sure you want to leave?';
        return e.returnValue;
      }
    };
    
    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [isDirty]);
  
  const loadFile = async () => {
    setLoading(true);
    setError(null);
    
    try {
      const res = await fetch(`${API_BASE}/editor/file?path=${encodeURIComponent(filePath)}`);
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to load file');
      }
      
      const data = await res.json();
      setContent(data.content);
      setOriginalContent(data.content);
      setLanguage(data.language);
      setNeedsSudo(data.needs_sudo);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };
  
  const loadBackups = async () => {
    try {
      const res = await fetch(`${API_BASE}/editor/backups?path=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const data = await res.json();
        setBackups(data);
      }
    } catch (err) {
      console.error('Failed to load backups:', err);
    }
  };
  
  const loadSessionAndRestore = async () => {
    try {
      const res = await fetch(`${API_BASE}/editor/session?path=${encodeURIComponent(filePath)}`);
      if (res.ok) {
        const session = await res.json();
        if (session && session.current_content && session.current_content !== session.original_content) {
          // There's an unsaved session - auto-restore with notification
          setContent(session.current_content);
          setSuccessMessage('Restored unsaved changes from previous session');
          setTimeout(() => setSuccessMessage(null), 4000);
        }
      }
    } catch (err) {
      console.error('Failed to load session:', err);
    }
  };
  
  const saveSession = async () => {
    try {
      const session: EditorSession = {
        id: filePath.replace(/\//g, '_'),
        file_path: filePath,
        original_content: originalContent,
        current_content: content,
        chat_history: [], // TODO: integrate with chat
        created_at: Date.now() / 1000,
        updated_at: Date.now() / 1000,
        status: 'editing',
      };
      
      await fetch(`${API_BASE}/editor/session`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(session),
      });
    } catch (err) {
      console.error('Failed to save session:', err);
    }
  };
  
  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccessMessage(null);
    
    try {
      const res = await fetch(`${API_BASE}/editor/file`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath,
          content: content,
          create_backup: true,
          backup_label: 'Before save',
        }),
      });
      
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to save file');
      }
      
      setOriginalContent(content);
      setSuccessMessage('File saved successfully');
      loadBackups(); // Refresh backup list
      
      // Clear session since we saved
      await fetch(`${API_BASE}/editor/session?path=${encodeURIComponent(filePath)}`, {
        method: 'DELETE',
      });
      
      setTimeout(() => setSuccessMessage(null), 3000);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };
  
  const handleCreateBackup = async () => {
    try {
      const res = await fetch(`${API_BASE}/editor/backup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path: filePath,
          label: 'Manual backup',
        }),
      });
      
      if (res.ok) {
        loadBackups();
        setSuccessMessage('Backup created');
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err) {
      console.error('Failed to create backup:', err);
    }
  };
  
  const handleRestoreBackup = async (backupId: string) => {
    if (!window.confirm('Restore this backup? Current content will be replaced.')) {
      return;
    }
    
    try {
      // Get backup content
      const res = await fetch(
        `${API_BASE}/editor/backup/${backupId}/content?path=${encodeURIComponent(filePath)}`
      );
      if (res.ok) {
        const data = await res.json();
        setContent(data.content);
        setShowBackups(false);
        setSuccessMessage('Backup restored to editor (not saved yet)');
        setTimeout(() => setSuccessMessage(null), 3000);
      }
    } catch (err) {
      console.error('Failed to restore backup:', err);
    }
  };
  
  const handleClose = () => {
    if (isDirty) {
      const confirm = window.confirm('You have unsaved changes. Close anyway?');
      if (!confirm) return;
    }
    onClose();
  };
  
  const handleEditorMount = (editor: any, monaco: any) => {
    editorRef.current = editor;
    
    // Add Ctrl+S shortcut
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
      handleSave();
    });
  };
  
  const formatTimestamp = (ts: number) => {
    return new Date(ts * 1000).toLocaleString();
  };
  
  return (
    <div className="flex flex-col h-full -m-8">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-4 py-2 border-b bg-muted/50">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={handleClose}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
          
          <div className="flex items-center gap-2 text-sm">
            {/* Unsaved dot indicator - standard UX pattern */}
            {isDirty && (
              <span className="w-2 h-2 bg-yellow-500 rounded-full" title="Unsaved changes" />
            )}
            <span className="font-mono text-muted-foreground">{filePath}</span>
            {needsSudo && (
              <span className="text-xs bg-orange-500/20 text-orange-500 px-1.5 py-0.5 rounded">
                sudo
              </span>
            )}
            {isDirty && (
              <span className="text-xs bg-yellow-500/20 text-yellow-500 px-1.5 py-0.5 rounded">
                unsaved
              </span>
            )}
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {/* Backups dropdown */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm">
                <History className="h-4 w-4 mr-1" />
                Backups ({backups.length})
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem onClick={handleCreateBackup}>
                + Create Backup Now
              </DropdownMenuItem>
              {backups.length > 0 && <div className="border-t my-1" />}
              {backups.slice(0, 10).map((backup) => (
                <DropdownMenuItem
                  key={backup.id}
                  onClick={() => handleRestoreBackup(backup.id)}
                  className="flex flex-col items-start"
                >
                  <span className="text-xs text-muted-foreground">
                    {formatTimestamp(backup.timestamp)}
                  </span>
                  <span className="text-sm">{backup.label}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
          
          {/* Save button */}
          <Button
            onClick={handleSave}
            disabled={saving || !isDirty}
            size="sm"
          >
            {saving ? (
              <Loader2 className="h-4 w-4 mr-1 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-1" />
            )}
            Save
          </Button>
        </div>
      </div>
      
      {/* Status messages */}
      {error && (
        <div className="px-4 py-2 bg-destructive/20 text-destructive flex items-center gap-2">
          <AlertCircle className="h-4 w-4" />
          {error}
        </div>
      )}
      {successMessage && (
        <div className="px-4 py-2 bg-green-500/20 text-green-500 flex items-center gap-2">
          <Check className="h-4 w-4" />
          {successMessage}
        </div>
      )}
      
      {/* Editor area */}
      <div className="flex-1 flex">
        {/* Monaco Editor */}
        <div className="flex-1">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <Suspense
              fallback={
                <div className="flex items-center justify-center h-full">
                  <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              }
            >
              <Editor
                height="100%"
                language={language}
                value={content}
                onChange={(value: string | undefined) => setContent(value || '')}
                onMount={handleEditorMount}
                theme="vs-dark"
                options={{
                  minimap: { enabled: false },
                  lineNumbers: 'on',
                  wordWrap: 'on',
                  fontSize: 14,
                  automaticLayout: true,
                  scrollBeyondLastLine: false,
                  padding: { top: 16 },
                }}
              />
            </Suspense>
          )}
        </div>
      </div>
      
      {/* Status bar */}
      <div className="px-4 py-1 border-t bg-muted/50 text-xs text-muted-foreground flex items-center gap-4">
        <span>{language.toUpperCase()}</span>
        <span>UTF-8</span>
        {editorRef.current && (
          <span>
            Ln {editorRef.current.getPosition()?.lineNumber || 1}, 
            Col {editorRef.current.getPosition()?.column || 1}
          </span>
        )}
      </div>
    </div>
  );
}

export default ConfigEditor;
