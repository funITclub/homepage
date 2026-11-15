// 解答履歴。新しい順に20件ずつ。正誤と分野で絞り込む。
// 絞り込みとページはアドレス（?result=wrong&category=3&page=2）に持つ。
// 選ぶとすぐ絞り込む。

import { useSearchParams } from 'react-router'

import { api } from './api'
import { LoadError, Loading } from './Status'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

const when = (iso: string) => {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}/${pad(d.getMonth() + 1)}/${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function HistoryPage() {
  usePageView('history')
  const [params, setParams] = useSearchParams()
  const query = params.toString()
  const { data, error, reload } = useLoad(() => api.history(query), [query])

  const change = (key: string, value: string) => {
    const next = new URLSearchParams(params)
    if (value) next.set(key, value)
    else next.delete(key)
    // 絞り込みを変えたら1ページ目から
    if (key !== 'page') next.delete('page')
    setParams(next)
  }

  return (
    <>
      <section className="fe-section fe-filters">
        <div className="fe-settings-field">
          <label htmlFor="fe-result" className="form-label">正誤</label>
          <select id="fe-result" className="form-select form-select-sm" value={params.get('result') ?? ''}
                  onChange={(e) => change('result', e.target.value)}>
            <option value="">すべて</option>
            <option value="wrong">まちがえた問題</option>
            <option value="correct">正解した問題</option>
          </select>
        </div>
        <div className="fe-settings-field">
          <label htmlFor="fe-history-category" className="form-label">分野</label>
          <select id="fe-history-category" className="form-select form-select-sm" value={params.get('category') ?? ''}
                  onChange={(e) => change('category', e.target.value)}>
            <option value="">すべて</option>
            {data?.categories.map((c) => <option key={c.code} value={c.code}>{c.label}</option>)}
          </select>
        </div>
      </section>

      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!error && !data && <Loading />}
      {data && data.results.length === 0 && <p className="fe-muted">該当する解答履歴がありません。</p>}
      {data && data.results.length > 0 && (
        <>
          <div className="fe-list">
            {data.results.map((a) => (
              <div key={a.id} className="fe-card fe-history">
                <div className="fe-muted small mb-1">
                  <span className={`fe-mark ${a.is_correct ? 'fe-mark-good' : 'fe-mark-bad'}`}>{a.is_correct ? '○' : '×'}</span>
                  {a.category}{a.topic && ` ／ ${a.topic}`}
                  <span className="ms-2">{when(a.answered_at)}</span>
                </div>
                <div className="fe-history-stem">{a.stem}</div>
                {!a.is_correct && (
                  <div className="fe-muted small mt-1">正解：{a.answer_label} ／ あなたの解答：{a.selected_label}</div>
                )}
              </div>
            ))}
          </div>
          {data.num_pages > 1 && (
            <nav className="fe-pager">
              <button type="button" className="btn btn-sm btn-outline-primary" disabled={data.page <= 1}
                      onClick={() => change('page', String(data.page - 1))}>前へ</button>
              <span className="fe-muted small">{data.page} / {data.num_pages}</span>
              <button type="button" className="btn btn-sm btn-outline-primary" disabled={data.page >= data.num_pages}
                      onClick={() => change('page', String(data.page + 1))}>次へ</button>
            </nav>
          )}
        </>
      )}

      <div className="fe-note small mt-4">
        この履歴は、いま登録されている問題に対するものだけです。
        問題を入れ替えると、入れ替え前の問題に対する履歴は問題と一緒に消えます。
        <strong>分野ごとの正答率と苦手分野の判定は別に記録している</strong>ので、
        入れ替えても失われません。
      </div>
    </>
  )
}
