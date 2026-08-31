// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2024-2026 Eric Bintner and Halbert Contributors
/**
 * AgentChat Component
 *
 * Cascade-style chat that renders structured agent events.
 * Based on research2.md state machine workflow.
 *
 * Phase 59: Enhanced with Chat feature parity:
 * - @mention autocomplete
 * - Vision/image support (drag/drop/paste)
 * - Message queue (type while busy)
 * - Code block rendering with run buttons
 * - Model loading status
 */

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Send,
  StopCircle,
  RotateCcw,
  AtSign,
  Terminal,
  Image as ImageIcon,
  X as XIcon,
  Camera,
  ArrowDown,
} from 'lucide-react';
import { useAgentStream, type AgentSession, type AgentState } from '../../hooks/useAgentStream';
import { useTimeline, type UseTimelineReturn } from '../../hooks/useTimeline';
import { useHostIdentity } from '../../hooks/useHostIdentity';
import { useInstanceVariant } from '../../hooks/useInstanceVariant';
import { StateBadge } from './StateBadge';
import { PlanChecklist } from './PlanChecklist';
import { ToolExecutionCard } from './ToolExecutionCard';
import { ConfirmationDialog } from './ConfirmationDialog';
import { ThinkingPanel } from './ThinkingPanel';
import { WhyChip, type ProvenanceRef } from '../WhyChip';
import { ModuleRenderer } from '../ModuleRenderer';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { ChatModelPill } from '../llm/ChatModelPill';
import { ModelStatusCard } from '../llm/ModelStatusCard';
import { TurnModelNotice } from '../llm/TurnModelNotice';
import { ModalityHandoffBadge, VoiceCompanionPill } from '../audio';
import { useModelPicker, matchModels, providerDescriptor } from '@halbert/model-picker';
import { CHAT_ROLE_ID, halbertRolesForVariant, modelPickerTransport } from '@/lib/halbertModelRoles';
import { parseModelCommand, formatModelStatus, type ModelStatusLines } from '@/lib/slashCommands';
import { ScanBlock } from './ScanBlock';
import { ContextBar, type ContextItem, type ContextType } from './ContextBar';
import { DiffBlock } from './DiffBlock';
import { HostGreeting } from './HostGreeting';
import { InlineTerminals } from './InlineTerminals';
import { MessageContent } from './MessageContent';
import { Timeline } from './Timeline';
import { CurrentTopicLabel } from './CurrentTopicLabel';
import { cn } from '../../lib/utils';
import { api } from '../../lib/api';
import { subscribeHost } from '../../lib/hostConversation';
import { announce } from '../../lib/announce';
import { turnFromSession } from '../../lib/turnFromSession';
import type { TimelineTurn } from '../../types/timeline';

interface UserMessage {
  id: string;
  content: string;
  timestamp: number;
  images?: string[];  // Base64 image data
}

/**
 * An ephemeral note the composer itself puts in the stream — the answer to a
 * `/model` command. It never reaches the backend and is not part of the
 * conversation the agent sees.
 */
interface SystemNotice {
  id: string;
  timestamp: number;
  text?: string;
  status?: ModelStatusLines;
  tone: 'info' | 'warning';
}

interface AttachedImage {
  id: string;
  dataUrl: string;
  name: string;
}

interface Mentionable {
  id: string;
  mention: string;
  name: string;
  type: string;
}

/**
 * How often this surface re-reads the host's identity.
 *
 * It wants one field — the name the conversation is with — and a machine's
 * name effectively never changes. `useHostIdentity` polls once for every
 * consumer at the shortest period any of them asked for, so a slow ask here
 * costs nothing; the same number the mode switch uses, for the same reason.
 */
const NAME_POLL_MS = 60_000;

interface AgentChatProps {
  className?: string;
  onRunCommand?: (cmd: string) => Promise<{output?: string, error?: string, exit_code?: number}>;
  /** Opens Settings -> AI Models from the quick-switch footer. */
  onOpenModelSettings?: () => void;
}

/**
 * What each agent state is called when it is announced, for a screen reader
 * following a turn it cannot watch. States happen at most a handful of times
 * per turn — never per token — so the whole map is one short sentence each.
 *
 * Two states deliberately have no sentence here, because something else
 * already says them exactly once: `awaiting_confirmation` is said
 * assertively by the hook (design §11 reserves the assertive region for
 * blocked-on-approval), and `error` is the agentError banner, which the
 * effect below announces. Repeating either here would double it.
 */
const STATE_ANNOUNCEMENTS: Partial<Record<AgentState, string>> = {
  planning: 'Planning response',
  searching: 'Searching knowledge base',
  reading: 'Reading files',
  executing: 'Executing tool',
  observing: 'Observing results',
  reflecting: 'Reflecting on results',
  responding: 'Responding',
};

/** DOM id of the mention popup, so the composer can point at it. */
const MENTION_LISTBOX_ID = 'mention-listbox';

// -----------------------------------------------------------------------------
// Provenance ref → module parsing (Phase 8 / T8a.3)
//
// Ref strings arrive from the backend in free-form shapes. Parse defensively:
// accept a JSON object, "source@cursor" / "source:cursor" for log refs, and
// "path:start-end" / "path:line" suffixes for path refs. Fall back to treating
// the whole ref as the source/path.
// -----------------------------------------------------------------------------

interface ExpandedProvenanceModule {
  key: string;
  label: string;
  module: string;
  props: Record<string, any>;
}

function parseLogRef(ref: string): { source?: string; cursor?: string } {
  try {
    const parsed = JSON.parse(ref);
    if (parsed && typeof parsed === 'object') {
      return {
        source: parsed.source ?? parsed.log ?? parsed.unit ?? parsed.service,
        cursor: parsed.cursor ?? parsed.pos ?? parsed.offset,
      };
    }
  } catch { /* not JSON */ }
  const atIdx = ref.indexOf('@');
  if (atIdx > 0) return { source: ref.slice(0, atIdx), cursor: ref.slice(atIdx + 1) };
  const colonIdx = ref.indexOf(':');
  if (colonIdx > 0) return { source: ref.slice(0, colonIdx), cursor: ref.slice(colonIdx + 1) };
  return { source: ref };
}

function parsePathRef(ref: string): { path?: string } {
  try {
    const parsed = JSON.parse(ref);
    if (parsed && typeof parsed === 'object') {
      const path = parsed.path ?? parsed.file ?? parsed.filename;
      if (typeof path === 'string') return { path };
    }
  } catch { /* not JSON */ }
  // Strip a trailing ":N" or ":N-M" line-range suffix, but only when what
  // precedes it looks like a path (avoids mangling "C:\..."-style strings).
  const m = ref.match(/^(.+?\/.*?):(\d+)(?:-(\d+))?$/);
  if (m) return { path: m[1] };
  return { path: ref };
}

/** Where a context_loaded item came from -> which chip to draw. */
function contextTypeFor(source: string): ContextType {
  switch (source) {
    case 'file': return 'file';
    case 'memory': return 'memory';
    case 'thread': return 'thread';
    default: return 'search';
  }
}

export function AgentChat({ className, onRunCommand, onOpenModelSettings }: AgentChatProps) {
  // The turn in flight. Once it finishes it is appended to the timeline
  // (turnFromSession) and this goes back to null — never both at once.
  const [liveUser, setLiveUser] = useState<UserMessage | null>(null);
  const cancelledRef = useRef(false);
  const appendedRef = useRef<string | null>(null);
  // The per-turn model pin. Deliberately component state and never persisted:
  // a pin governs this conversation only, while the settings drawer is what
  // changes the stored default.
  // One picker for the whole composer: the pill shows it and `/model` drives
  // it. Two would let the command and the control disagree about what is
  // pinned. The pin lives here and is never persisted.
  // The roles are filtered to this instance's variant before the picker sees
  // them — a home instance offers no secure slot, and the picker package
  // cannot know that without breaking its no-role-names rule. An unknown
  // variant keeps the full set, so a failed info route never empties the
  // composer's model control.
  const variant = useInstanceVariant();
  // A home node is a pure client of the workstation's compute
  // endpoint: no model is chosen here, so the composer carries no model
  // control at all. Hidden rather than rendered read-only — the pill's whole
  // job is choosing between models, its status is derived from a local model
  // listing that does not exist on this node, and a read-only variant would
  // need a new seam in a package that knows no peer provider. The settings
  // AI tab's ComputePeerCard is the one surface where the link lives.
  // An unknown variant keeps the pill, same fail-open as the role filter.
  const peerGovernedVariant = variant === 'home';
  const variantRoles = useMemo(
    () => halbertRolesForVariant(variant),
    [variant],
  );
  const picker = useModelPicker({
    transport: modelPickerTransport,
    roles: variantRoles,
  });
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState<string | undefined>(undefined);
  const [systemNotices, setSystemNotices] = useState<SystemNotice[]>([]);
  const [input, setInput] = useState('');
  const [agentError, setAgentError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  // Whether the user is near the bottom of the scroll container. Auto-scroll
  // only fires when this is true, so scrolling up to read an old answer
  // during streaming is not yanked away on every token. The threshold is
  // 100px — generous enough for sub-pixel rounding, tight enough that the
  // user doesn't have to scroll all the way to the last pixel to re-pin.
  const [isAtBottom, setIsAtBottom] = useState(true);

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setIsAtBottom(distanceFromBottom < 100);
  }, []);

  /**
   * Drain requests parked by the dashboard bridge.
   *
   * The prefill is placed in the composer and NOT sent: a staged command must
   * be readable before it runs, and an "ask about this" should still be the
   * user's sentence. Anything queued before this mounted arrives here too, so
   * the mode flip does not drop it.
   */
  useEffect(() => subscribeHost((request) => {
    if (request.prefill) {
      setInput(request.prefill);
    } else if (request.itemId) {
      setInput((current) => `${current}@${request.itemId} `);
    }
    inputRef.current?.focus();
  }), []);

  // One conversation, stored server-side; paged here.
  const {
    turns,
    hasMore,
    loading: timelineLoading,
    loadOlder,
    loadAround,
    loadLatest,
    anchored,
    appendLive,
    loadFailed,
    currentThread,
    setCurrentThread,
    byDay,
  } = useTimeline();

  /**
   * Who the conversation is with, for the feed's accessible name.
   *
   * `display_name` is the name chosen in onboarding — what this machine is
   * called. Never `hostname`, which is a DNS fact about the machine and not
   * its name. Until it resolves, Timeline falls back to a bare
   * "Conversation"; a feed that named itself after nothing would be worse.
   *
   * The period is deliberate and matches the mode switch: a machine's name
   * effectively never changes, and `useHostIdentity` runs ONE shared request
   * loop at the shortest period any mounted consumer asked for — so asking
   * slowly here adds a consumer, not a second poll.
   */
  const { identity } = useHostIdentity(NAME_POLL_MS);

  // Phase 59: @mention autocomplete
  const [mentionables, setMentionables] = useState<Mentionable[]>([]);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  // The option the arrow keys (and Enter) act on while the popup is open.
  const [activeMentionIndex, setActiveMentionIndex] = useState(0);

  // Phase 59: Vision/image support
  const [attachedImages, setAttachedImages] = useState<AttachedImage[]>([]);
  const [isDraggingImage, setIsDraggingImage] = useState(false);

  // Phase 59: Message queue (type while busy)
  const [messageQueue, setMessageQueue] = useState<string[]>([]);

  // Phase 8 / T8a.3: modules expanded from provenance WhyChip clicks
  const [expandedProvenanceModules, setExpandedProvenanceModules] = useState<ExpandedProvenanceModule[]>([]);

  const {
    session,
    isStreaming,
    response,
    thinking,
    provenance,
    moduleInvocations,
    turnModel,
    sendMessage,
    confirmAction,
    applyDiff,
    rejectDiff,
    cancel,
    reset,
    dismissContextItem,
  } = useAgentStream({
    onStateChange: (state, prev) => {
      console.log('State:', prev, '->', state);
      // Progress a screen reader can follow. The feed is not a live region,
      // so without this the agent's work happens in silence for anyone not
      // watching the screen.
      const said = STATE_ANNOUNCEMENTS[state];
      if (said) announce(said);
    },
    onToolStart: (tool, args) => {
      console.log('Tool start:', tool, args);
    },
    onError: (err) => {
      console.error('Agent error:', err);
      setAgentError(err);
    },
  });

  // Announce agent errors assertively so screen-reader users know a retry
  // button is available. The banner is visual-only without this.
  useEffect(() => {
    if (agentError) {
      announce(agentError, { assertive: true });
    }
  }, [agentError]);

  // Whether the turn that just stopped streaming was stopped by the admin:
  // the Stop button says "Stopped" itself, so the end-of-turn sentence below
  // must not talk over it. A ref rather than cancelledRef because the fold
  // effect resets that one as part of finishing the turn.
  const stoppedRef = useRef(false);
  const wasStreamingRef = useRef(false);
  useEffect(() => {
    const ended = wasStreamingRef.current && !isStreaming;
    wasStreamingRef.current = isStreaming;
    if (!ended) return;
    if (stoppedRef.current) {
      stoppedRef.current = false;
      return;
    }
    // Everything with a sentence of its own stays out of this one's way:
    // the error banner (above), and a turn parked on an approval or an
    // undecided proposal, which has not finished — it is waiting.
    if (agentError) return;
    if (session?.pendingConfirmation || session?.state === 'awaiting_confirmation') return;
    if (session?.diffProposals.some((diff) => diff.status === 'pending')) return;
    // A queued question is about to be sent; it says so next, and two
    // sentences in one breath would eat each other.
    if (messageQueue.length > 0) return;
    announce('Reply finished');
  }, [isStreaming, agentError, session, messageQueue.length]);

  // Load mentionables on mount
  useEffect(() => {
    const loadMentionables = async () => {
      try {
        const data = await api.getMentionables();
        setMentionables(data.mentionables || []);
      } catch (error) {
        console.error('Failed to load mentionables:', error);
      }
    };
    loadMentionables();
  }, []);

  // Listen for screenshots captured by Layout.tsx (the camera button
  // dispatches halbert:capture-screenshot, Layout captures and dispatches
  // halbert:add-screenshot with the base64 data). Without this listener the
  // screenshot is captured and then dropped on the floor.
  useEffect(() => {
    const handleAddScreenshot = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.dataUrl) {
        setAttachedImages(prev => [...prev, {
          id: 'screenshot-' + Date.now(),
          dataUrl: detail.dataUrl,
          name: detail.name || 'Screenshot',
        }]);
      }
    };
    const handleScreenshotError = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      const msg = detail?.error || 'Screenshot failed';
      // Surface the error to the user. If screen capture is disabled,
      // the message tells them exactly where to enable it.
      setAgentError(detail?.errorType === 'disabled'
        ? 'Screen capture is disabled. Enable it in Settings > Vision.'
        : `Screenshot failed: ${msg}`);
      setTimeout(() => setAgentError(null), 5000);
    };
    window.addEventListener('halbert:add-screenshot', handleAddScreenshot);
    window.addEventListener('halbert:screenshot-error', handleScreenshotError);
    return () => {
      window.removeEventListener('halbert:add-screenshot', handleAddScreenshot);
      window.removeEventListener('halbert:screenshot-error', handleScreenshotError);
    };
  }, []);

  // Everything the fold below needs, one assignment fresh. The fold runs
  // from three places and one of them (the queued-send timeout) reads a
  // closure that is a render behind, so it must not read those values
  // directly. Declared ABOVE the fold effect so this refresh runs first in
  // the same commit.
  const foldInputs = useRef<{
    liveUser: UserMessage | null;
    session: AgentSession | null;
    response: string;
    anchored: boolean;
    appendLive: (turn: TimelineTurn) => void;
    // Taken from the hook rather than restated, so widening what `loadLatest`
    // answers with is one edit and not a type error here as well.
    loadLatest: UseTimelineReturn['loadLatest'];
  }>({ liveUser, session, response, anchored, appendLive, loadLatest });
  useEffect(() => {
    foldInputs.current = { liveUser, session, response, anchored, appendLive, loadLatest };
  });

  // Put the turn that is on screen into the transcript, as it stands.
  //
  // Idempotent (`appendedRef`), so the three callers cannot double-append:
  // the effect below when a turn simply finishes, and handleSend / the
  // queued-send timeout before a new turn takes liveUser's place. That last
  // pair is not belt-and-braces. A turn parked on an undecided proposal
  // keeps liveUser; the next question replaces it and sendMessage starts a
  // fresh session, taking session.diffProposals with it — so without this
  // the question, the reply and the proposal all left the page at once,
  // with no decision recorded anywhere the admin can see. Folding it first
  // keeps the exchange, with the proposal recorded read-only as what it is:
  // proposed, never answered.
  const foldLiveTurn = useCallback(() => {
    const { liveUser: live, session: current, response: text, anchored: away } = foldInputs.current;
    if (!live || !current) return;
    const turn = turnFromSession(current, live, text, { cancelled: cancelledRef.current });
    if (appendedRef.current === turn.turnId) return;
    appendedRef.current = turn.turnId;
    if (away) {
      // appendLive is a documented no-op on an anchored window (the turn
      // would assert an adjacency that is false), so appending here would
      // simply lose the exchange the admin just had until they found the
      // "Back to latest" button. Go back to the tail instead: the turn is
      // already stored, and the newest page has it.
      void foldInputs.current.loadLatest();
    } else {
      foldInputs.current.appendLive(turn);
    }
  }, []);

  // The finished turn becomes a stored turn. Guarded so a turn still waiting
  // on the admin is not folded away early, and so one turn is appended once.
  //
  // Two things park a turn. A confirmation prompt (stream closed, session
  // waiting) is the obvious one. A diff the agent proposed and nobody has
  // answered is the same situation: the timeline renders stored diffs
  // read-only (Timeline.tsx), because a past turn must not act on a session
  // that no longer exists — so folding a pending proposal in would degrade
  // Apply/Reject to the word "proposed" the instant the reply finished, with
  // the backend still perfectly willing to carry out the decision. It stays
  // live until applyDiff/rejectDiff resolves it, and this effect re-runs.
  useEffect(() => {
    if (isStreaming || !liveUser || !session) return;
    if (session.pendingConfirmation || session.state === 'awaiting_confirmation') return;
    if (session.diffProposals.some((diff) => diff.status === 'pending')) return;
    foldLiveTurn();
    setLiveUser(null);
    cancelledRef.current = false;
  }, [isStreaming, liveUser, session, response, foldLiveTurn]);

  // Thread identity is the server's; the label and the live region follow.
  useEffect(() => {
    const thread = session?.thread;
    if (!thread) return;
    if (currentThread && currentThread.threadId !== thread.threadId) {
      announce('New subject');
    }
    if (!currentThread || currentThread.threadId !== thread.threadId || currentThread.title !== thread.title) {
      setCurrentThread({ threadId: thread.threadId, title: thread.title, status: 'open' });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session?.thread]);

  useEffect(() => {
    const recalled = session?.recalled;
    if (!recalled) return;
    announce(`Pulled in earlier work: ${recalled.title}`);
  }, [session?.recalled]);

  // Dropping the thread chip retracts the recall server-side too, so the
  // next turn's hint does not pull it straight back in.
  const handleRemoveContextItem = useCallback((id: string) => {
    if (id.startsWith('thread:') && currentThread) {
      api.retractRecall(currentThread.threadId, id.slice('thread:'.length)).catch((err) => {
        console.warn('retract recall failed:', err);
      });
    }
    dismissContextItem(id);
  }, [currentThread, dismissContextItem]);

  // The thread chip is a real control (spec §6): a click scrolls the
  // timeline to where that subject last happened — the page around its last
  // turn. Other chips have nowhere to go yet.
  const handleContextItemClick = useCallback((item: ContextItem) => {
    if (item.type !== 'thread') return;
    const lastTurnId = session?.recalled?.lastTurnId;
    if (lastTurnId) void loadAround(lastTurnId);
  }, [session?.recalled, loadAround]);

  // Follow the conversation — but only when it actually grew at the bottom.
  // `turns.length` changes for two other reasons, and both of them are the
  // admin deliberately reading somewhere else: "Load earlier" prepends a
  // page (useTimeline.mergeOlder), and a thread chip jump replaces the page
  // with a window around an earlier turn, which useTimeline has just
  // centred. Scrolling to the newest message on either one answers a
  // question nobody asked and undoes the navigation that was asked for.
  const tailTurnId = turns.length > 0 ? turns[turns.length - 1].turnId : null;
  useEffect(() => {
    if (anchored || !isAtBottom) return;
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [tailTurnId, anchored, isAtBottom, liveUser, response, session?.toolExecutions]);

  // Process queued messages when streaming completes
  useEffect(() => {
    if (!isStreaming && messageQueue.length > 0) {
      const nextMessage = messageQueue[0];
      setMessageQueue(prev => prev.slice(1));
      setInput(nextMessage);
      // Auto-send after a brief delay
      setTimeout(() => {
        // `/model` typed while the agent was streaming is still a command,
        // not a question. handleSend guards it; this path did not, so the
        // command reached the backend as ordinary text — harmless while a
        // session was thrown away each turn, but every turn is persisted
        // now, so it would be written into the transcript and read back in
        // the thread receipt. Guarded first: nothing else has happened yet,
        // so there is nothing to unwind.
        if (handleModelCommand(nextMessage)) return;
        const userMsg: UserMessage = {
          id: 'user-' + Date.now(),
          content: nextMessage,
          timestamp: Date.now(),
        };
        // Same as handleSend: whatever is still on screen goes into the
        // transcript before this turn takes its place.
        foldLiveTurn();
        cancelledRef.current = false;
        setLiveUser(userMsg);
        // Same as handleSend: re-pin to the bottom for the new turn.
        setIsAtBottom(true);
        sendMessage(nextMessage, undefined, picker.selection);
        setInput('');
      }, 100);
    }
  }, [isStreaming, messageQueue]);

  // Filter mentionables based on input
  const filteredMentionables = mentionables.filter(m =>
    m.mention.toLowerCase().includes(mentionFilter.toLowerCase()) ||
    m.name.toLowerCase().includes(mentionFilter.toLowerCase())
  ).slice(0, 8);

  // Image handling
  const processImageFile = (file: File): Promise<AttachedImage> => {
    return new Promise((resolve, reject) => {
      if (!file.type.startsWith('image/')) {
        reject(new Error('Not an image file'));
        return;
      }
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target?.result as string;
        resolve({
          id: `img-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
          dataUrl,
          name: file.name,
        });
      };
      reader.onerror = () => reject(new Error('Failed to read file'));
      reader.readAsDataURL(file);
    });
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(false);
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingImage(false);

    const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'));
    if (files.length === 0) return;

    try {
      const newImages = await Promise.all(files.map(processImageFile));
      setAttachedImages(prev => [...prev, ...newImages]);
    } catch (err) {
      console.error('Failed to process dropped images:', err);
    }
  };

  const handlePaste = async (e: React.ClipboardEvent) => {
    const items = Array.from(e.clipboardData.items);
    const imageItems = items.filter(item => item.type.startsWith('image/'));

    if (imageItems.length === 0) return;

    e.preventDefault();

    for (const item of imageItems) {
      const file = item.getAsFile();
      if (file) {
        try {
          const image = await processImageFile(file);
          setAttachedImages(prev => [...prev, image]);
        } catch (err) {
          console.error('Failed to process pasted image:', err);
        }
      }
    }
  };

  const removeAttachedImage = (id: string) => {
    setAttachedImages(prev => prev.filter(img => img.id !== id));
  };

  // Input handling with @mention detection
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setInput(value);

    const lastAtIndex = value.lastIndexOf('@');
    if (lastAtIndex !== -1 && lastAtIndex === value.length - 1) {
      setShowMentions(true);
      setMentionFilter('');
      setActiveMentionIndex(0);
    } else if (lastAtIndex !== -1) {
      const afterAt = value.slice(lastAtIndex + 1);
      if (!afterAt.includes(' ')) {
        setShowMentions(true);
        setMentionFilter(afterAt.toLowerCase());
        // A fresh filter is a fresh list: the highlight restarts at the
        // top rather than pointing past the end of a shrunken list.
        setActiveMentionIndex(0);
      } else {
        setShowMentions(false);
      }
    } else {
      setShowMentions(false);
    }
  };

  const insertMention = (mentionable: Mentionable) => {
    const lastAtIndex = input.lastIndexOf('@');
    const newInput = input.slice(0, lastAtIndex) + mentionable.mention + ' ';
    setInput(newInput);
    setShowMentions(false);
    inputRef.current?.focus();
  };

  // Phase 8 / T8a.3: clicking a provenance ref expands the source inline.
  // log_cursor / metric_window → evidence module; path_lines / snapshot_id →
  // config-diff module. memory_id / observation_id keep the chip popover.
  const handleProvenanceExpand = (provRef: ProvenanceRef) => {
    let expansion: Omit<ExpandedProvenanceModule, 'key'> | null = null;

    if (provRef.type === 'log_cursor' || provRef.type === 'metric_window') {
      const { source, cursor } = parseLogRef(provRef.ref);
      expansion = {
        label: provRef.label || provRef.ref,
        module: 'evidence',
        props: { source, cursor },
      };
    } else if (provRef.type === 'path_lines' || provRef.type === 'snapshot_id') {
      const { path } = parsePathRef(provRef.ref);
      expansion = {
        label: provRef.label || provRef.ref,
        module: 'config-diff',
        props: { path },
      };
    }

    if (!expansion) return;

    setExpandedProvenanceModules(prev => {
      const key = `${expansion.module}:${provRef.ref}`;
      if (prev.some(p => p.key === key)) return prev; // already expanded
      return [...prev, { key, ...expansion }];
    });
  };

  const dismissExpandedModule = (key: string) => {
    setExpandedProvenanceModules(prev => prev.filter(m => m.key !== key));
  };

  const notify = (notice: Omit<SystemNotice, 'id' | 'timestamp'>) => {
    setSystemNotices(prev => [
      ...prev,
      { ...notice, id: 'note-' + Date.now() + '-' + prev.length, timestamp: Date.now() },
    ]);
    // Through the shell's region, not a region of this note's own. A
    // `role="status"` on an element that mounts with its text already in it is
    // both an extra polite region (see lib/announce.ts) and an unreliable
    // announcement: what a screen reader watches is a region that was already
    // there changing. The status-card form has no one sentence to read out, so
    // it stays visual-only, as it was.
    if (notice.text) announce(notice.text);
  };

  /**
   * The one thing on this surface that is not a reply and still has to be
   * heard: the conversation could not be loaded. Announced on the transition
   * into failure, which is a transition on every attempt — `loadLatest`
   * clears `loadFailed` before it asks and writes it again in the catch, so
   * asking again and failing again says so again.
   */
  useEffect(() => {
    if (loadFailed) announce('Could not load the stored conversation');
  }, [loadFailed]);

  /**
   * A retry in flight, which is not the same as `loadFailed`.
   *
   * The notice below is the admin's only way back from a backend that was
   * restarting, and its button is what they have just pressed. Rendering it
   * on `loadFailed` alone unmounted the whole notice the instant the retry
   * cleared that flag — taking the focused button out from under the person
   * using it and dropping focus to the body, then putting a new one back a
   * moment later. It stays while its own attempt is running.
   */
  const [retrying, setRetrying] = useState(false);
  const retryLoad = useCallback(() => {
    setRetrying(true);
    void loadLatest()
      .then((loaded) => {
        // The other half of the sentence above. Failure announces itself on
        // the transition into `loadFailed`; success used to announce nothing
        // at all, because the only thing that changed was the page filling
        // with turns — which is not a change a screen reader reads out. The
        // admin who pressed this button heard the failure, pressed again,
        // and then heard nothing whether it had worked or not.
        if (loaded) announce('Conversation loaded');
      })
      .finally(() => setRetrying(false));
  }, [loadLatest]);

  /**
   * Handle composer input that is a `/model` command.
   *
   * Returns true when the input was consumed, so the caller must not send it.
   * A command never reaches the backend — it changes the pin for the next turn
   * and answers in the stream.
   */
  const handleModelCommand = (raw: string): boolean => {
    const command = parseModelCommand(raw);
    if (!command) return false;

    // The command still belongs to the user on a peer-governed variant, so
    // it is consumed with an answer rather than swallowed — but it has no
    // pin to move: the workstation's own model configuration governs.
    if (peerGovernedVariant) {
      notify({
        tone: 'info',
        text: 'Model choice is governed by the paired workstation. Link or change the peer in Settings, under Models & Providers.',
      });
      return true;
    }

    const candidates = picker.modelsForRole(CHAT_ROLE_ID);

    const pinMatching = (query: string, tier?: 'guide' | 'specialist' | 'vision') => {
      const matches = matchModels(candidates, query);
      if (matches.length === 0) {
        notify({ tone: 'warning', text: `No configured model matches "${query}".` });
        return;
      }
      // More than one match is a question, not a guess: open the popover with
      // the query already typed rather than silently picking the top hit.
      if (matches.length > 1) {
        setPickerQuery(query);
        setPickerOpen(true);
        return;
      }
      const chosen = matches[0];
      picker.pinModel(chosen.id, chosen.endpointId);
      if (tier) picker.pinTier(tier);
      notify({
        tone: 'info',
        text: `Pinned to ${chosen.name} (${providerDescriptor(chosen.provider).label}).`,
      });
    };

    switch (command.kind) {
      case 'open':
        setPickerQuery(undefined);
        setPickerOpen(true);
        break;
      case 'search':
        pinMatching(command.query);
        break;
      case 'pin':
        pinMatching(command.query);
        break;
      case 'tier':
        if (command.query) {
          pinMatching(command.query, command.tier);
        } else {
          picker.pinTier(command.tier);
          notify({ tone: 'info', text: `Pinned to the ${command.tier} tier.` });
        }
        break;
      case 'auto':
        picker.clearPin();
        notify({ tone: 'info', text: 'Back to automatic routing.' });
        break;
      case 'status': {
        const assignment = picker.assignmentFor(CHAT_ROLE_ID);
        const endpoint = assignment ? picker.endpointFor(assignment.endpointId) : undefined;
        const active = picker.selection.model
          || turnModel?.model
          || assignment?.model
          || '';
        const model = candidates.find(m => m.id === active);
        notify({
          tone: 'info',
          status: formatModelStatus({
            activeModel: active,
            providerLabel: endpoint ? providerDescriptor(endpoint.provider).label : '',
            isLocal: model ? model.isLocal : Boolean(endpoint && providerDescriptor(endpoint.provider).isLocal),
            pinned: picker.isPinned,
            tier: picker.selection.tier && picker.selection.tier !== 'auto'
              ? picker.selection.tier
              : (turnModel?.tier || 'auto'),
            contextWindow: model?.capabilities.contextWindow,
            endpointUrl: endpoint?.url,
          }),
        });
        break;
      }
      case 'error':
        notify({ tone: 'warning', text: command.message });
        break;
    }
    setInput('');
    return true;
  };

  const handleSend = async () => {
    if (!isStreaming && handleModelCommand(input)) return;

    // Queue messages if streaming
    if (isStreaming && input.trim()) {
      setMessageQueue(prev => [...prev, input.trim()]);
      setInput('');
      // The composer swallowed the sentence; the queue chip is the only
      // other trace of it, and a feed is not a live region. Without this,
      // Enter while the agent is busy appears to do nothing at all.
      announce('Message queued');
      return;
    }

    if ((!input.trim() && attachedImages.length === 0)) return;

    // Extract base64 data from attached images
    const imageData = attachedImages.map(img => {
      const base64Match = img.dataUrl.match(/^data:image\/\w+;base64,(.+)$/);
      return base64Match ? base64Match[1] : img.dataUrl;
    });

    const userMsg: UserMessage = {
      id: 'user-' + Date.now(),
      content: input.trim() || (imageData.length > 0 ? '[Image]' : ''),
      timestamp: Date.now(),
      images: imageData.length > 0 ? imageData : undefined,
    };

    // A turn parked on an undecided proposal (or a confirmation) is still
    // liveUser and is about to lose both its slot and its session. Record
    // it first — folding reads cancelledRef, so it happens before the reset
    // below, which exists because a parked turn never reached the effect
    // that normally clears it: a Stop pressed two turns ago must not follow
    // this one into the transcript as "cancelled".
    foldLiveTurn();
    cancelledRef.current = false;
    stoppedRef.current = false;
    setLiveUser(userMsg);
    setAgentError(null);
    setAttachedImages([]);
    setExpandedProvenanceModules([]);
    // Re-pin to the bottom: sending a message means the user wants to see
    // it and the response, even if they had scrolled up to read something.
    setIsAtBottom(true);

    // No conversation id: the server resolves the subject. A session id
    // names one turn, so the hook mints a fresh one per send.
    sendMessage(
      input.trim() || (imageData.length > 0 ? '[Image]' : ''),
      undefined,
      picker.selection,
      imageData.length > 0 ? imageData : undefined,
    );
    setInput('');
    // The sentence vanishing from the composer is the only visual trace of
    // the send until the agent starts working, which can take seconds. A
    // screen reader hears nothing at all in that window without this.
    announce('Message sent');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    // The mention popup is a listbox this composer owns (see the markup at
    // MENTION_LISTBOX_ID): the arrow keys walk it, Enter takes the active
    // option. Before this, Enter with the popup open did nothing at all —
    // the options were decoration a keyboard could see and not reach.
    if (showMentions && filteredMentionables.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveMentionIndex(i => Math.min(i + 1, filteredMentionables.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveMentionIndex(i => Math.max(i - 1, 0));
        return;
      }
      if (e.key === 'Enter') {
        e.preventDefault();
        insertMention(filteredMentionables[activeMentionIndex]);
        return;
      }
    }
    if (e.key === 'Enter' && !e.shiftKey && !showMentions) {
      e.preventDefault();
      handleSend();
    } else if (e.key === 'Escape') {
      setShowMentions(false);
    }
  };

  // Auto-resize textarea
  const autoResizeTextarea = () => {
    const textarea = inputRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 150) + 'px';
    }
  };

  useEffect(() => {
    if (!input && inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
  }, [input]);

  // Retry after an error clears the live state only; stored turns stay.
  const handleReset = () => {
    reset();
    setAgentError(null);
    setExpandedProvenanceModules([]);
    setLiveUser(null);
  };

  return (
    <div className={cn('flex flex-col h-full bg-background', className)}>
      <CurrentTopicLabel thread={currentThread} />

      {session?.contextItems && session.contextItems.length > 0 && (
        <ContextBar
          items={session.contextItems.map(ci => ({
            id: ci.id,
            type: contextTypeFor(ci.source),
            label: ci.label,
            tokens: ci.tokens,
            // The thread chip's "why now": the terms that matched (spec §6).
            hint:
              ci.source === 'thread' && session.recalled && session.recalled.matchTerms.length > 0
                ? `matched: ${session.recalled.matchTerms.join(', ')}`
                : undefined,
          }))}
          onRemoveItem={handleRemoveContextItem}
          onItemClick={handleContextItemClick}
        />
      )}

      <div
        ref={scrollContainerRef}
        onScroll={handleScroll}
        // aria-busy, not a live region: it tells assistive tech the content
        // is still filling in (the feed inside carries its own feed
        // semantics), without making every streamed token a spoken event.
        aria-busy={isStreaming}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4 relative"
      >
        {/* Empty state: the host introduces itself — only when there is
            nothing stored and nothing in flight. `loadFailed` is the rest of
            that condition: an empty timeline because the request could not
            reach a restarting backend is not an empty timeline because this
            is the first time we have spoken, and greeting over someone's
            real conversation is the worse of the two mistakes. */}
        {turns.length === 0 && !liveUser && !timelineLoading && !loadFailed && (
          <HostGreeting onPrompt={setInput} />
        )}

        {/* The other half of that condition, said out loud. useTimeline
            only warns to the console, and an empty page renders nothing, so
            an admin whose backend was mid-restart was shown a blank
            conversation with no explanation and no way back short of
            restarting the app — so the way back has to be offered here, and
            has to survive being used (see `retrying`). */}
        {(loadFailed || retrying) && (
          <div className="flex justify-center">
            <div className="flex items-center gap-2 rounded-lg border border-hairline bg-canvas-subtle px-3 py-1.5 text-[11px] font-mono text-ink-secondary">
              <span>Could not load the stored conversation</span>
              <button
                type="button"
                onClick={retryLoad}
                disabled={timelineLoading}
                className="rounded border border-hairline px-1.5 py-0.5 text-ink-secondary hover:text-ink disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
              >
                {timelineLoading ? 'Trying…' : 'Try again'}
              </button>
            </div>
          </div>
        )}

        {/* Every turn that has finished, oldest first, grouped by day. */}
        <Timeline
          byDay={byDay}
          hasMore={hasMore}
          loading={timelineLoading}
          anchored={anchored}
          onLoadOlder={loadOlder}
          onLoadLatest={loadLatest}
          onRunCommand={onRunCommand}
          displayName={identity?.display_name}
        />

        {/* The turn in flight: the live assistant block, exactly as before. */}
        {liveUser && (
          <div className="space-y-3" data-live-turn={session?.turnId ?? liveUser.id}>
            <div className="flex justify-end">
              <div className="max-w-[80%] bg-primary text-primary-foreground px-4 py-2 rounded-lg">
                <p className="text-sm whitespace-pre-wrap break-words">{liveUser.content}</p>
              </div>
            </div>

            {session && (
              <div className="flex justify-start">
                <div className="max-w-[85%] bg-muted/50 border border-border/50 rounded-lg p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <StateBadge state={session.state} showPulse={isStreaming} />
                    {session.loopCount > 0 && (
                      <span className="text-xs text-muted-foreground">Loop {session.loopCount}</span>
                    )}
                  </div>

                  {session.plan.length > 0 && (
                    <PlanChecklist plan={session.plan} currentStep={session.currentStep} />
                  )}

                  {/* Active Scan Visualization */}
                  {session.activeScan && (
                    <ScanBlock
                      source={session.activeScan.source}
                      query={session.activeScan.query}
                      fileCount={session.activeScan.fileCount}
                      isComplete={session.activeScan.isComplete}
                      resultsCount={session.activeScan.results}
                    />
                  )}

                  {session.toolExecutions.map((exec) => (
                    <ToolExecutionCard key={exec.executionId} execution={exec} />
                  ))}

                  {/* Terminals Halbert opened for this turn, flowing in the
                      conversation; they dock to the right column on scroll. */}
                  <InlineTerminals sessionIds={session.terminalSessions ?? []} />

                  {/* Diff Proposals */}
                  {session.diffProposals.map((diff) => (
                    <DiffBlock
                      key={diff.id}
                      filePath={diff.filePath}
                      oldContent={diff.oldContent}
                      newContent={diff.newContent}
                      additions={diff.additions}
                      deletions={diff.deletions}
                      status={diff.status}
                      onApply={() => applyDiff(diff.id)}
                      onReject={() => rejectDiff(diff.id)}
                    />
                  ))}

                  {/* What answered, when that is not what was asked for — an
                      escalation or a fallback. Rendered here while the turn
                      is live, and again below once it is not: this block
                      unmounts the moment `liveUser` goes null and Timeline
                      stores no model, so a paid-for escalation would
                      otherwise flash for a few milliseconds and be gone.
                      `liveUser` gates the two slots apart, so it is never on
                      screen twice. (The durable fix is to persist the
                      answering model on the turn row and let Timeline render
                      it — a spec change, not a merge decision.) */}
                  {turnModel && <TurnModelNotice turn={turnModel} />}

                  {session?.modality && <ModalityHandoffBadge modality={session.modality} />}

                  {session?.speechSegments && session.speechSegments.length > 0 && (
                    <VoiceCompanionPill
                      segments={session.speechSegments}
                      isActive={isStreaming}
                    />
                  )}

                  {thinking && <ThinkingPanel thinking={thinking} isStreaming={isStreaming} />}

                  {session.confidence > 0 && (
                    <ConfidenceIndicator
                      confidence={session.confidence}
                      cragAction={session.cragAction}
                      size="sm"
                    />
                  )}

                  {response && (
                    <div className="text-sm text-foreground">
                      <MessageContent content={response} onRunCommand={onRunCommand} />
                      {isStreaming && <span className="inline-block w-2 h-4 bg-muted animate-pulse motion-reduce:animate-none ml-0.5" />}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Phase 8 extras for the turn that just finished: what answered,
            provenance chips, module invocations, and sources expanded from a
            chip. They belong to the last reply and clear on the next send. */}
        {!liveUser && !isStreaming && (turnModel || provenance.length > 0 || moduleInvocations.length > 0 || expandedProvenanceModules.length > 0) && (
          <div className="flex justify-start">
            <div className="max-w-[85%] space-y-3">
              {turnModel && <TurnModelNotice turn={turnModel} />}
              {session?.modality && <ModalityHandoffBadge modality={session.modality} />}
              {provenance.length > 0 && (
                <WhyChip provenance={provenance} onExpand={handleProvenanceExpand} />
              )}
              {moduleInvocations.length > 0 && (
                <div className="space-y-3">
                  {moduleInvocations.map((inv, i) => (
                    <ModuleRenderer key={i} module={inv.module} props={inv.props} />
                  ))}
                </div>
              )}
              {expandedProvenanceModules.length > 0 && (
                <div className="space-y-3">
                  {expandedProvenanceModules.map((m) => (
                    <div key={m.key} className="relative">
                      <button
                        type="button"
                        aria-label="Close expanded source"
                        onClick={() => dismissExpandedModule(m.key)}
                        className="absolute right-2 top-2 z-10 p-1 rounded bg-muted/80 hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
                      >
                        <XIcon className="h-3 w-3" aria-hidden="true" />
                      </button>
                      <ModuleRenderer module={m.module} props={m.props} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {agentError && !isStreaming && (
          <div className="flex justify-center">
            <div className="bg-error/10 border border-error/30 rounded-lg px-4 py-2 flex items-center gap-2">
              <span className="text-sm text-error">{agentError}</span>
              <button type="button" aria-label="Retry" onClick={handleReset} className="p-1 hover:bg-error/20 rounded">
                <RotateCcw className="h-4 w-4 text-error" aria-hidden="true" />
              </button>
            </div>
          </div>
        )}

        {systemNotices.map(notice => (
          <div key={notice.id} className="text-xs">
            {notice.status ? (
              <ModelStatusCard rows={notice.status} />
            ) : (
              <div
                className={cn(
                  'rounded-lg border px-3 py-2',
                  notice.tone === 'warning'
                    ? 'border-warning/40 bg-warning/10 text-foreground'
                    : 'border-border bg-muted/40 text-muted-foreground',
                )}
              >
                {notice.text}
              </div>
            )}
          </div>
        ))}

        <div ref={messagesEndRef} />
      </div>

      {/* Floating "Jump to latest" — shown when the user has scrolled up
          during streaming and is not in an anchored (thread-chip) view.
          Clicking re-pins to the bottom and re-enables auto-scroll. */}
      {!isAtBottom && !anchored && (
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
              setIsAtBottom(true);
            }}
            aria-label="Jump to latest"
            className="absolute bottom-2 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 rounded-full border border-border bg-background px-3 py-1.5 text-xs text-foreground shadow-lg hover:bg-muted transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus"
          >
            <ArrowDown className="h-3.5 w-3.5" aria-hidden="true" />
            Jump to latest
          </button>
        </div>
      )}

      {/* Mention Autocomplete — a real listbox (see handleKeyDown): the
          composer points at it with aria-controls and names the active
          option with aria-activedescendant, so the arrow keys are the
          standard combobox interaction, not a mouse-only popup. */}
      {showMentions && filteredMentionables.length > 0 && (
        <div
          id={MENTION_LISTBOX_ID}
          role="listbox"
          aria-label="Mentions"
          className="mx-4 mb-1 bg-muted border border-border rounded-md shadow-lg max-h-48 overflow-y-auto"
        >
          {filteredMentionables.map((m, idx) => (
            <button
              key={m.id}
              id={`mention-option-${m.id}`}
              type="button"
              role="option"
              aria-selected={idx === activeMentionIndex}
              className={cn(
                "w-full px-3 py-1.5 text-left hover:bg-muted flex items-center gap-2 text-xs",
                idx === activeMentionIndex && "bg-muted",
              )}
              onClick={() => insertMention(m)}
            >
              {m.type === 'terminal' ? (
                <Terminal className="h-3 w-3 text-success" />
              ) : (
                <AtSign className="h-3 w-3 text-muted-foreground" />
              )}
              <span className="font-medium text-foreground">{m.mention}</span>
              <span className="text-muted-foreground ml-auto">{m.type}</span>
            </button>
          ))}
        </div>
      )}

      <div
        className={cn(
          "border-t border-border p-4 transition-colors",
          isDraggingImage && "bg-info/10 border-info"
        )}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {/* Attached Images Preview */}
        {attachedImages.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {attachedImages.map(img => (
              <div key={img.id} className="relative group">
                <img
                  src={img.dataUrl}
                  alt={img.name}
                  className="h-12 w-12 object-cover rounded border border-border"
                />
                <button
                  type="button"
                  aria-label={`Remove image ${img.name}`}
                  onClick={() => removeAttachedImage(img.id)}
                  className="absolute -top-1 -right-1 h-4 w-4 bg-error text-white rounded-full flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <XIcon className="h-2.5 w-2.5" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Drop indicator */}
        {isDraggingImage && (
          <div className="mb-2 p-2 border-2 border-dashed border-info rounded text-center text-xs text-info">
            <ImageIcon className="h-4 w-4 mx-auto mb-1" />
            Drop image here
          </div>
        )}

        {/* Message Queue */}
        {messageQueue.length > 0 && (
          <div className="mb-2 space-y-1">
            {messageQueue.map((msg, idx) => (
              <div key={idx} className="flex items-center justify-between gap-2 px-2 py-1 bg-warning/10 border border-warning/20 rounded text-xs">
                <span className="text-muted-foreground truncate">Queued: {msg}</span>
                <button
                  type="button"
                  aria-label={`Remove queued message: ${msg}`}
                  onClick={() => setMessageQueue(prev => prev.filter((_, i) => i !== idx))}
                  className="text-muted-foreground hover:text-foreground shrink-0"
                >
                  <XIcon className="h-3 w-3" aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-end gap-2">
          <div className="flex-1 relative">
            <textarea
              ref={inputRef}
              value={input}
              aria-label="Message Halbert"
              // Combobox semantics for the mention listbox (see the popup
              // markup and handleKeyDown): expanded/pointing/active, so the
              // screen reader follows the arrows instead of guessing.
              aria-expanded={showMentions}
              aria-controls={showMentions ? MENTION_LISTBOX_ID : undefined}
              aria-activedescendant={
                showMentions && filteredMentionables.length > 0
                  ? `mention-option-${filteredMentionables[Math.min(activeMentionIndex, filteredMentionables.length - 1)].id}`
                  : undefined
              }
              onChange={(e) => {
                handleInputChange(e);
                autoResizeTextarea();
              }}
              onKeyDown={handleKeyDown}
              onPaste={handlePaste}
              placeholder={isStreaming ? "Type to queue next message..." : "Ask Halbert... (@ to mention, paste/drop images)"}
              className="w-full bg-muted border border-border rounded-lg px-4 py-2 pr-10 text-sm text-foreground placeholder-zinc-500 focus:outline-none focus:border-info resize-none overflow-hidden min-h-[40px]"
              rows={1}
              style={{ maxHeight: '150px' }}
            />
            <button
              type="button"
              onClick={() => window.dispatchEvent(new CustomEvent('halbert:capture-screenshot'))}
              className="absolute right-2 bottom-2 text-muted-foreground hover:text-foreground transition-colors"
              title="Screenshot"
            >
              <Camera className="h-4 w-4" />
            </button>
          </div>

          {isStreaming ? (
            <button
              type="button"
              aria-label="Stop"
              onClick={() => {
                cancelledRef.current = true;
                // Said here rather than in the stream-end effect, which
                // would have to guess why streaming stopped; the hand on
                // the button is the only place that knows.
                stoppedRef.current = true;
                cancel();
                announce('Stopped');
              }}
              className="p-2 bg-error hover:bg-error rounded-lg transition-colors flex-shrink-0"
            >
              <StopCircle className="h-5 w-5 text-white" aria-hidden="true" />
            </button>
          ) : (
            <button
              type="button"
              aria-label="Send"
              onClick={handleSend}
              disabled={!input.trim() && attachedImages.length === 0}
              className="p-2 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors flex-shrink-0"
            >
              <Send className="h-5 w-5 text-white" aria-hidden="true" />
            </button>
          )}
        </div>

        {/* The pill sits where the session id used to: the composer footer is
            the only place left that belongs to the next turn rather than to
            the transcript. Its popover therefore has to open upward.
            On a home variant there is no pill to sit here at all
            — see peerGovernedVariant above. */}
        <div className="mt-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>{isStreaming ? 'Agent working... type to queue' : 'Press Enter to send'}</span>
          {peerGovernedVariant ? null : (
            <ChatModelPill
              picker={picker}
              open={pickerOpen}
              onOpenChange={(next) => {
                setPickerOpen(next);
                if (!next) setPickerQuery(undefined);
              }}
              initialQuery={pickerQuery}
              onOpenSettings={onOpenModelSettings}
            />
          )}
        </div>
      </div>

      {session?.pendingConfirmation && (
        <ConfirmationDialog
          confirmation={session.pendingConfirmation}
          onConfirm={() => confirmAction(session.pendingConfirmation!.actionId, true)}
          onReject={() => confirmAction(session.pendingConfirmation!.actionId, false)}
        />
      )}
    </div>
  );
}

export default AgentChat;
