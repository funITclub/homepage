// 学習モードの結果。解いた問題を、正解したものも含めて全問読み返せるようにする。

import { Link, useParams } from 'react-router'

import { api } from './api'
import { Source, Stem } from './QuestionParts'
import { LoadError, Loading } from './Status'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

export function LearnResultPage() {
  usePageView('learn_result')
  const id = Number(useParams().id)
  const { data, error, reload } = useLoad(() => api.learnResult(id), [id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={4} />

  const { round, items } = data
  const missed = items.some((i) => i.is_correct === false)

  return (
    <div className="fe-narrow-wide">
      <div className="fe-card fe-result-head">
        <div>
          <div className="fe-muted small mb-1">読んだ解説</div>
          <div className="fw-bold">{round.has_note ? round.title : '（削除された解説）'}</div>
        </div>
        <div className="text-end">
          <div className="fe-result-score">{round.correct}<small> / {round.total}</small></div>
          {round.rate_percent !== null && <div className="fe-muted small">正答率 {round.rate_percent}％</div>}
        </div>
      </div>

      {!missed && <div className="fe-card fe-verdict fe-verdict-good">全問正解です。</div>}

      <h2 className="fe-section-title mt-4">解いた問題</h2>
      {items.map((item, i) => (
        <div key={i} className="fe-card">
          <div className="mb-2">
            <span className="fw-bold small me-2">問{i + 1}</span>
            {item.is_correct === true && <span className="fe-mark fe-mark-good">正解</span>}
            {item.is_correct === false && <span className="fe-mark fe-mark-bad">不正解</span>}
            {item.is_correct === null && <span className="fe-badge">未解答</span>}
            <span className="fe-badge ms-1">{item.question.category_name}</span>
            {item.question.topic && <span className="fe-muted small ms-2">{item.question.topic}</span>}
          </div>
          <Stem question={item.question} small />
          <div className="small my-2">
            {item.is_correct === false && <span className="fe-bad me-3">あなたの解答 {item.selected_label}</span>}
            <span className="fe-good">正解 {item.answer_label}　{item.answer_text}</span>
            {item.answer_figure && (
              <img className="fe-choice-figure" src={item.answer_figure}
                   alt={`正解 ${item.answer_label}：${item.answer_text}`} loading="lazy" />
            )}
          </div>
          {item.explanation && <div className="fe-stem fe-stem-small fe-muted">{item.explanation}</div>}
          <Source question={item.question} />
        </div>
      ))}

      <div className="d-flex gap-2 mt-4">
        <Link to="/learn/" className="btn btn-primary">もう1ラウンド</Link>
        {round.has_note && <Link to={`/learn/${round.id}/read/`} className="btn btn-outline-secondary">解説を読み返す</Link>}
      </div>
    </div>
  )
}
