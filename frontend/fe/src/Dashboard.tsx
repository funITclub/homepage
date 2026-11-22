// ダッシュボード。上から次の順に並べる。「はじめる」のカードは、押すと plan&check（/planandcheck/）へ移る。
// plan&check はヘッダーのメニューに出さず、このカードからだけ開く。計画は ID ごとに持つので、カードは ID ありのときだけ出す。
//   ID あり：帯（総合正答率・直近の正答率・学習した日数・収録問題） → 「はじめる」のカード → 苦手分野・未着手・分野別・直近14日
//            → みんなの集計（と合格の申告） → 問題メール
//   ID なし：みんなの集計 → 問題メール（「はじめる」のカードは出さない）
//            開いたときに ID の入力のポップアップ（IdPopup.tsx）を出す（「次回から表示しない」まで）
// 1問1答と学習モードのボタンは置かない（plan&check の計画の中分類か、ヘッダーのメニューから開く）。
// ダッシュボードを開いたら、学習コーナーの中分類（corner.tsx）を忘れる。
// 出題設定は1問1答の画面で変える。説明は「このアプリについて」にまとめる。

import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { useMe } from './App'
import { clearCorner } from './corner'
import { api, type Dashboard as DashboardData, type Personal } from './api'
import { Icon } from './Icon'
import { IdPopup } from './IdPopup'
import { MailSection } from './MailSection'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { useLoad } from './useLoad'

const percent = (value: number | null) => (value === null ? '—' : `${value}％`)

export function Dashboard() {
  const { me } = useMe()
  const board = useLoad(api.dashboard)
  useEffect(clearCorner, [])

  if (board.error) return <LoadError message={board.error} onRetry={() => void board.reload()} />
  if (!board.data) return <Loading rows={4} />
  const data = board.data

  return (
    <>
      {me.is_temporary && <IdPopup onEntered={() => void board.reload()} />}

      {data.personal && <PersonalStats personal={data.personal} questionTotal={data.question_total} />}

      <Summary data={data} temporary={me.is_temporary} onChange={() => void board.reload()} />

      {data.question_total === 0 && (
        <section className="fe-section">
          <div className="fe-card fe-warning">
            問題集はまだ用意されていません。用意されるまでは、計算問題だけを出題します。
          </div>
        </section>
      )}

      {/* 問題メール（ID なしでも登録できる。答えた分は ID ありならその ID に、ID なしならみんなの集計にだけ） */}
      <MailSection />
    </>
  )
}

/** 自分の成績（ID があるときだけ）。以前のダッシュボードと同じ中身 */
function PersonalStats({ personal, questionTotal }: { personal: Personal; questionTotal: number }) {
  const o = personal.overall
  const maxDaily = Math.max(1, ...personal.daily.map((d) => d.total))
  return (
    <>
      {/* いちばん上の帯（plan&check の帯と同じ見た目） */}
      <section className="fe-section fe-band">
        <div className="fe-band-item">
          <div className="fe-band-label">総合正答率</div>
          <div className="fe-band-value">{percent(o.rate_percent)}</div>
          <div className="fe-band-sub">{o.correct} / {o.total} 問正解</div>
        </div>
        <div className="fe-band-item">
          <div className="fe-band-label">直近{o.recent_days}日の正答率</div>
          <div className="fe-band-value">{percent(o.recent_rate_percent)}</div>
          <div className="fe-band-sub">目安は {o.pass_line_percent}％以上</div>
        </div>
        <div className="fe-band-item">
          <div className="fe-band-label">学習した日数</div>
          <div className="fe-band-value">{o.study_days}<small> 日</small></div>
          <div className="fe-band-sub">継続が一番効く</div>
        </div>
        <div className="fe-band-item">
          <div className="fe-band-label">収録問題</div>
          <div className="fe-band-value">{questionTotal}<small> 問</small></div>
          <div className="fe-band-sub">＋ 計算問題 {personal.template_total} 型</div>
        </div>
      </section>

      <StartCard />

      <section className="fe-section">
        <h2 className="fe-section-title">苦手分野</h2>
        {personal.weak.length === 0 ? (
          <p className="fe-muted small">
            いま苦手と判定している分野はありません。3問以上解いた分野のうち，60％ に寄せて平滑化した正答率が 60％ を下回るものが，ここに苦手な順で並びます。
          </p>
        ) : (
          <div className="fe-list">
            {personal.weak.map((row) => {
              const bad = (row.rate_percent ?? 0) < 50
              return (
                <div key={row.code} className="fe-card fe-weak">
                  <div className="fe-weak-head">
                    <div>
                      <span className="fe-badge me-2">{row.field}</span>
                      <strong>{row.label}</strong>
                      <span className="fe-muted small ms-2">
                        本番の想定出題数 {row.exam_weight} 問／{row.subject === 'B' ? 20 : 60}問
                      </span>
                    </div>
                    <div className="text-end">
                      <span className={bad ? 'fe-bad' : 'fe-warn'}>{percent(row.rate_percent)}</span>
                      <span className="fe-muted small">（{row.correct}/{row.total}）</span>
                    </div>
                  </div>
                  <div className="fe-bar">
                    <span className={bad ? 'fe-bar-bad' : 'fe-bar-warn'} style={{ width: `${row.rate_percent ?? 0}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </section>

      {personal.untouched.length > 0 && (
        <section className="fe-section">
          <h2 className="fe-section-title">まだ手を付けていない分野</h2>
          <div className="fe-chips">
            {personal.untouched.map((c) => <span key={c.code} className="fe-chip">{c.label}</span>)}
          </div>
          <p className="fe-muted small mt-2">実力が分からない分野は，おまかせモードで優先的に出題されます。</p>
        </section>
      )}

      <section className="fe-section">
        <h2 className="fe-section-title">分野別の正答率</h2>
        <div className="fe-fields">
          {personal.fields.map((f) => (
            <div key={f.label} className="fe-card">
              <div className="d-flex justify-content-between">
                <strong>{f.label}</strong>
                <span>{percent(f.rate_percent)}</span>
              </div>
              <div className="fe-bar mt-2"><span style={{ width: `${f.rate_percent ?? 0}%` }} /></div>
              <div className="fe-muted small mt-1">{f.correct} / {f.total} 問　本番の想定 {f.weight} 問／60問</div>
            </div>
          ))}
        </div>
      </section>

      <section className="fe-section">
        <h2 className="fe-section-title">直近14日の解答数</h2>
        <div className="fe-card fe-daily">
          {personal.daily.map((day) => (
            <div key={day.date} className="fe-daily-col"
                 title={`${Number(day.date.slice(5, 7))}月${Number(day.date.slice(8))}日 ${day.total}問（正解 ${day.correct}）`}>
              <div className="fe-daily-bar" style={{ height: `${(day.total / maxDaily) * 100}%`, minHeight: day.total ? 4 : 0 }} />
              <div className="fe-daily-day">{Number(day.date.slice(8))}</div>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

/** みんなの集計。個人の成績は出さない。ID があれば、合格の申告もここで受け付ける */
function Summary({ data, temporary, onChange }: { data: DashboardData; temporary: boolean; onChange: () => void }) {
  const s = data.summary
  return (
    <section className="fe-section" id="summary">
      <h2 className="fe-section-title">みんなの集計</h2>
      <div className="fe-tiles">
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">のべ解答数</div>
          <div className="fe-tile-value">{s.total}<small> 問</small></div>
          <div className="fe-tile-sub">うち正解 {s.correct} 問</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">全体の正答率</div>
          <div className="fe-tile-value">{s.rate_percent === null ? '—' : <>{s.rate_percent}<small> ％</small></>}</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">学習した人</div>
          <div className="fe-tile-value">{s.learners}<small> 人</small></div>
          <div className="fe-tile-sub">1問以上解いた人</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">合格者数</div>
          <div className="fe-tile-value">{s.passers}<small> 人</small></div>
          <div className="fe-tile-sub">本番合格の申告数</div>
        </div>
      </div>
      {/* 消える記録から申告されると合格者数が実態と合わなくなるので、履歴を残さない利用では出さない */}
      {!temporary && <PassReport data={data} onChange={onChange} />}
    </section>
  )
}

function PassReport({ data, onChange }: { data: DashboardData; onChange: () => void }) {
  const toast = useToast()
  const [passedOn, setPassedOn] = useState('')
  const [sending, setSending] = useState(false)

  const run = async (action: () => Promise<{ message: string }>) => {
    setSending(true)
    try {
      const { message } = await action()
      toast.show(message, { kind: 'success' })
      onChange()
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
    } finally {
      setSending(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void run(() => api.reportPass(passedOn))
  }

  if (data.my_report) {
    const [y, m, d] = data.my_report.passed_on.split('-').map(Number)
    return (
      <div className="fe-card fe-pass">
        <div>
          <strong>合格を申告済みです</strong>
          <span className="fe-muted small ms-2">受験日 {y}年{m}月{d}日</span>
        </div>
        <button type="button" className="btn btn-sm btn-outline-secondary" disabled={sending}
                onClick={() => void run(api.withdrawPass)}>申告を取り消す</button>
      </div>
    )
  }

  return (
    <div className="fe-card">
      <div className="mb-2"><strong>本番に合格したら、ここで申告してください</strong></div>
      <form className="fe-pass-form" onSubmit={submit}>
        <div>
          <label className="form-label" htmlFor="fe-passed-on">合格した試験の受験日</label>
          <input id="fe-passed-on" type="date" className="form-control form-control-sm" required
                 max={data.today} value={passedOn} onChange={(e) => setPassedOn(e.target.value)} />
        </div>
        <button type="submit" className="btn btn-sm btn-primary" disabled={sending || !passedOn}>合格を申告する</button>
      </form>
      <div className="fe-muted small mt-2">合格者数に1人ぶん加わります。名前は表示されません。あとから取り消せます。</div>
    </div>
  )
}

/** 「はじめる」のカード。押すと plan&check（学習コーナーのトップ）へ移る */
function StartCard() {
  return (
    <section className="fe-section">
      <Link to="/planandcheck/" className="fe-card fe-start-card text-decoration-none">
        <span className="fe-start-card-title">はじめる</span>
        <Icon name="arrow-right" />
      </Link>
    </section>
  )
}
