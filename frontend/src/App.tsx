import { useState, useEffect, useCallback } from 'react'
import {
  chatWithLLM,
  fetchMappings,
  createMapping,
  updateMapping,
  removeMapping,
  fetchRegexPatterns,
  createRegexPattern,
  updateRegexPattern,
  removeRegexPattern,
  getGlobalScanner,
  setGlobalScanner,
  type Mapping,
  type RegexPattern,
} from './api'
import Sidebar from './Sidebar'
import Chat from './Chat'

export interface SecurityBlock {
  scanner: string
  reason: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  safe_prompt?: string
  llm_response_raw?: unknown
  timestamp: number
  block?: SecurityBlock
}

function generateId() {
  return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)
}

function generateSessionId() {
  return 'sess_' + (crypto.randomUUID?.() ?? Math.random().toString(36).slice(2, 14))
}

function parseBlockError(msg: string): SecurityBlock | undefined {
  const match = msg.match(/Security Policy Violation \[([^\]]+)\]:\s*(.+)/)
  if (!match) return
  return { scanner: match[1], reason: match[2].replace(/^Security Policy Violation:\s*|^Policy Violation:\s*/i, '') }
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(generateSessionId)

  const [mappings, setMappings] = useState<Mapping[]>([])
  const [newLabel, setNewLabel] = useState('')
  const [mappingsError, setMappingsError] = useState<string | null>(null)
  const [regexPatterns, setRegexPatterns] = useState<RegexPattern[]>([])
  const [activeScanners, setActiveScanners] = useState<string[]>(['spacy'])

  const loadMappings = useCallback(async () => {
    setMappingsError(null)
    try {
      const { data } = await fetchMappings()
      setMappings(data)
    } catch (e) {
      setMappingsError((e as Error).message)
    }
  }, [])

  const loadRegexPatterns = useCallback(async () => {
    try {
      const { data } = await fetchRegexPatterns()
      setRegexPatterns(data)
    } catch (e) {
      console.error('Failed to load regex patterns:', e)
    }
  }, [])

  useEffect(() => {
    loadMappings()
    loadRegexPatterns()
    getGlobalScanner().then(({ data }) => setActiveScanners(data.active_scanners)).catch(() => {})
  }, [loadMappings, loadRegexPatterns])

  const handleScannerChange = async (scanner: string) => {
    const next = activeScanners.includes(scanner)
      ? activeScanners.filter((s) => s !== scanner)
      : [...activeScanners, scanner]
    if (next.length === 0) return
    try {
      await setGlobalScanner(next)
      setActiveScanners(next)
    } catch (e) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleSend = async (text: string) => {
    const userMsg: Message = {
      id: generateId(),
      role: 'user',
      content: text,
      timestamp: Date.now(),
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const { data } = await chatWithLLM(text, sessionId)

      const assistantMsg: Message = {
        id: generateId(),
        role: 'assistant',
        content: data.final_response,
        safe_prompt: data.safe_prompt,
        llm_response_raw: data.llm_response_raw,
        timestamp: Date.now(),
      }

      if (data.session_id && data.session_id !== sessionId) {
        console.debug('Session ID updated by server:', data.session_id)
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (e: unknown) {
      const raw = (e as Error).message
      const block = parseBlockError(raw)
      const errMsg: Message = {
        id: generateId(),
        role: 'assistant',
        content: block ? '' : 'Error: ' + raw,
        timestamp: Date.now(),
        block,
      }
      setMessages((prev) => [...prev, errMsg])
    }
    setLoading(false)
  }

  const handleClear = () => {
    setMessages([])
  }

  const handleAddMapping = async () => {
    if (!newLabel.trim()) return
    try {
      await createMapping(newLabel.trim())
      setNewLabel('')
      await loadMappings()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleToggleMapping = async (m: Mapping) => {
    try {
      await updateMapping(m.id, { is_active: !m.is_active })
      await loadMappings()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleDeleteMapping = async (id: number) => {
    try {
      await removeMapping(id)
      await loadMappings()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleAddRegexPattern = async (
    name: string,
    pattern: string,
    entity_type: string,
    score: number,
  ) => {
    try {
      await createRegexPattern(name, pattern, entity_type, score)
      await loadRegexPatterns()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleToggleRegexPattern = async (p: RegexPattern) => {
    try {
      await updateRegexPattern(p.id, { is_active: !p.is_active })
      await loadRegexPatterns()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleUpdateRegexPattern = async (
    id: number,
    data: { pattern?: string; score?: number },
  ) => {
    try {
      await updateRegexPattern(id, data)
      await loadRegexPatterns()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  const handleDeleteRegexPattern = async (id: number) => {
    try {
      await removeRegexPattern(id)
      await loadRegexPatterns()
    } catch (e: unknown) {
      alert('Error: ' + (e as Error).message)
    }
  }

  return (
    <div className="app">
      <Sidebar
        open={sidebarOpen}
        onToggle={() => setSidebarOpen((v) => !v)}
        mappings={mappings}
        newLabel={newLabel}
        onNewLabelChange={setNewLabel}
        onAddMapping={handleAddMapping}
        onToggleMapping={handleToggleMapping}
        onDeleteMapping={handleDeleteMapping}
        error={mappingsError}
        activeScanners={activeScanners}
        onScannerChange={handleScannerChange}
        regexPatterns={regexPatterns}
        onAddRegexPattern={handleAddRegexPattern}
        onToggleRegexPattern={handleToggleRegexPattern}
        onUpdateRegexPattern={handleUpdateRegexPattern}
        onDeleteRegexPattern={handleDeleteRegexPattern}
      />
      <button
        className="sidebar-toggle-btn"
        style={{ left: sidebarOpen ? '280px' : '0' }}
        onClick={() => setSidebarOpen((v) => !v)}
      >
        {sidebarOpen ? '◀' : '☰'}
      </button>
      <Chat
        messages={messages}
        onSend={handleSend}
        onClear={handleClear}
        loading={loading}
        sessionId={sessionId}
      />
    </div>
  )
}
