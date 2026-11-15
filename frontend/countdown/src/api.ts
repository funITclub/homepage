// Django の API（works/countdown/api.py）とのやりとり。
//
// 型は api.py の event_json が返す JSON の形に合わせてある。どちらかを変えたら、もう一方も合わせる。
// 日数は画面が derive.ts で計算する（サーバーの today を使う）。
// 返事を待たずに表示する場面（楽観的更新・入力中の見通し）があるため。
//
// ログインはない。置き場（ID の一覧か共有ボードか）は API の URL で決まる。

/** 予定・出来事 1件（API が返す形） */
export type CountEvent = {
  id: number
  name: string
  /** 2026-11-07 の形 */
  date: string
  memo: string
  notify: boolean
  /** 登録日時（日本時間。"2026-10-01T12:00:00.123+09:00"） */
  created_at: string
}

/** 一覧（GET /countdown/api/events/） */
export type EventList = {
  today: string
  upcoming: CountEvent[]
  past: CountEvent[]
}

/** 登録・編集で送る欄 */
export type EventInput = Pick<CountEvent, 'name' | 'date' | 'memo' | 'notify'>

/** 入力のまちがい。欄の名前 → メッセージの並び（Django の Form の errors の形） */
export type FieldErrors = Partial<Record<keyof EventInput | 'non_field_errors', string[]>>

/** API がエラーを返したとき投げる。入力のまちがい（400）なら fieldErrors に入る */
export class ApiError extends Error {
  status: number
  fieldErrors: FieldErrors

  constructor(status: number, message: string, fieldErrors: FieldErrors = {}) {
    super(message)
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

/** 入れ物のページ（countdown/app.html）が data-* で渡す値。main.tsx が最初に入れる */
export type Site = {
  apiUrl: string
  /** ID で入る・作る画面 */
  enterUrl: string
  /** ID の一覧なら ID。共有ボードなら null（共有ボードではメール通知を使わない） */
  board: string | null
  /** メール通知の設定画面（ID の一覧のときだけ） */
  mailUrl: string
  /** 通知先のアドレスを伏せたもの（a***@example.com）。未登録なら空 */
  notifyTo: string
}

export const site: Site = { apiUrl: '', enterUrl: '', board: null, mailUrl: '', notifyTo: '' }

export function configure(values: Site) {
  Object.assign(site, values)
}

const config = site

/** Django が配る csrftoken の Cookie を読む（入れ物のページが ensure_csrf_cookie で配る） */
function csrfToken(): string {
  const hit = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))
  return hit ? decodeURIComponent(hit.split('=')[1]) : ''
}

const notFound = '見つかりません。削除されたか、この一覧のものではありません。'

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  // 書き込みには CSRF トークンが要る（Django の CsrfViewMiddleware が確かめる）
  if (method !== 'GET') headers.set('X-CSRFToken', csrfToken())

  const res = await fetch(url, { ...init, headers, credentials: 'same-origin' })

  // 一覧からの導線（config/gate.py）の印が切れると、API も成果物一覧へ転送される。
  // そのときは JSON ではなくページが返るので、開き直してもらう
  if (res.redirected || !(res.headers.get('Content-Type') ?? '').includes('json')) {
    if (res.status === 204) return undefined as T
    if (res.status === 404) throw new ApiError(404, notFound)
    throw new ApiError(res.status, '読み込めませんでした。ページを開き直してください。')
  }

  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    if (res.status === 400) {
      throw new ApiError(400, '入力を確かめてください。', data as FieldErrors)
    }
    if (res.status === 404) {
      throw new ApiError(404, notFound)
    }
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    throw new ApiError(res.status, detail || `うまくいきませんでした（${res.status}）。`)
  }
  return data as T
}

const eventUrl = (id: number) => `${config.apiUrl}${id}/`

export const api = {
  list: () => request<EventList>(config.apiUrl),
  create: (input: EventInput) =>
    request<CountEvent>(config.apiUrl, { method: 'POST', body: JSON.stringify(input) }),
  update: (id: number, input: Partial<EventInput>) =>
    request<CountEvent>(eventUrl(id), { method: 'PATCH', body: JSON.stringify(input) }),
  remove: (id: number) => request<void>(eventUrl(id), { method: 'DELETE' }),
  /**
   * ページを閉じる間ぎわの削除。keepalive を付けると、ページが無くなっても送りきってくれる。
   * 「元に戻す」を待っている削除を、タブを閉じたときに送るのに使う（useEvents.ts）。
   */
  removeOnLeave: (id: number) => {
    void fetch(eventUrl(id), {
      method: 'DELETE',
      headers: { 'X-CSRFToken': csrfToken() },
      credentials: 'same-origin',
      keepalive: true,
    })
  },
}
