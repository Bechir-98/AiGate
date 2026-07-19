import { type Mapping } from './api'
import './Sidebar.css'

const SCANNERS = ['spacy', 'gliner1', 'gliner2'] as const

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
  activeScanner: string
  onScannerChange: (scanner: string) => void
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
  activeScanner,
  onScannerChange,
}: SidebarProps) {
  return (
    <div className={`sidebar ${open ? 'open' : 'closed'}`}>
      <div className="sidebar-inner">
        <div className="sidebar-header">
          <h2>Entity Mappings</h2>
        </div>
        <div className="sidebar-body">
          <div className="sidebar-section">
            <div className="sidebar-section-title">Detection Engine</div>
            <div className="scanner-group">
              {SCANNERS.map((s) => (
                <button
                  key={s}
                  className={`scanner-btn ${activeScanner === s ? 'active' : ''}`}
                  onClick={() => onScannerChange(s)}
                >
                  {s === 'spacy' ? 'SpaCy' : s === 'gliner1' ? 'GLiNER v1' : 'GLiNER v2'}
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
        </div>
      </div>
    </div>
  )
}
