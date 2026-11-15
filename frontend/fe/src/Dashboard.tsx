// ダッシュボード。上から次の順に並べる。
//   ID あり：自分の成績（4枚・苦手分野・未着手・分野別・直近14日） → みんなの集計（と合格の申告）
//            → 「1問1答」「学習モード」のボタン → 問題メール
//   ID なし：みんなの集計 → 「1問1答」「学習モード」のボタン → ID を作る案内 → 問題メール
// 出題設定は1問1答の画面で変える。説明は「このアプリについて」にまとめる。

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { useMe } from './App'
import { api, type Dashboard as DashboardData, type Personal } from './api'
import { Icon } from './Icon'
import { MailSection } from './MailSection'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { useLoad } from './useLoad'

const percent = (value: number | null) => (value === null ? '—' : `${value}％`)

export function Dashboard() {
  const { me } = useMe()
  const board = useLoad(api.dashboard)

  if (board.error) return <LoadError message={board.error} onRetry={() => void board.reload()} />
  if (!board.data) return <Loading rows={4} />
  const data = board.data

  return (
    <>
      {data.personal && <PersonalStats personal={data.personal} questionTotal={data.question_total} />}

      <Summary data={data} temporary={me.is_temporary} onChange={() => void board.reload()} />

      {/* 出題（出題設定は1問1答の画面で変える）。集計の下に、ボタンを縦に並べて、それぞれ短い説明を添える */}
      <section className="fe-section">
        <div className="fe-start-list">
          <div className="fe-start-row">
            <Link to="/quiz/" className="btn btn-primary btn-sm">
              <Icon name="play" className="me-2" />1問1答
            </Link>
            <span className="fe-muted small">苦手な分野を重めに、1問ずつ出題します。出題設定で分野や出し方を変えられます。</span>
          </div>
          <div className="fe-start-row">
            <Link to="/learn/" className="btn btn-outline-primary btn-sm">
              <Icon name="book-open" className="me-2" />学習モード
            </Link>
            <span className="fe-muted small">技術解説を読んでから、その範囲の問題を解きます。</span>
          </div>
        </div>
        {data.question_total === 0 && (
          <div className="fe-card fe-warning mt-3">
            問題集はまだ用意されていません。用意されるまでは、計算問題だけを出題します。
          </div>
        )}
      </section>

      {/* 記録を残したくなった人への案内（ID なしのときだけ） */}
      {me.is_temporary && (
        <section className="fe-section">
          <div className="fe-card fe-invite">
            <div>
              <div className="fe-invite-title"><Icon name="save" className="me-2" />学習の記録を残しませんか</div>
              <div className="fe-muted small">
                いまの記録はブラウザを閉じると消えます。ID を作ると記録が残り、別の端末からも続きを開けて、問題メールで答えた分も記録されます。
              </div>
            </div>
            <div className="fe-invite-actions">
              <Link to="/id/" className="btn btn-primary btn-sm">ID を作って記録を残す</Link>
              <Link to="/id/" className="btn btn-outline-primary btn-sm">ID をお持ちの方はこちら</Link>
            </div>
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
      <section className="fe-section fe-tiles">
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">総合正答率</div>
          <div className="fe-tile-value">{percent(o.rate_percent)}</div>
          <div className="fe-tile-sub">{o.correct} / {o.total} 問正解</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">直近{o.recent_days}日の正答率</div>
          <div className="fe-tile-value">{percent(o.recent_rate_percent)}</div>
          <div className="fe-tile-sub">目安は {o.pass_line_percent}％以上</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">学習した日数</div>
          <div className="fe-tile-value">{o.study_days}<small> 日</small></div>
          <div className="fe-tile-sub">継続が一番効く</div>
        </div>
        <div className="fe-card fe-tile">
          <div className="fe-tile-label">収録問題</div>
          <div className="fe-tile-value">{questionTotal}<small> 問</small></div>
          <div className="fe-tile-sub">＋ 計算問題 {personal.template_total} 型</div>
        </div>
      </section>

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
