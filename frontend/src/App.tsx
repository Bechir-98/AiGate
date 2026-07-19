import { useState, useEffect, useCallback } from 'react'
import {
  chatWithLLM,
  fetchMappings,
  createMapping,
  updateMapping,
  removeMapping,
  getGlobalScanner,
  setGlobalScanner,
  type Mapping,
} from './api'
import Sidebar from './Sidebar'
import Chat from './Chat'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  safe_prompt?: string
  llm_response_raw?: unknown
  timestamp: number
}

function generateId() {
  return crypto.randomUUID?.() ?? Math.random().toString(36).slice(2)
}

function generateSessionId() {
  return 'sess_' + (crypto.randomUUID?.() ?? Math.random().toString(36).slice(2, 14))
}

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [sessionId] = useState(generateSessionId)

  const [mappings, setMappings] = useState<Mapping[]>([])
  const [newLabel, setNewLabel] = useState('')
  const [mappingsError, setMappingsError] = useState<string | null>(null)
  const [activeScanner, setActiveScanner] = useState('spacy')

  const loadMappings = useCallback(async () => {
    setMappingsError(null)
    try {
      const { data } = await fetchMappings()
      setMappings(data)
    } catch (e) {
      setMappingsError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    loadMappings()
    getGlobalScanner().then(({ data }) => setActiveScanner(data.active_scanner)).catch(() => {})
  }, [loadMappings])

  const handleScannerChange = async (scanner: string) => {
    try {
      await setGlobalScanner(scanner)
      setActiveScanner(scanner)
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
      setMessages((prev) => [...prev, assistantMsg])
    } catch (e: unknown) {
      const errMsg: Message = {
        id: generateId(),
        role: 'assistant',
        content: 'Error: ' + (e as Error).message,
        timestamp: Date.now(),
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
        activeScanner={activeScanner}
        onScannerChange={handleScannerChange}
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
