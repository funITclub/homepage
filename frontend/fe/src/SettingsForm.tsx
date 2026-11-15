// 出題設定（出題モード・科目・分野）。1問1答の画面のいちばん下に置く。
//
// ・分野はどのモードでも選べる。選ぶと、そのモードの出し方のままその分野の中だけから出す。
// ・件数と選べるかどうかはモードで変わるので、API が全モードぶん（by_mode）を渡し、
//   モードを切り替えたらここで出し分ける。いまのモードで出せない分野は選べなくする。
// ・分類は科目ごとに別で、科目Aは中分類（1〜23）、科目Bは5項目（101〜105）。重なりが無いので、
//   選んだ科目の分類だけを並べる。科目を変えたり、選んでいた分野がそのモードで出せなく
//   なったりしたら「指定なし」に戻す。
// ・「分野を指定」は分野が無いと成り立たないので、分野を選ぶまで保存できない（API も断る）。

import { useState, type FormEvent } from 'react'

import { api, type Settings } from './api'
import { useToast } from './toast'

export function SettingsForm({
  settings,
  submitLabel,
  onSaved,
}: {
  settings: Settings
  /** ボタンの文言（1問1答は「この設定で出題」） */
  submitLabel: string
  onSaved: (settings: Settings) => void
}) {
  const toast = useToast()
  const [mode, setMode] = useState(settings.mode)
  const [subject, setSubject] = useState(settings.subject)
  const [category, setCategory] = useState<number | null>(settings.category)
  const [saving, setSaving] = useState(false)

  const options = settings.categories
    .filter((c) => c.subject === subject)
    .map((c) => {
      const [count, selectable] = c.by_mode[mode] ?? [c.question_count, c.question_count > 0]
      return { ...c, count, selectable }
    })

  const stillSelectable = (code: number | null, nextMode: string, nextSubject: string) => {
    const option = settings.categories.find((c) => c.code === code)
    return !!option && option.subject === nextSubject && !!option.by_mode[nextMode]?.[1]
  }

  const changeMode = (next: string) => {
    setMode(next)
    if (!stillSelectable(category, next, subject)) setCategory(null)
  }

  const changeSubject = (next: string) => {
    setSubject(next)
    if (!stillSelectable(category, mode, next)) setCategory(null)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    try {
      onSaved(await api.saveSettings(mode, subject, category))
    } catch (error) {
      toast.show((error as Error).message, { kind: 'danger' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="fe-settings" onSubmit={submit}>
      <div className="fe-settings-field">
        <label htmlFor="fe-mode" className="form-label">出題モード</label>
        <select id="fe-mode" className="form-select form-select-sm" value={mode}
                onChange={(e) => changeMode(e.target.value)}>
          {settings.modes.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
        </select>
      </div>
      <div className="fe-settings-field">
        <label htmlFor="fe-subject" className="form-label">科目</label>
        <select id="fe-subject" className="form-select form-select-sm" value={subject}
                onChange={(e) => changeSubject(e.target.value)}>
          {settings.subjects.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
        </select>
      </div>
      <div className="fe-settings-field">
        <label htmlFor="fe-category" className="form-label">分野</label>
        <select id="fe-category" className="form-select form-select-sm" value={category ?? ''}
                onChange={(e) => setCategory(e.target.value ? Number(e.target.value) : null)}>
          <option value="">指定なし</option>
          {options.map((o) => (
            <option key={o.code} value={o.code} disabled={!o.selectable}>
              {o.label}{o.count ? `（${o.count}問）` : ''}
            </option>
          ))}
        </select>
      </div>
      <button type="submit" className="btn btn-sm btn-outline-primary fe-settings-submit" disabled={saving}>
        {submitLabel}
      </button>
    </form>
  )
}
