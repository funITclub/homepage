// 学習モードの入口。学習対象（解説）と読む時間を選んでラウンドを始める。
//
// ・学習対象は中分類ごとに畳み、開くと小分類（解説）が1行ずつ並ぶ。出題できる問題の無い行は選べない
// ・最初に開いておくのは、ダッシュボードで指定した分野と、直前に学習した中分類（API の opened）。
//   選ぶのは利用者なので、どれも選んだ状態にはしない
// ・何も選ばなければ「おまかせ」（苦手な分野から選ぶ。分野を指定していればその中から）
// ・選んだ行と、それを含む中分類は目立たせる。畳んだままでもどこを選んだか分かるように

import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { api, type LearnStart } from './api'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

const when = (iso: string) => {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getMonth() + 1}/${d.getDate()} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function LearnStartPage() {
  usePageView('learn_start')
  const { data, error, reload } = useLoad(api.learn)
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={4} />
  return <LearnStartForm data={data} />
}

function LearnStartForm({ data }: { data: LearnStart }) {
  const toast = useToast()
  const navigate = useNavigate()
  const [note, setNote] = useState<number | null>(null)
  const [minutes, setMinutes] = useState(data.default_minutes)
  const [open, setOpen] = useState(() => new Set(data.groups.filter((g) => g.opened).map((g) => g.code)))
  const [sending, setSending] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setSending(true)
    try {
      const { round } = await api.startRound(minutes, note)
      navigate(`/learn/${round.id}/read/`)
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
      setSending(false)
    }
  }

  const toggle = (code: number) => {
    const next = new Set(open)
    if (next.has(code)) next.delete(code)
    else next.add(code)
    setOpen(next)
  }

  return (
    <div className="fe-narrow-wide">
      <p className="fe-muted">解説を読んでから、その小分類の問題を最大{data.count}問解きます。</p>

      <form className="fe-card fe-section" onSubmit={submit}>
        <div className="fe-card-title">学習対象</div>
        {data.groups.length === 0 ? (
          <div className="fe-warning">解説がありません。</div>
        ) : (
          <div className="fe-pick">
            <label className={`fe-pick-row fe-pick-auto${note === null ? ' fe-pick-on' : ''}`}>
              <input className="form-check-input mt-0" type="radio" name="note" checked={note === null}
                     onChange={() => setNote(null)} />
              <strong>おまかせ</strong>
            </label>
            {data.groups.map((group) => {
              const here = group.entries.some((e) => e.note === note)
              const isOpen = open.has(group.code)
              return (
                <div key={group.code} className={`fe-pick-group${here ? ' fe-pick-here' : ''}`}>
                  <button type="button" className="fe-pick-summary" aria-expanded={isOpen} onClick={() => toggle(group.code)}>
                    <span>
                      <span className="fe-muted small me-2">{group.code}</span>
                      <strong>{group.name}</strong>
                      <span className="fe-muted small ms-2">解説{group.note_count}本</span>
                      {here && <span className="fe-badge fe-badge-strong ms-2">選択中</span>}
                    </span>
                    <span className="small text-nowrap">
                      {group.rate_percent !== null
                        ? <span className={group.is_weak ? 'fe-bad' : 'fe-muted'}>正答率 {group.rate_percent}％</span>
                        : <span className="fe-muted">未着手</span>}
                      <span className="fe-muted ms-2">問題{group.question_count}問</span>
                      <span className="fe-pick-caret ms-2" aria-hidden="true">{isOpen ? '▾' : '▸'}</span>
                    </span>
                  </button>
                  {isOpen && (
                    <div className="fe-pick-entries">
                      {group.entries.map((entry) => (
                        <label key={entry.note}
                               className={`fe-pick-row${entry.questions ? '' : ' fe-pick-off'}${note === entry.note ? ' fe-pick-on' : ''}`}>
                          <input className="form-check-input mt-0" type="radio" name="note" checked={note === entry.note}
                                 disabled={!entry.questions} onChange={() => setNote(entry.note)} />
                          {entry.topic && <span className="fe-badge">{entry.topic}</span>}
                          <span>{entry.titles.join('／')}</span>
                          <span className={`small ${entry.questions ? 'fe-muted' : 'fe-bad'}`}>問題{entry.questions}問</span>
                          {entry.rounds
                            ? <span className="fe-muted small">学習{entry.rounds}回</span>
                            : <span className="fe-accent small">未読</span>}
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        <div className="fe-card-title mt-4">読む時間</div>
        <div className="fe-minutes">
          {data.minute_choices.map((m) => (
            <div key={m} className="form-check">
              <input className="form-check-input" type="radio" name="minutes" id={`fe-m${m}`}
                     checked={minutes === m} onChange={() => setMinutes(m)} />
              <label className="form-check-label" htmlFor={`fe-m${m}`}>{m}分</label>
            </div>
          ))}
        </div>
        <button type="submit" className="btn btn-primary" disabled={!data.groups.length || sending}>はじめる</button>
      </form>

      {data.recent.length > 0 && (
        <section className="fe-card">
          <div className="fe-card-title">これまでのラウンド</div>
          <ul className="fe-rounds">
            {data.recent.map((r) => (
              <li key={r.id}>
                <Link to={`/learn/${r.id}/result/`}>{r.has_note ? r.title : '（削除された解説）'}</Link>
                <span className="fe-muted small text-nowrap">{r.correct}/{r.total}問　{when(r.started_at)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
