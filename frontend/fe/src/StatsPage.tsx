// 分野別の正答率。科目で絞る（?subject=A|B。アドレスに持つ）。中分類ごとの表、分野ごとのまとめ、
// 「重点出題の比率」の読み方、直近14日の解答数。

import { useSearchParams } from 'react-router'

import { api } from './api'
import { LoadError, Loading } from './Status'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

const percent = (value: number | null) => (value === null ? '—' : `${value}％`)

/** 習得度の帯の色。50％未満・70％未満・それ以上 */
const barClass = (value: number | null) =>
  value === null ? '' : value < 50 ? 'fe-bar-bad' : value < 70 ? 'fe-bar-warn' : 'fe-bar-good'

export function StatsPage() {
  usePageView('stats')
  const [params, setParams] = useSearchParams()
  const subject = params.get('subject') ?? ''
  const { data, error, reload } = useLoad(() => api.stats(subject), [subject])

  const pick = (value: string) => setParams(value ? { subject: value } : {})
  const maxDaily = Math.max(1, ...(data?.daily ?? []).map((d) => d.total))

  return (
    <>
      <div className="fe-section fe-subject-filter">
        <button type="button" className={`btn btn-sm ${!subject ? 'btn-primary' : 'btn-outline-primary'}`}
                onClick={() => pick('')}>両科目</button>
        {(data?.subjects ?? [{ value: 'A', label: '科目A' }, { value: 'B', label: '科目B' }]).map((s) => (
          <button key={s.value} type="button"
                  className={`btn btn-sm ${subject === s.value ? 'btn-primary' : 'btn-outline-primary'}`}
                  onClick={() => pick(s.value)}>{s.label}</button>
        ))}
      </div>

      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!error && !data && <Loading rows={5} />}
      {data && (
        <>
          <section className="fe-section">
            <div className="fe-card fe-table-wrap">
              <table className="fe-table">
                <thead>
                  <tr>
                    <th>分野</th>
                    <th>中分類</th>
                    <th className="text-end">本番<br />想定</th>
                    <th className="text-end">解答数</th>
                    <th className="text-end">正答率</th>
                    <th className="fe-col-bar">習得度</th>
                    <th className="text-end">重点出題<br />の比率</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.code} className={row.is_weak ? 'fe-row-weak' : ''}>
                      <td className="fe-muted small">{row.field}</td>
                      <td>
                        {row.label}
                        {row.is_weak && <span className="fe-badge fe-badge-bad ms-1">苦手</span>}
                        {row.is_untouched && row.question_count > 0 && <span className="fe-badge ms-1">未着手</span>}
                        <div className="fe-muted small">出題可能 {row.question_count} 問</div>
                      </td>
                      <td className="text-end">{row.exam_weight}</td>
                      <td className="text-end">{row.total}</td>
                      <td className="text-end">{percent(row.rate_percent)}</td>
                      <td className="fe-col-bar">
                        <div className="fe-bar"><span className={barClass(row.rate_percent)} style={{ width: `${row.rate_percent ?? 0}%` }} /></div>
                      </td>
                      <td className="text-end fe-muted small">{row.focus_share}％</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="fe-section fe-fields">
            {data.fields.map((f) => (
              <div key={f.label} className="fe-card">
                <div className="d-flex justify-content-between">
                  <strong>{f.label}</strong>
                  <span>{percent(f.rate_percent)}</span>
                </div>
                <div className="fe-bar mt-2"><span style={{ width: `${f.rate_percent ?? 0}%` }} /></div>
                <div className="fe-muted small mt-1">{f.correct} / {f.total} 問　本番 {f.weight} 問／60問</div>
              </div>
            ))}
          </section>

          <section className="fe-section">
            <div className="fe-note small">
              <strong>「重点出題の比率」の読み方：</strong>
              「おまかせ（苦手を重点出題）」モードで，次の1問がその分野から出る確率です。
              本番の出題比率（＝本番想定の問数）を土台に，苦手なほど最大で約 2.3 倍まで重みを上げ，
              得意な分野は 0.3 倍まで下げています。本番で8問出るセキュリティを軽視しないための設計です。
            </div>
          </section>

          <section className="fe-section">
            <h2 className="fe-section-title">直近14日の解答数</h2>
            <div className="fe-card fe-daily">
              {data.daily.map((day) => (
                <div key={day.date} className="fe-daily-col"
                     title={`${Number(day.date.slice(5, 7))}月${Number(day.date.slice(8))}日 ${day.total}問（正解 ${day.correct}）`}>
                  <div className="fe-daily-bar" style={{ height: `${(day.total / maxDaily) * 100}%`, minHeight: day.total ? 4 : 0 }} />
                  <div className="fe-daily-day">{Number(day.date.slice(8))}</div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  )
}
