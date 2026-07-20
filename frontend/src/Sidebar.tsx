import { useState } from 'react'
import { type Mapping, type RegexPattern } from './api'
import './Sidebar.css'

const SCANNERS = [
  { id: 'spacy', label: 'SpaCy' },
  { id: 'gliner1', label: 'GLiNER v1' },
  { id: 'gliner2', label: 'GLiNER v2' },
  { id: 'prompt_guard', label: 'Prompt Guard' },
  { id: 'toxicity', label: 'Toxicity' },
  { id: 'custom_regex', label: 'Custom Regex' },
] as const

interface SidebarProps {
  open: boolean
  onToggle: () => void
  mappings: Mapping[]
  newLabel: string
  onNewLabelChange: (val: string) => void
  onAddMapping: () => void
  onToggleMapping: (m: Mapping) => void
  onDeleteMapping: (id: number) => void
  error: string | null
  activeScanners: string[]
  onScannerChange: (scanner: string) => void
  regexPatterns: RegexPattern[]
  onAddRegexPattern: (name: string, pattern: string, entity_type: string, score: number) => void
  onToggleRegexPattern: (p: RegexPattern) => void
  onUpdateRegexPattern: (id: number, data: { pattern?: string; score?: number }) => void
  onDeleteRegexPattern: (id: number) => void
}

interface RegexFormState {
  name: string
  pattern: string
  entity_type: string
  score: string
}

const emptyRegexForm: RegexFormState = { name: '', pattern: '', entity_type: '', score: '0.85' }

function RegexForm({ onSubmit }: { onSubmit: (vals: RegexFormState) => void }) {
  const [form, setForm] = useState<RegexFormState>(emptyRegexForm)

  const handleSubmit = () => {
    if (!form.name.trim() || !form.pattern.trim() || !form.entity_type.trim()) return
    onSubmit(form)
    setForm(emptyRegexForm)
  }

  const set = (key: keyof RegexFormState) => (
    e: React.ChangeEvent<HTMLInputElement>,
  ) => setForm((prev) => ({ ...prev, [key]: e.target.value }))

  return (
    <div className="regex-add-form">
      <input placeholder="Name (e.g. employee_id)" value={form.name} onChange={set('name')} />
      <input placeholder="Pattern (e.g. E-\\d{6})" value={form.pattern} onChange={set('pattern')} />
      <input placeholder="Entity type (e.g. EMPLOYEE_ID)" value={form.entity_type} onChange={set('entity_type')} />
      <div className="regex-add-row">
        <input
          type="number"
          step="0.05"
          min="0"
          max="1"
          placeholder="Score"
          value={form.score}
          onChange={set('score')}
        />
        <button
          onClick={handleSubmit}
          disabled={!form.name.trim() || !form.pattern.trim() || !form.entity_type.trim()}
        >
          Add
        </button>
      </div>
    </div>
  )
}

function RegexPatternItem({
  pattern,
  onToggle,
  onUpdate,
  onDelete,
}: {
  pattern: RegexPattern
  onToggle: () => void
  onUpdate: (data: { pattern?: string; score?: number }) => void
  onDelete: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [editPattern, setEditPattern] = useState(pattern.pattern)
  const [editScore, setEditScore] = useState(String(pattern.score))

  const handleSave = () => {
    const updates: { pattern?: string; score?: number } = {}
    if (editPattern !== pattern.pattern) updates.pattern = editPattern
    const parsedScore = parseFloat(editScore)
    if (!isNaN(parsedScore) && parsedScore !== pattern.score) updates.score = parsedScore
    if (Object.keys(updates).length > 0) onUpdate(updates)
    setEditing(false)
  }

  return (
    <div className="regex-item">
      <div className="regex-item-top">
        <button
          className={`entity-check ${pattern.is_active ? 'on' : ''}`}
          onClick={onToggle}
        >
          {pattern.is_active ? '✓' : ''}
        </button>
        <div className="regex-labels">
          <span className="regex-name">{pattern.name}</span>
          <span className="regex-entity">{pattern.entity_type}</span>
        </div>
        <button className="entity-del" onClick={onDelete}>✕</button>
      </div>
      {editing ? (
        <div className="regex-edit-form">
          <input
            value={editPattern}
            onChange={(e) => setEditPattern(e.target.value)}
            placeholder="Pattern"
          />
          <div className="regex-edit-row">
            <input
              type="number"
              step="0.05"
              min="0"
              max="1"
              value={editScore}
              onChange={(e) => setEditScore(e.target.value)}
            />
            <button onClick={handleSave}>Save</button>
            <button className="regex-cancel-btn" onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div className="regex-detail" onClick={() => setEditing(true)}>
          <code className="regex-pattern">{pattern.pattern}</code>
          <span className="regex-score">{pattern.score.toFixed(2)}</span>
        </div>
      )}
    </div>
  )
}

export default function Sidebar({
  open,
  mappings,
  newLabel,
  onNewLabelChange,
  onAddMapping,
  onToggleMapping,
  onDeleteMapping,
  error,
  activeScanners,
  onScannerChange,
  regexPatterns,
  onAddRegexPattern,
  onToggleRegexPattern,
  onUpdateRegexPattern,
  onDeleteRegexPattern,
}: SidebarProps) {
  return (
    <div className={`sidebar ${open ? 'open' : 'closed'}`}>
      <div className="sidebar-inner">
        <div className="sidebar-header">
          <h2>Configuration</h2>
        </div>
        <div className="sidebar-body">
          <div className="sidebar-section">
            <div className="sidebar-section-title">Detection Engine</div>
            <div className="scanner-group">
              {SCANNERS.map((s) => (
                <button
                  key={s.id}
                  className={`scanner-btn ${activeScanners.includes(s.id) ? 'active' : ''}`}
                  onClick={() => onScannerChange(s.id)}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-title">GLiNER → Presidio</div>
            {error && <div className="sidebar-error">{error}</div>}
            {mappings.length === 0 ? (
              <div className="entity-empty">No mappings yet</div>
            ) : (
              <div className="entity-list">
                {mappings.map((m) => (
                  <div key={m.id} className="entity-item">
                    <button
                      className={`entity-check ${m.is_active ? 'on' : ''}`}
                      onClick={() => onToggleMapping(m)}
                    >
                      {m.is_active ? '✓' : ''}
                    </button>
                    <div className="entity-labels">
                      <span className="entity-gliner">{m.gliner_label}</span>
                      <span className="entity-presidio">→ {m.presidio_label}</span>
                    </div>
                    <button
                      className="entity-del"
                      onClick={() => onDeleteMapping(m.id)}
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-title">Add Mapping</div>
            <div className="add-form">
              <input
                placeholder="New GLiNER label..."
                value={newLabel}
                onChange={(e) => onNewLabelChange(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && onAddMapping()}
              />
              <button onClick={onAddMapping} disabled={!newLabel.trim()}>
                Add
              </button>
            </div>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-title">Custom Regex Patterns</div>
            {regexPatterns.length === 0 ? (
              <div className="entity-empty">No custom patterns</div>
            ) : (
              <div className="regex-list">
                {regexPatterns.map((p) => (
                  <RegexPatternItem
                    key={p.id}
                    pattern={p}
                    onToggle={() => onToggleRegexPattern(p)}
                    onUpdate={(data) => onUpdateRegexPattern(p.id, data)}
                    onDelete={() => onDeleteRegexPattern(p.id)}
                  />
                ))}
              </div>
            )}
            <RegexForm onSubmit={(vals) => onAddRegexPattern(vals.name, vals.pattern, vals.entity_type, parseFloat(vals.score))} />
          </div>
        </div>
      </div>
    </div>
  )
}