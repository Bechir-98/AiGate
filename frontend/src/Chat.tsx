import { useState, useRef, useEffect, useCallback } from 'react'
import type { Message } from './App'
import './Chat.css'

interface ChatProps {
  messages: Message[]
  onSend: (text: string) => void
  onClear: () => void
  loading: boolean
  sessionId: string
}

const TABS = ['Final', 'Anonymized', 'Raw LLM'] as const

function formatTime(ts: number) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Chat({ messages, onSend, onClear, loading, sessionId }: ChatProps) {
  const [input, setInput] = useState('')
  const [activeTab, setActiveTab] = useState<Record<string, number>>({})
  const listRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(() => {
    const text = input.trim()
    if (!text || loading) return
    onSend(text)
    setInput('')
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
  }, [input, loading, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
  }

  const getTabContent = (msg: Message, tabIndex: number): string => {
    switch (tabIndex) {
      case 0:
        return msg.content
      case 1:
        return msg.safe_prompt ?? ''
      case 2: {
        const raw = msg.llm_response_raw
        if (raw == null) return ''
        return typeof raw === 'string' ? raw : JSON.stringify(raw, null, 2)
      }
      default:
        return ''
    }
  }

  const showTabs = (msg: Message): boolean => {
    return msg.role === 'assistant' && !!msg.safe_prompt && !!msg.llm_response_raw
  }

  return (
    <div className="chat">
      <div className="chat-header">
        <div className="chat-header-left">
          <h1>Gateway Chat</h1>
          <span className="chat-session">{sessionId.slice(0, 22)}</span>
        </div>
        {messages.length > 0 && (
          <button className="chat-clear" onClick={onClear}>
            Clear
          </button>
        )}
      </div>

      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <div className="chat-empty">
            <div className="chat-empty-icon">◇</div>
            <p>Send a message to test the anonymization pipeline.</p>
            <p className="chat-empty-hint">
              Prompts are sanitized, sent to the LLM, then restored — all transparently.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`msg ${msg.role}`}>
            <div className="msg-bubble">
              <div className="msg-label">{msg.role === 'user' ? 'You' : 'Assistant'}</div>

              {msg.role === 'user' ? (
                <div className="msg-content">{msg.content}</div>
              ) : (
                <>
                  {showTabs(msg) && (
                    <div className="msg-tabs">
                      {TABS.map((label, i) => (
                        <button
                          key={label}
                          className={`msg-tab ${(activeTab[msg.id] ?? 0) === i ? 'active' : ''}`}
                          onClick={() =>
                            setActiveTab((prev) => ({ ...prev, [msg.id]: i }))
                          }
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                  {showTabs(msg) && (activeTab[msg.id] ?? 0) !== 0 ? (
                    <div className="msg-tab-content">
                      {getTabContent(msg, activeTab[msg.id] ?? 0)}
                    </div>
                  ) : (
                    <div className="msg-content">
                      {getTabContent(msg, activeTab[msg.id] ?? 0)}
                    </div>
                  )}
                </>
              )}

              <div className="msg-timestamp">{formatTime(msg.timestamp)}</div>
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg assistant">
            <div className="msg-bubble">
              <div className="msg-label">Assistant</div>
              <div className="typing">
                <div className="typing-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="chat-input-area">
        <div className="chat-input-row">
          <textarea
            ref={inputRef}
            className="chat-input"
            placeholder="Type a message..."
            value={input}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            rows={1}
          />
          <button
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!input.trim() || loading}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  )
}
