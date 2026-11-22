// ダッシュボードを開いたときに出す、ID の入力のポップアップ（ID なしのときだけ）。
// 以前ダッシュボードに置いていた「学習の記録を残しませんか」のカードの代わり。
//
// ・中身は ID の入力欄・「入室」・「ID なしで入室」・「次回から表示しない」だけ
//   （説明文は画面に出さない。ID の扱いは /id/ と「このアプリについて」にある）
// ・「新規作成」のボタンは置かない。「入室」で、まだ無い ID だったら（api.EnterAPI の not_found）
//   「新規作成しますか？」の確認に切りかえ、「新規作成」で作る・「戻る」で入力に戻る。
//   打ち間違えた ID でいきなり作ってしまわないよう、作る前に必ずこの確認を通す（ユーザーの指示）
// ・出すのはページを読み込んでから最初にダッシュボードを開いたときだけ（shownThisLoad）。
//   ほかの画面からダッシュボードへ戻るたびに出すとうるさいので、再読み込みまでは出さない
// ・「次回から表示しない」に印を付けて ID で入る（作る）と、ブラウザを閉じても ID を保持する
//   （サーバーが ID の Cookie に期限を付ける。views.LEARNER_KEEP_DAYS）。ID で入っていればポップアップは
//   出ないので、次回から出なくなる
// ・印が効くのは ID で入ったときだけ。ID なしのまま出さなくすると、ずっと ID なしになってしまうため
//   （ユーザーの指示）。ID の入力欄が空の間は、チェックボックスを押せなくしておく
// ・Enter は「入室」と同じ（フォームの最初の送信ボタン）。「ID なしで入室」・背景・Esc は同じ「閉じる」扱いで、
//   次の読み込みでまた出る。作成の確認の間は、Esc・背景は「戻る」と同じ
// ・ID で入る・作るの処理は EnterPage と同じ（api.enter）

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { useMe } from './App'
import { ApiError, api } from './api'
import { useToast } from './toast'

/** ページを読み込んでから、もう出したか */
let shownThisLoad = false

/** onEntered：ID で入った・作ったあと（ダッシュボードはその ID の成績で読み直す） */
export function IdPopup({ onEntered }: { onEntered: () => void }) {
  const { me, setMe } = useMe()
  const toast = useToast()
  // 最初の描画で決めて、そのあとは変えない（ID で入ったら me が変わるが、そのときは自分で閉じる）
  const [open, setOpen] = useState(() => !me.code && !shownThisLoad)
  const [code, setCode] = useState('')
  const [dontShow, setDontShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  // まだ無い ID で「入室」を押したら、その ID を作るかの確認を出す
  const [confirming, setConfirming] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const createButton = useRef<HTMLButtonElement>(null)
  const titleId = useId()

  useEffect(() => {
    if (open) shownThisLoad = true
  }, [open])

  const back = () => {
    setConfirming(false)
    setError(null)
  }
  const close = () => (confirming ? back() : setOpen(false))

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  })

  // 開いたとき・確認から戻ったときは入力欄に、確認に切りかえたときは「新規作成」に合わせる
  useEffect(() => {
    if (!open) return
    if (confirming) createButton.current?.focus({ preventScroll: true })
    else input.current?.focus({ preventScroll: true })
  }, [open, confirming])

  if (!open) return null

  const empty = code.trim() === ''
  const keep = dontShow && !empty

  const send = async (action: 'enter' | 'create') => {
    setSending(true)
    setError(null)
    try {
      const { message, ...next } = await api.enter(code, action, keep)
      setOpen(false)
      setMe(next)
      toast.show(message)
      onEntered()
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) {
        if (action === 'enter' && e.notFound) setConfirming(true)
        else {
          // 作れなかった（使えない ID など）ときは、入力に戻して誤りを出す
          setConfirming(false)
          setError(e.message)
        }
      } else toast.show((e as Error).message, { kind: 'danger' })
    } finally {
      setSending(false)
    }
  }

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void send(confirming ? 'create' : 'enter')
  }

  return (
    <div className="fe-popup">
      <div className="fe-popup-backdrop" onClick={close} />
      <form className="fe-popup-panel" role="dialog" aria-modal="true" aria-labelledby={titleId}
            onSubmit={submit} noValidate>
        <h2 id={titleId} className="fe-popup-title">ID</h2>
        {confirming ? (
          <>
            <p className="fe-popup-confirm">「<strong>{code.trim().toLowerCase()}</strong>」を新規作成しますか？</p>
            <div className="fe-popup-actions">
              <button ref={createButton} type="submit" className="btn btn-primary" disabled={sending}>新規作成</button>
              <button type="button" className="btn btn-outline-secondary" disabled={sending} onClick={back}>戻る</button>
            </div>
          </>
        ) : (
          <>
            <input ref={input} className={`form-control${error ? ' is-invalid' : ''}`} maxLength={30}
                   aria-labelledby={titleId} autoComplete="username" autoCapitalize="none" spellCheck={false}
                   value={code} onChange={(e) => setCode(e.target.value)} />
            {error && <div className="fe-field-error">{error}</div>}
            <div className="fe-popup-actions">
              <button type="submit" className="btn btn-primary" disabled={sending}>入室</button>
              <button type="button" className="btn btn-outline-secondary" disabled={sending}
                      onClick={() => setOpen(false)}>ID なしで入室</button>
            </div>
          </>
        )}
        <label className={`fe-popup-check${empty ? ' fe-popup-check-off' : ''}`}>
          <input type="checkbox" className="form-check-input" checked={keep} disabled={empty}
                 onChange={(e) => setDontShow(e.target.checked)} />
          次回から表示しない
        </label>
      </form>
    </div>
  )
}
