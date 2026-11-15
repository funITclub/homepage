// 1問1答。問題、いちばん下に出題設定。上の「出題設定」のリンクで、いちばん下の出題設定へ移る。
//
// 解答の前：問題の属性 → 問題文（図） → 選択肢 → 出典 → 「解答する」
// 解答の後：問題の属性 → 問題文 → 正誤 → 選択肢（正解と自分の解答に色） → 出典 → 解説 → 「次の問題へ」
// 正解と解説は解答してから API が返す（先に渡すと、画面の中を覗けば答えが分かるため）。
// いま出している問題でない解答（二重送信など）は API が 409 で断るので、次の問題を出し直す。

import { useCallback, useEffect, useState, type FormEvent } from 'react'

import { ApiError, api, type QuizNext, type QuizResult, type Settings } from './api'
import { Icon } from './Icon'
import { Choices, Explanation, Source, Stem } from './QuestionParts'
import { SettingsForm } from './SettingsForm'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { usePageView } from './usePageView'

export function QuizPage() {
  usePageView('quiz')
  const toast = useToast()
  const [settings, setSettings] = useState<Settings | null>(null)
  const [next, setNext] = useState<QuizNext | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [choice, setChoice] = useState<number | null>(null)
  const [result, setResult] = useState<QuizResult | null>(null)
  const [sending, setSending] = useState(false)

  const loadNext = useCallback(async () => {
    setError(null)
    setNext(null)
    setResult(null)
    setChoice(null)
    try {
      setNext(await api.quizNext())
      window.scrollTo({ top: 0 })
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(() => {
    api.settings().then(setSettings).catch((e: Error) => setError(e.message))
    void loadNext()
  }, [loadNext])

  const saved = (value: Settings) => {
    setSettings(value)
    void loadNext()
  }

  const answer = async (event: FormEvent) => {
    event.preventDefault()
    if (!next?.question || choice === null) return
    setSending(true)
    try {
      setResult(await api.quizAnswer(next.question.id, choice))
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        toast.show(e.message, { kind: 'info' })
        void loadNext()
      } else {
        toast.show((e as Error).message, { kind: 'danger' })
      }
    } finally {
      setSending(false)
    }
  }

  const settingsCard = settings && (
    <section className="fe-card fe-quiz-settings" id="fe-quiz-settings">
      <div className="fe-card-title">出題設定</div>
      <SettingsForm key={`${settings.mode}-${settings.subject}-${settings.category}`}
                    settings={settings} submitLabel="この設定で出題" onSaved={saved} />
    </section>
  )

  // 上の「出題設定」のリンク。いちばん下の出題設定へ移る
  const settingsLink = (
    <div className="fe-quiz-top">
      <button type="button" className="btn btn-link btn-sm p-0"
              onClick={() => document.getElementById('fe-quiz-settings')?.scrollIntoView({ behavior: 'smooth' })}>
        <Icon name="sliders-h" className="me-1" />出題設定
      </button>
    </div>
  )

  if (error) return <><LoadError message={error} onRetry={() => void loadNext()} />{settingsCard}</>
  if (!next) return <Loading rows={2} />
  if (!next.question) {
    return (
      <>
        <div className="fe-card fe-warning">いまの設定で出題できる問題がありません。出題モードか科目を変えてください。</div>
        {settingsCard}
      </>
    )
  }

  const q = next.question
  const answered = result !== null
  const progress = answered ? result.progress : next.progress

  return (
    <>
      {settingsLink}
      <div className="fe-quiz-meta">
        <div>
          <span className="fe-badge fe-badge-strong">{q.subject_label}</span>
          <span className="fe-badge ms-1">{q.field}</span>
          <span className="fe-muted small ms-2">{q.category_label}{q.topic && ` ／ ${q.topic}`}</span>
        </div>
        {next.reason && <span className="fe-muted small"><Icon name="bullseye" className="me-1" />{next.reason}</span>}
      </div>

      <div className="fe-card"><Stem question={q} /></div>

      {answered && (
        <div className={`fe-card fe-verdict ${result.is_correct ? 'fe-verdict-good' : 'fe-verdict-bad'}`} role="status">
          <span className="fe-verdict-mark">{result.is_correct ? '○' : '×'}</span>
          <strong>{result.is_correct ? '正解' : '不正解'}</strong>
          <span className="ms-2">正解は <strong>{result.answer_label}</strong></span>
          {!result.is_correct && <span className="ms-2 small">（選んだのは {result.selected_label}）</span>}
        </div>
      )}

      <form onSubmit={answer}>
        {answered
          ? <Choices question={q} answer={result.answer_index} selected={result.selected} />
          : <Choices question={q} picked={choice} onPick={setChoice} />}
        <Source question={q} />
        {answered && <Explanation info={result} />}

        <div className="fe-quiz-foot">
          <div className="fe-muted small">
            {progress.name}：{answered ? '' : 'これまで '}{progress.correct}/{progress.total} 問正解
            {answered && progress.rate_percent !== null && `（${progress.rate_percent}％）`}
          </div>
          {answered ? (
            <button type="button" className="btn btn-primary" onClick={() => void loadNext()}>
              次の問題へ<Icon name="arrow-right" className="ms-2" />
            </button>
          ) : (
            <button type="submit" className="btn btn-primary" disabled={choice === null || sending}>解答する</button>
          )}
        </div>
      </form>

      <hr className="fe-rule fe-rule-wide" />
      {settingsCard}
    </>
  )
}
