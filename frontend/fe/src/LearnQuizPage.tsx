// 学習モードの「解く」段階。読んだ範囲をそのまま1問1答で出す。
//
// 解答したら正誤・選択肢（正解と自分の解答に色）・出典・解説を出し、「次の問題」で次へ進む。
// 最後の1問なら「結果を見る」。まだ読む段階のラウンドなら読む画面へ、終わったラウンドなら結果へ移る。
// いちばん下に「中断して学習モードトップへ」（ラウンドは破棄される。解いたぶんの記録は残る）。

import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useParams } from 'react-router'

import { api, type LearnItem } from './api'
import { CornerBackIfAny, getCorner } from './corner'
import { Choices, Source, Stem } from './QuestionParts'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

export function LearnQuizPage() {
  usePageView('learn_quiz')
  const id = Number(useParams().id)
  const { data, setData, error, reload } = useLoad(() => api.learnQuiz(id), [id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={3} />
  if (data.round.phase === 'reading') return <Navigate to={`/learn/${id}/read/`} replace />
  if (data.round.phase === 'done' || !data.question) return <Navigate to={`/learn/${id}/result/`} replace />
  return <Item key={`${id}-${data.round.position}`} item={data} onChange={setData} onReload={() => void reload()} />
}

function Item({ item, onChange, onReload }: {
  item: Exclude<LearnItem, { question: null }>
  onChange: (item: LearnItem) => void
  onReload: () => void
}) {
  const navigate = useNavigate()
  const toast = useToast()
  const { round, question } = item
  const [choice, setChoice] = useState<number | null>(null)
  const [sending, setSending] = useState(false)

  const run = async (action: () => Promise<void>) => {
    setSending(true)
    try {
      await action()
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
      setSending(false)
    }
  }

  const answer = (event: FormEvent) => {
    event.preventDefault()
    if (choice === null) return
    void run(async () => {
      onChange(await api.learnAnswer(round.id, choice))
      setSending(false)
    })
  }

  const next = () => void run(async () => {
    const { round: after } = await api.learnNext(round.id)
    if (after.phase === 'done') navigate(`/learn/${round.id}/result/`)
    else {
      window.scrollTo({ top: 0 })
      onReload()
    }
  })

  const abandon = () => void run(async () => {
    const result = await api.abandonRound(round.id)
    if (result.message) toast.show(result.message, { kind: 'info' })
    // 学習コーナーでは入口を通さないので、何も解かずにやめたら plan&check へ戻る
    navigate(result.abandoned ? (getCorner() ? '/planandcheck/' : '/learn/') : `/learn/${round.id}/result/`)
  })

  const last = round.position + 1 >= round.total

  return (
    <div className="fe-narrow-wide">
      <CornerBackIfAny />
      {round.title && <div className="fe-muted small mb-2">{round.title}</div>}
      <div className="fe-round-head">
        <span className="fe-accent fw-bold">{round.position + 1} / {round.total}問目</span>
        <span className="fe-muted small">正解 {round.correct}問</span>
      </div>
      <div className="fe-bar fe-round-bar"><span style={{ width: `${round.total ? (round.position / round.total) * 100 : 0}%` }} /></div>

      <div className="mb-3">
        <span className="fe-badge">{question.category_code}. {question.category_name}</span>
        {question.topic && <span className="fe-muted small ms-2">{question.topic}</span>}
      </div>

      <div className="fe-card"><Stem question={question} /></div>

      {item.answered ? (
        <>
          <div className={`fe-card fe-verdict ${item.is_correct ? 'fe-verdict-good' : 'fe-verdict-bad'}`} role="status">
            <strong>{item.is_correct ? '正解' : '不正解'}</strong>
            <span className="ms-2 small">あなたの解答 {item.selected_label}　／　正解 {item.answer_label}</span>
          </div>
          <Choices question={question} answer={item.answer_index} selected={item.selected} />
          <Source question={question} />
          {item.explanation && (
            <div className="fe-card fe-learn-explanation">
              <div className="fe-card-title fe-accent small">解説</div>
              <div className="fe-stem fe-stem-small">{item.explanation}</div>
            </div>
          )}
          <button type="button" className="btn btn-primary" disabled={sending} onClick={next}>
            {last ? '結果を見る' : '次の問題'}
          </button>
        </>
      ) : (
        <form onSubmit={answer}>
          <Choices question={question} picked={choice} onPick={setChoice} />
          <Source question={question} />
          <button type="submit" className="btn btn-primary" disabled={choice === null || sending}>解答する</button>
        </form>
      )}

      <div className="fe-abandon">
        <span className="fe-muted small">このラウンドは破棄されます</span>
        <button type="button" className="btn btn-outline-secondary btn-sm" disabled={sending} onClick={abandon}>
          中断して学習モードトップへ
        </button>
      </div>
    </div>
  )
}
