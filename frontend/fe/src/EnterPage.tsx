// ID を作る・入る・切り替える（/id/ で、入っていないときと ?switch のとき）。
// ID なしで使い始めるのが基本なので、ここは記録を残したくなった人のための画面。
// 打ち間違えた ID で新しく作ってしまわないよう、「新しく作る」と「作った ID で入る」を分ける。

import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'

import { useMe } from './App'
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

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const submitter = (event.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null
    const action = submitter?.value === 'create' ? 'create' : 'enter'
    setSending(true)
    setError(null)
    try {
      const { message, ...next } = await api.enter(code, action)
      setMe(next)
      toast.show(message)
      navigate('/')
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setError(e.message)
      else toast.show((e as Error).message, { kind: 'danger' })
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="fe-narrow">
      <h2 className="fe-page-title">ID で入る・ID を作る</h2>
      {me.code ? (
        <div className="fe-note small">
          いまは ID「<strong>{me.code}</strong>」で入っています。別の ID を入力すると切り替わります。
          <Link to="/" className="ms-1">ダッシュボードに戻る</Link>
        </div>
      ) : (
        <>
          <p>ID をお持ちの方は、ID を入力して「作った ID で入る」を押してください。続きから使えます。</p>
          <p>
            ID を作ると、解答の記録と分野ごとの理解度がその ID に残ります。
            別の端末でも同じ ID を入れれば続きから使え、合格の申告もできるようになります。ID で入って問題メールを登録すると、メールで答えた分もその ID に記録されます。
          </p>
          {me.entered && <p className="fe-muted small">ID を作る前の解答は引き継がれず、ゼロから始まります。</p>}
        </>
      )}

      <form className="fe-card" onSubmit={submit} noValidate>
        <label htmlFor="fe-code" className="form-label fe-label-strong">ID</label>
        <input id="fe-code" className={`form-control${error ? ' is-invalid' : ''}`} maxLength={30}
               autoComplete="username" autoCapitalize="none" spellCheck={false}
               value={code} onChange={(e) => setCode(e.target.value)} />
        {error && <div className="fe-field-error">{error}</div>}
        <div className="fe-muted small mt-1">半角の英小文字・数字・「_」「-」で、3〜30文字。</div>
        <div className="d-flex flex-wrap gap-2 mt-3">
          <button type="submit" name="action" value="create" className="btn btn-primary" disabled={sending}>新しく作る</button>
          <button type="submit" name="action" value="enter" className="btn btn-outline-primary" disabled={sending}>作った ID で入る</button>
        </div>
      </form>

      <p className="fe-muted small">
        ID には合言葉がありません。人と同じ ID は使わないでください。
        記録の扱いは<Link to="/guide/#id">このアプリについて</Link>にあります。
      </p>
    </div>
  )
}
