// 学習モードの「読む」段階。同じ小分類の技術解説をまとめて出し、読む時間を数える。
//
// ・残り時間はサーバーが開始時刻から数える（再読み込みしても増えない）。0 になったら解答へ自動で進む
// ・読み上げ（科目Aの解説だけ。音声があるときだけ再生バーを出す）を再生している間は時間を止める。
//   止めたこともサーバーに残し（api/learn/<id>/timer/）、残り時間はサーバーの値に合わせ直す
// ・一度に鳴らす読み上げは1本だけ。画面を見ていない間（別のタブ・画面を消す）は止め、
//   戻っても自動では再開しない
// ・終わったラウンドの解説は、結果画面から読み返せる（時間は数えない）
// ・解く段階に進んだラウンドを開いたら、解く画面へ移る
// ・学習コーナー（plan&check の「解説」から開いたとき。corner.tsx）は読む時間を数えない。
//   残り時間を出さず、0 になって自動で進むこともない。進むボタンはどちらも「問題へ進む」

import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, Navigate, useNavigate, useParams } from 'react-router'

import { api, type LearnRead } from './api'
import { CornerBackIfAny, getCorner } from './corner'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

export function LearnReadPage() {
  usePageView('learn_read')
  const id = Number(useParams().id)
  const { data, error, reload } = useLoad(() => api.learnRead(id), [id])
  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={4} />
  if (data.round.phase === 'quiz') return <Navigate to={`/learn/${id}/quiz/`} replace />
  return <Reading key={id} data={data} />
}

const clock = (seconds: number) => {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

function Reading({ data }: { data: LearnRead }) {
  const { round, notes } = data
  const finished = round.phase === 'done'
  const navigate = useNavigate()
  const toast = useToast()
  const [remaining, setRemaining] = useState(data.remaining)
  const [paused, setPaused] = useState(false)
  const [moving, setMoving] = useState(false)
  const players = useRef<HTMLAudioElement[]>([])
  const moved = useRef(false)
  // 学習コーナーでは読む時間を数えない
  const [untimed] = useState(() => getCorner() !== null)

  const goQuiz = useCallback(async () => {
    if (moved.current) return
    moved.current = true
    setMoving(true)
    try {
      await api.finishReading(round.id)
      navigate(`/learn/${round.id}/quiz/`)
    } catch (e) {
      moved.current = false
      setMoving(false)
      toast.show((e as Error).message, { kind: 'danger' })
    }
  }, [navigate, round.id, toast])

  const abandon = async () => {
    try {
      const result = await api.abandonRound(round.id)
      if (result.message) toast.show(result.message, { kind: 'info' })
      // 学習コーナーでは入口を通さないので、何も解かずにやめたら plan&check へ戻る
      navigate(result.abandoned ? (getCorner() ? '/planandcheck/' : '/learn/') : `/learn/${round.id}/result/`)
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
    }
  }

  // 1秒ごとに減らす。止めている間（読み上げ中）は減らさない
  useEffect(() => {
    if (finished || paused || untimed) return
    if (remaining <= 0) {
      void goQuiz()
      return
    }
    const timer = window.setTimeout(() => setRemaining((r) => r - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [finished, paused, untimed, remaining, goQuiz])

  const playing = () => players.current.some((p) => p && !p.paused)

  const onPlay = (player: HTMLAudioElement) => {
    // 一度に鳴らすのは1本だけ
    for (const other of players.current) if (other && other !== player) other.pause()
    if (finished || untimed) return
    setPaused(true)
    api.learnTimer(round.id, 'pause').then((r) => setRemaining(r.remaining)).catch(() => {})
  }

  const onStop = () => {
    // 別の解説の読み上げに切り替えただけなら、止めたままにする
    if (finished || untimed || playing()) return
    api.learnTimer(round.id, 'resume')
      .then((r) => {
        if (playing()) return
        setRemaining(r.remaining)
        setPaused(false)
      })
      .catch(() => setPaused(false))
  }

  // 画面を見ていない間は読み上げを止める（戻っても自動では再開しない）
  useEffect(() => {
    const stopAll = () => players.current.forEach((p) => p?.pause())
    const onVisibility = () => {
      if (document.visibilityState === 'hidden') stopAll()
    }
    document.addEventListener('visibilitychange', onVisibility)
    window.addEventListener('pagehide', stopAll)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      window.removeEventListener('pagehide', stopAll)
      stopAll()
    }
  }, [])

  return (
    <div className="fe-narrow-wide">
      <CornerBackIfAny />
      {finished ? (
        <div className="fe-card fe-timer-bar">
          <div className="fe-muted small">このラウンドは終了しています</div>
          <Link to={`/learn/${round.id}/result/`} className="btn btn-outline-primary btn-sm">結果に戻る</Link>
        </div>
      ) : (
        <div className="fe-card fe-timer-bar fe-sticky">
          <div className="fe-muted small">読み終わったら、この範囲から{round.total}問出題します</div>
          <div className="fe-timer-actions">
            {!untimed && paused && <span className="fe-muted small">読み上げ中は止めています</span>}
            {!untimed && <span className="fe-timer" aria-live="off">{clock(Math.max(0, remaining))}</span>}
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => void abandon()}>やめる</button>
            <button type="button" className="btn btn-primary btn-sm" disabled={moving} onClick={() => void goQuiz()}>問題へ進む</button>
          </div>
        </div>
      )}

      {notes.map((note, i) => (
        <article key={note.id} className={`fe-note-article${i > 0 ? ' fe-note-next' : ''}`}>
          <div className="mb-2">
            <span className="fe-badge">{note.category_code}. {note.category_name}</span>
            {note.topic && <span className="fe-muted small ms-2">{note.topic}</span>}
            {notes.length > 1 && <span className="fe-muted small ms-2">{i + 1} / {notes.length}</span>}
          </div>
          <h2 className="fe-note-title">{note.title}</h2>
          {note.audio_url && (
            <audio ref={(el) => { if (el) players.current[i] = el }}
                   className="fe-note-audio" controls preload="none" src={note.audio_url}
                   onPlay={(e) => onPlay(e.currentTarget)} onPause={onStop} onEnded={onStop} />
          )}
          <div className="fe-note-body">{note.body}</div>
          {note.source && (
            <div className="fe-muted small fe-note-source">
              出題範囲：{note.source}<br />本文は、この範囲の用語をもとに書き起こしたものです。
            </div>
          )}
        </article>
      ))}
    </div>
  )
}
