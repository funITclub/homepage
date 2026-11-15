// ダッシュボードの「問題メール」の欄。ID のあり・なしにかかわらず出す。
//
// 9〜18時の毎時に、IPA 公開問題が3問ずつ届く。選ぶものは無く、受け取るか止めるかだけ。
// ID で入って登録すれば、メールで答えた分をその ID の学習履歴に足す。ID なしで登録すれば、
// みんなの集計にだけ数える（どちらになるかは、登録したときに ID で入っていたかで決まる）。
// 未登録なら、アドレスを入れて確認のメールを送る（登録はメールのリンクの「受け取る」から）。
// 登録済みならアドレスは変えられない。アドレスの変更と解除は、届いた問題メールの末尾の
// リンクからだけできる（ID のあり・なしとも。画面からは解除しない）。

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'

import { api, type Mail } from './api'
import { LoadError, Loading } from './Status'
import { useToast } from './toast'
import { useLoad } from './useLoad'

export function MailSection() {
  const { data, setData, error, reload } = useLoad(api.mail)

  return (
    <section className="fe-section" id="mail">
      <h2 className="fe-section-title">問題メール</h2>
      {error && <LoadError message={error} onRetry={() => void reload()} />}
      {!error && !data && <Loading rows={1} />}
      {data && <MailForm mail={data} onSaved={setData} />}
    </section>
  )
}

function MailForm({ mail, onSaved }: { mail: Mail; onSaved: (mail: Mail) => void }) {
  const toast = useToast()
  const [email, setEmail] = useState('')
  const [sending, setSending] = useState(false)

  const run = async (action: () => Promise<{ message: string } & Partial<Mail>>) => {
    setSending(true)
    try {
      const { message, ...next } = await action()
      toast.show(message)
      if ('registered' in next) onSaved(next as Mail)
    } catch (e) {
      toast.show((e as Error).message, { kind: 'danger' })
    } finally {
      setSending(false)
    }
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    void run(() => api.registerMail(email))
  }

  return (
    <div className="fe-card">
      <p className="fe-muted small">
        毎日9時から18時まで毎時、IPA の公開問題を3問ずつ送ります。
        メールの「この問題に答える」から答えると、正解と解説が出ます。
      </p>
      {mail.with_id ? (
        <p className="fe-muted small">
          ID で入って登録しているので、問題はあなたの苦手な分野を重く選び、答えた分はこの ID の成績に記録されます。
        </p>
      ) : (
        <p className="fe-muted small">
          ID なしで登録すると、答えた分はみんなの集計にだけ数え、個人の成績には残りません。
          成績に残したいときは、<Link to="/id/">ID で入って</Link>から登録してください。
        </p>
      )}

      {mail.registered ? (
        <>
          <div className="fe-note small">
            配信先 <strong>{mail.masked_email}</strong>
            <div className="fe-muted mt-1">アドレスの変更と解除は、届いた問題メールの末尾のリンクからできます。</div>
          </div>
        </>
      ) : (
        <>
          {mail.pending && (
            <div className="fe-note fe-note-info small">
              確認のメールを送ってあります。メールのリンクを開いて「受け取る」を押すと登録されます。
              届かないときは、時間をおいてもう一度登録してください。
            </div>
          )}
          <form onSubmit={submit}>
            <div className="mb-3 fe-mail-email">
              <label className="form-label" htmlFor="fe-mail-email">メールアドレス</label>
              <input type="email" className="form-control form-control-sm" id="fe-mail-email" required
                     autoComplete="email" placeholder="you@example.com"
                     value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <button type="submit" className="btn btn-primary btn-sm" disabled={sending || !email}>
              確認のメールを送る
            </button>
          </form>
        </>
      )}
    </div>
  )
}
