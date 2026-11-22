// plan&check（学習計画、/planandcheck/）。学習コーナーのトップ。ダッシュボードの「はじめる」のカードから開く。
// 画面では「巡」を Round と書く。
// 受験日だけを入れると、apps/fe/plan.py が中分類の日程を3巡ぶん組む。
//   1巡目：学習モードの順（科目A 1〜23 → 科目B）。2巡目以降：前の巡の正答率が低い順（その巡が始まってから組む）
//   巡の中で、どの小分類も 5問以上・正答率 80％以上になった中分類は合格。後の巡の日程から外れる
//   表のセルには、小分類のうち基準に届いた数（「小分類 2/5」）を出し、押すと小分類ごとの結果が開く
// 上から、帯（総合正答率・受験日・いまの巡・合格の数・未実施の数）→ 今日の中分類 → 中分類 × 巡の表 → 受験日の変更。
// 帯は計画が無くても総合正答率だけは出す。この画面には戻るボタンを置かない（ヘッダーから移る）。
// 1問1答と学習モードは、今日の中分類の「1問1答」「解説」から開く（Round ごとの結果の表は表示だけ）。出題設定をその中分類にしてから開く。
// 学習モードは入口（学習対象・読む時間を選ぶ画面）を通さず、その中分類のおまかせでラウンドを始めて読む画面へ移る。
// 開いた先は学習コーナー（corner.tsx）で、中分類を固定し、選択肢を出さず、plan&check へ戻るボタンを出す。
// この画面を開くたびに、学習コーナーの中分類を忘れる。
// 予定の日を過ぎても1問も解いていない中分類は「未実施」（正答率 0％）として目立たせる。持ち越さない。
// 計画は ID ごとに持つので、ID なしのとき（URL を直接開いたとき）はダッシュボードへ戻す。ID の入力画面へは案内しない。

import { useEffect, useState, type FormEvent } from 'react'
import { Navigate, useNavigate } from 'react-router'

import { useMe } from './App'
import { clearCorner, setCorner } from './corner'
import { api, type Plan, type PlanCell, type PlanResponse, type PlanRow } from './api'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { useLoad } from './useLoad'
import { usePageView } from './usePageView'

/** 2026-11-21 → 11/21 */
const md = (iso: string) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8))}`
const percent = (value: number | null) => (value === null ? '—' : `${value}％`)

/** 受験日に選べる最初の日（今日から3日後。plan.MIN_DAYS） */
function earliest(today: string) {
  const d = new Date(`${today}T00:00:00`)
  d.setDate(d.getDate() + 3)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

export function PlanPage() {
  usePageView('plan')
  const { me } = useMe()
  useEffect(clearCorner, [])
  if (me.is_temporary) return <Navigate to="/" replace />
  return <PlanBody />
}

function PlanBody() {
  const { data, setData, error, reload } = useLoad(api.plan)

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={4} />

  return (
    <>
      <Band data={data} />
      {data.plan ? (
        <>
          <Today plan={data.plan} />
          <RoundTable plan={data.plan} passPercent={data.pass_percent} />
        </>
      ) : null}
      <ExamDateForm data={data} onSaved={setData} />
    </>
  )
}

/** いちばん上の帯。総合正答率と、計画があれば受験日・いまの Round・合格・未実施 */
function Band({ data }: { data: PlanResponse }) {
  const plan = data.plan
  const current = plan?.rounds.find((r) => r.no === plan.current_round)
  return (
    <section className="fe-section fe-band">
      <div className="fe-band-item">
        <div className="fe-band-label">総合正答率</div>
        <div className="fe-band-value">{percent(data.overall.rate_percent)}</div>
        <div className="fe-band-sub">{data.overall.correct} / {data.overall.total} 問</div>
      </div>
      {plan && (
        <>
          <div className="fe-band-item">
            <div className="fe-band-label">受験日</div>
            <div className="fe-band-value">{md(plan.exam_date)}</div>
            <div className="fe-band-sub">あと {plan.days_left} 日</div>
          </div>
          <div className="fe-band-item">
            <div className="fe-band-label">Round</div>
            <div className="fe-band-value">{current ? current.no : '—'}</div>
            <div className="fe-band-sub">{current?.first && current.last ? `${md(current.first)}〜${md(current.last)}` : ''}</div>
          </div>
          <div className="fe-band-item">
            <div className="fe-band-label">合格</div>
            <div className="fe-band-value">{plan.passed_count}<small> / {plan.rows.length}</small></div>
          </div>
          <div className={`fe-band-item${plan.missed_count ? ' fe-band-missed' : ''}`}>
            <div className="fe-band-label">未実施</div>
            <div className="fe-band-value">{plan.missed_count}</div>
          </div>
        </>
      )}
    </section>
  )
}

/** 中分類の「解説」「1問1答」。出題設定をその中分類にしてから開く。「解説」は学習モード（読む → 解く）を始める */
function StudyButtons({ subject, code, label }: { subject: string; code: number; label: string }) {
  const navigate = useNavigate()
  const toast = useToast()
  const [busy, setBusy] = useState(false)

  const open = async (to: 'learn' | 'quiz') => {
    setBusy(true)
    try {
      await api.saveSettings('category', subject, code)
      setCorner({ subject, code, label })
      if (to === 'learn') {
        // 学習モードは入口を通さず、その中分類まるごと（解説をすべて読み、小分類ごとに解く）で始める
        const { round } = await api.startRound(null, null, 'category')
        navigate(`/learn/${round.id}/read/`)
      } else {
        navigate('/quiz/')
      }
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
      setBusy(false)
    }
  }

  return (
    <div className="fe-plan-actions">
      <button type="button" className="btn btn-outline-primary btn-sm" disabled={busy}
              onClick={() => void open('learn')}>解説</button>
      <button type="button" className="btn btn-primary btn-sm" disabled={busy}
              onClick={() => void open('quiz')}>1問1答</button>
    </div>
  )
}

/** 今日の中分類 */
function Today({ plan }: { plan: Plan }) {
  return (
    <section className="fe-section">
      <h2 className="fe-section-title">今日</h2>
      {plan.today.length === 0 ? (
        <p className="fe-muted small">今日の中分類はありません。</p>
      ) : (
        <div className="fe-plan-list">
          {plan.today.map((row) => (
            <div key={row.code} className="fe-card fe-plan-today">
              <div>
                <span className="fe-badge me-2">{row.subject === 'B' ? '科目B' : '科目A'}</span>
                <strong>{row.label}</strong>
                <span className="fe-muted small ms-2">
                  {row.answered ? `${row.correct}/${row.answered}（${percent(row.rate_percent)}）` : ''}
                </span>
              </div>
              <StudyButtons subject={row.subject} code={row.code} label={row.label} />
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

/** 中分類 × 巡の表。表示だけ（ボタンは置かない）。各巡のセルに日程と、その巡の正解数／解答数・正答率。
 *  合格した行は緑、合格していないで未実施のある行は赤。過ぎた巡の未実施は、合格してもセルに残す */
function RoundTable({ plan, passPercent }: { plan: Plan; passPercent: number }) {
  const groups: { subject: string; rows: PlanRow[] }[] = []
  for (const row of plan.rows) {
    const last = groups[groups.length - 1]
    if (last && last.subject === row.subject) last.rows.push(row)
    else groups.push({ subject: row.subject, rows: [row] })
  }

  return (
    <section className="fe-section">
      <h2 className="fe-section-title">Round ごとの結果</h2>
      <div className="fe-card fe-table-wrap">
        <table className="fe-table fe-plan-table">
          <thead>
            <tr>
              <th>中分類</th>
              {plan.rounds.map((r) => (
                <th key={r.no} className={r.no === plan.current_round ? 'fe-plan-current' : ''}>
                  Round {r.no}
                  <div className="fe-plan-range">{r.first && r.last ? `${md(r.first)}〜${md(r.last)}` : ''}</div>
                </th>
              ))}
              <th>合格</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => [
              <tr key={`h-${group.subject}`} className="fe-plan-subject">
                <td colSpan={plan.rounds.length + 2}>{group.subject === 'B' ? '科目B' : '科目A'}</td>
              </tr>,
              ...group.rows.map((row) => (
                <tr key={row.code} className={row.passed ? 'fe-row-pass' : row.rounds.some((c) => c.missed) ? 'fe-row-missed' : ''}>
                  <td className="fe-plan-name">{row.label}</td>
                  {row.rounds.map((cell, i) => (
                    <td key={i}>
                      <Cell cell={cell} built={plan.rounds[i].built} passPercent={passPercent} />
                    </td>
                  ))}
                  <td>
                    {row.passed ? (
                      <>
                        <span className="fe-badge fe-badge-good">合格</span>
                        <div className="fe-plan-range">Round {row.passed.round_no} {md(row.passed.passed_on)}</div>
                      </>
                    ) : null}
                  </td>
                </tr>
              )),
            ])}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function Cell({ cell, built, passPercent }: { cell: PlanCell; built: boolean; passPercent: number }) {
  if (!built && !cell.answered) return <span className="fe-muted">—</span>
  if (cell.missed) {
    return (
      <>
        <div className="fe-plan-range">{cell.dates.map(md).join('・')}</div>
        <div className="fe-plan-result">
          <span className="fe-missed">未実施</span>
          <span className="fe-bad ms-1">0％</span>
        </div>
      </>
    )
  }
  const rate = cell.rate_percent
  const tone = rate === null ? '' : rate >= passPercent ? 'fe-good' : rate < 60 ? 'fe-bad' : 'fe-warn'
  const total = cell.topics.length
  return (
    <>
      <div className="fe-plan-range">{cell.dates.map(md).join('・')}</div>
      {cell.answered > 0 && (
        <div className="fe-plan-result">
          <span className={tone}>{percent(rate)}</span>
          <span className="fe-muted small ms-1">{cell.correct}/{cell.answered}</span>
        </div>
      )}
      {/* 小分類のうち合格の基準に届いた数。全部そろうと中分類が合格。どれが残っているかは押すと開く */}
      {cell.answered > 0 && total > 0 && (
        <details className="fe-plan-topics">
          <summary className={cell.topics_passed === total ? 'fe-good' : 'fe-muted'}>
            小分類 {cell.topics_passed}/{total}
          </summary>
          <ul>
            {cell.topics.map((t) => (
              <li key={t.topic}>
                <span className={t.passed ? 'fe-good' : t.answered ? 'fe-warn' : 'fe-muted'}>{t.passed ? '✓' : '・'}</span>
                {t.topic}
                <span className="fe-muted ms-1">{t.answered ? `${percent(t.rate_percent)} ${t.correct}/${t.answered}` : '未'}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  )
}

/** 受験日。計画が無ければ組み、あれば組み直す（巡ごとの結果は消え、合格は残る） */
function ExamDateForm({ data, onSaved }: { data: PlanResponse; onSaved: (d: PlanResponse) => void }) {
  const toast = useToast()
  const [examDate, setExamDate] = useState(data.plan?.exam_date ?? '')
  const [sending, setSending] = useState(false)

  const run = async (action: () => Promise<PlanResponse>) => {
    setSending(true)
    try {
      onSaved(await action())
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
    } finally {
      setSending(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (data.plan && !window.confirm('計画を組み直します。Round ごとの結果は消え、合格は残ります。')) return
    void run(() => api.makePlan(examDate))
  }

  const drop = () => {
    if (!window.confirm('plan&check をやめます。Round ごとの結果は消え、合格は残ります。')) return
    void run(api.dropPlan)
  }

  return (
    <section className="fe-section">
      <div className="fe-card">
        <form className="fe-pass-form" onSubmit={submit}>
          <div>
            <label className="form-label" htmlFor="fe-exam-date">受験日</label>
            <input id="fe-exam-date" type="date" className="form-control form-control-sm" required
                   min={earliest(data.today)} value={examDate} onChange={(e) => setExamDate(e.target.value)} />
          </div>
          <button type="submit" className="btn btn-sm btn-primary" disabled={sending || !examDate}>
            {data.plan ? '組み直す' : '計画を立てる'}
          </button>
          {data.plan && (
            <button type="button" className="btn btn-sm btn-outline-secondary" disabled={sending} onClick={drop}>
              計画をやめる
            </button>
          )}
        </form>
      </div>
    </section>
  )
}
