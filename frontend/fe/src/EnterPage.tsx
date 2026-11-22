// ID で入る・作る・切り替える（/id/ で、入っていないときと ?switch のとき）。ヘッダーの「ID で入る」「ID を切り替える」から開く。
//
// ダッシュボードのポップアップ（IdPopup.tsx）と同じ形にそろえる（ユーザーの指示）。
// ・中身は ID の入力欄と「入室」だけ。説明文は画面に出さない（ID の扱いは「このアプリについて」にある）
// ・「新規作成」のボタンは置かない。「入室」で、まだ無い ID だったら（api.EnterAPI の not_found）
//   「新規作成しますか？」の確認に切りかえ、「新規作成」で作る・「戻る」で入力に戻る。
//   打ち間違えた ID でいきなり作ってしまわないよう、作る前に必ずこの確認を通す
// ・ポップアップの「ID なしで入室」「次回から表示しない」は、ポップアップを閉じる・出さなくするためのものなので置かない
// ・ID で入っているときは「ID から抜ける」も出す。抜けると ID の無い記録で使い続け、ID の成績はその ID に残る。
//   いまの ID はヘッダーに出ているので、ここには書かない
// ・見た目はポップアップのパネルと同じ（fe-popup-* のクラスを使う）

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'

import { useMe } from './App'
import { clearCorner } from './corner'
import { ApiError, api } from './api'
import { useToast } from './toast'
import { usePageView } from './usePageView'

export function EnterPage() {
  usePageView('id_entry')
  const { me, setMe } = useMe()
  const toast = useToast()
  const navigate = useNavigate()
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  // まだ無い ID で「入室」を押したら、その ID を作るかの確認を出す
  const [confirming, setConfirming] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const createButton = useRef<HTMLButtonElement>(null)
  const titleId = useId()

  // 開いたとき・確認から戻ったときは入力欄に、確認に切りかえたときは「新規作成」に合わせる
  useEffect(() => {
    if (confirming) createButton.current?.focus({ preventScroll: true })
    else input.current?.focus({ preventScroll: true })
  }, [confirming])

  const back = () => {
    setConfirming(false)
    setError(null)
  }

  // 確認の間は Esc で入力に戻る（ポップアップと同じ）
  useEffect(() => {
    if (!confirming) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') back()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [confirming])

  const send = async (action: 'enter' | 'create') => {
    setSending(true)
    setError(null)
    try {
      const { message, ...next } = await api.enter(code, action)
      setMe(next)
      toast.show(message)
      navigate('/')
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

  const leave = async () => {
    setSending(true)
    try {
      const { message, ...next } = await api.leave()
      clearCorner()
      setMe(next)
      toast.show(message)
      navigate('/')
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
      setSending(false)
    }
  }

  return (
    <div className="fe-narrow">
      <form className="fe-popup-panel fe-enter-panel" aria-labelledby={titleId} onSubmit={submit} noValidate>
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
              {me.code && (
                <button type="button" className="btn btn-outline-secondary" disabled={sending}
                        onClick={() => void leave()}>ID から抜ける</button>
              )}
            </div>
          </>
        )}
      </form>
    </div>
  )
}
