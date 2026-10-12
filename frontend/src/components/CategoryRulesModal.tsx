import { useState, type ChangeEvent } from 'react'
import { LuDownload, LuPlus, LuTrash2, LuUpload, LuX } from 'react-icons/lu'
import type { CategoryRule, CategoryRulesData } from '../types/budget'
import { downloadCategoryRulesFile, saveCategoryRules } from '../api/budget'

interface CategoryRulesModalProps {
  isOpen: boolean
  initialData: CategoryRulesData
  onClose: () => void
  onSaved: (newData: CategoryRulesData) => void
}

export function CategoryRulesModal({
  isOpen,
  initialData,
  onClose,
  onSaved,
}: CategoryRulesModalProps) {
  const [rules, setRules] = useState<CategoryRule[]>(() => initialData.rules)
  const [defaultCategory, setDefaultCategory] = useState<string>(
    initialData.default_category || 'Uncategorized',
  )
  const [viewMode, setViewMode] = useState<'visual' | 'raw'>('visual')
  const [rawJson, setRawJson] = useState<string>(() =>
    JSON.stringify(initialData, null, 2),
  )
  const [rawError, setRawError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)

  // New rule inputs
  const [newPattern, setNewPattern] = useState('')
  const [newCategory, setNewCategory] = useState('')
  const [newMatchType, setNewMatchType] = useState<
    'contains' | 'exact' | 'starts_with' | 'regex'
  >('contains')

  if (!isOpen) return null

  const handleAddRule = () => {
    if (!newPattern.trim() || !newCategory.trim()) return
    const updated = [
      ...rules,
      {
        pattern: newPattern.trim(),
        category: newCategory.trim(),
        match_type: newMatchType,
      },
    ]
    setRules(updated)
    setNewPattern('')
    setNewCategory('')
    setNewMatchType('contains')
    setRawJson(
      JSON.stringify(
        { rules: updated, default_category: defaultCategory },
        null,
        2,
      ),
    )
  }

  const handleDeleteRule = (index: number) => {
    const updated = rules.filter((_, i) => i !== index)
    setRules(updated)
    setRawJson(
      JSON.stringify(
        { rules: updated, default_category: defaultCategory },
        null,
        2,
      ),
    )
  }

  const handleRuleChange = (
    index: number,
    field: keyof CategoryRule,
    value: string,
  ) => {
    const updated = rules.map((r, i) => {
      if (i !== index) return r
      return { ...r, [field]: value }
    })
    setRules(updated)
    setRawJson(
      JSON.stringify(
        { rules: updated, default_category: defaultCategory },
        null,
        2,
      ),
    )
  }

  const handleDefaultCategoryChange = (val: string) => {
    setDefaultCategory(val)
    setRawJson(JSON.stringify({ rules, default_category: val }, null, 2))
  }

  const handleRawJsonChange = (val: string) => {
    setRawJson(val)
    try {
      const parsed = JSON.parse(val) as CategoryRulesData
      if (Array.isArray(parsed.rules)) {
        setRules(parsed.rules)
        setDefaultCategory(parsed.default_category || 'Uncategorized')
        setRawError(null)
      } else {
        setRawError('JSON must include a "rules" array')
      }
    } catch {
      setRawError('Invalid JSON format')
    }
  }

  const handleExport = () => {
    const dataToExport: CategoryRulesData = {
      rules,
      default_category: defaultCategory,
    }
    downloadCategoryRulesFile(dataToExport)
  }

  const handleImportFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const text = e.target?.result as string
        const parsed = JSON.parse(text) as CategoryRulesData
        if (Array.isArray(parsed.rules)) {
          setRules(parsed.rules)
          const def = parsed.default_category || 'Uncategorized'
          setDefaultCategory(def)
          setRawJson(JSON.stringify(parsed, null, 2))
          setRawError(null)
          setSaveMessage('File loaded successfully! Click Save to apply.')
        } else {
          setRawError('Imported file must contain a "rules" array')
        }
      } catch (err) {
        setRawError(
          err instanceof Error
            ? `Failed to parse file: ${err.message}`
            : 'Invalid JSON file',
        )
      }
    }
    reader.readAsText(file)
    // Reset file input
    event.target.value = ''
  }

  const handleSave = async () => {
    setSaving(true)
    setSaveMessage(null)
    setRawError(null)

    let dataToSave: CategoryRulesData
    if (viewMode === 'raw') {
      try {
        dataToSave = JSON.parse(rawJson) as CategoryRulesData
      } catch {
        setRawError('Cannot save invalid JSON')
        setSaving(false)
        return
      }
    } else {
      dataToSave = {
        rules,
        default_category: defaultCategory,
      }
    }

    try {
      await saveCategoryRules(dataToSave)
      setSaveMessage('Rules saved to category_rules.json successfully!')
      onSaved(dataToSave)
      setTimeout(() => {
        onClose()
      }, 700)
    } catch (err) {
      setRawError(err instanceof Error ? err.message : 'Failed to save rules')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="modal-title">
      <div className="modal-window">
        <header className="modal-header">
          <div>
            <p className="kicker">Rules file: category_rules.json</p>
            <h2 id="modal-title" className="modal-title">Category Rules</h2>
          </div>
          <button
            type="button"
            className="modal-close-button"
            onClick={onClose}
            aria-label="Close modal"
          >
            <LuX size={20} aria-hidden="true" />
          </button>
        </header>

        <div className="modal-toolbar">
          <div className="modal-tabs">
            <button
              type="button"
              className={`tab-btn ${viewMode === 'visual' ? 'tab-btn--active' : ''}`}
              onClick={() => setViewMode('visual')}
            >
              Rule Editor ({rules.length})
            </button>
            <button
              type="button"
              className={`tab-btn ${viewMode === 'raw' ? 'tab-btn--active' : ''}`}
              onClick={() => {
                setRawJson(
                  JSON.stringify(
                    { rules, default_category: defaultCategory },
                    null,
                    2,
                  ),
                )
                setViewMode('raw')
              }}
            >
              Raw JSON
            </button>
          </div>

          <div className="modal-file-actions">
            <button
              type="button"
              className="action-btn"
              onClick={handleExport}
              title="Download category_rules.json to your computer"
            >
              <LuDownload size={14} aria-hidden="true" />
              Export File
            </button>
            <label className="action-btn action-btn--file">
              <LuUpload size={14} aria-hidden="true" />
              Import File
              <input
                type="file"
                accept=".json,application/json"
                onChange={handleImportFile}
                style={{ display: 'none' }}
              />
            </label>
          </div>
        </div>

        <div className="modal-content">
          {viewMode === 'visual' ? (
            <div className="rules-editor">
              <div className="default-category-row">
                <label className="field-inline">
                  <span>Default Category (when no rule matches):</span>
                  <input
                    type="text"
                    value={defaultCategory}
                    onChange={(e) => handleDefaultCategoryChange(e.target.value)}
                    placeholder="Uncategorized"
                  />
                </label>
              </div>

              <div className="new-rule-card">
                <h4>Add New Rule</h4>
                <div className="new-rule-fields">
                  <label className="field">
                    <span>Pattern / Keyword</span>
                    <input
                      type="text"
                      placeholder="e.g. Netflix or Uber"
                      value={newPattern}
                      onChange={(e) => setNewPattern(e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Match Type</span>
                    <select
                      value={newMatchType}
                      onChange={(e) =>
                        setNewMatchType(
                          e.target.value as 'contains' | 'exact' | 'starts_with' | 'regex',
                        )
                      }
                    >
                      <option value="contains">Contains (substring)</option>
                      <option value="exact">Exact match</option>
                      <option value="starts_with">Starts with</option>
                      <option value="regex">Regex</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Category</span>
                    <input
                      type="text"
                      placeholder="e.g. Subscriptions"
                      value={newCategory}
                      onChange={(e) => setNewCategory(e.target.value)}
                    />
                  </label>
                  <div className="new-rule-btn-wrap">
                    <button
                      type="button"
                      className="add-rule-btn"
                      onClick={handleAddRule}
                      disabled={!newPattern.trim() || !newCategory.trim()}
                    >
                      <LuPlus size={16} aria-hidden="true" />
                      Add Rule
                    </button>
                  </div>
                </div>
              </div>

              <div className="rules-table-container">
                <table className="rules-table">
                  <thead>
                    <tr>
                      <th style={{ width: '38%' }}>Pattern</th>
                      <th style={{ width: '22%' }}>Match Type</th>
                      <th style={{ width: '30%' }}>Category</th>
                      <th style={{ width: '10%' }}>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule, idx) => (
                      <tr key={`${rule.pattern}-${idx}`}>
                        <td>
                          <input
                            type="text"
                            value={rule.pattern}
                            onChange={(e) =>
                              handleRuleChange(idx, 'pattern', e.target.value)
                            }
                            placeholder="Pattern"
                          />
                        </td>
                        <td>
                          <select
                            value={rule.match_type || 'contains'}
                            onChange={(e) =>
                              handleRuleChange(
                                idx,
                                'match_type',
                                e.target.value,
                              )
                            }
                          >
                            <option value="contains">Contains</option>
                            <option value="exact">Exact</option>
                            <option value="starts_with">Starts with</option>
                            <option value="regex">Regex</option>
                          </select>
                        </td>
                        <td>
                          <input
                            type="text"
                            value={rule.category}
                            onChange={(e) =>
                              handleRuleChange(idx, 'category', e.target.value)
                            }
                            placeholder="Category"
                          />
                        </td>
                        <td>
                          <button
                            type="button"
                            className="delete-rule-btn"
                            onClick={() => handleDeleteRule(idx)}
                            title="Delete rule"
                            aria-label={
                              rule.pattern ? `Delete rule "${rule.pattern}"` : 'Delete rule'
                            }
                          >
                            <LuTrash2 size={16} aria-hidden="true" />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {rules.length === 0 && (
                      <tr>
                        <td colSpan={4} className="empty-rules-cell">
                          No rules added yet. Add a rule above or import a file.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div className="raw-json-editor">
              <p className="token-note">
                Directly edit the JSON specification for category classification.
                Must include <code>"rules"</code> array.
              </p>
              <textarea
                value={rawJson}
                onChange={(e) => handleRawJsonChange(e.target.value)}
                rows={16}
                spellCheck={false}
              />
            </div>
          )}

          {rawError && (
            <p className="feedback feedback--error" role="alert">
              {rawError}
            </p>
          )}
          {saveMessage && (
            <p className="feedback feedback--success" role="status">
              {saveMessage}
            </p>
          )}
        </div>

        <footer className="modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSave}
            disabled={saving || Boolean(rawError)}
          >
            {saving ? 'Saving…' : 'Save Rules & Reclassify'}
          </button>
        </footer>
      </div>
    </div>
  )
}

