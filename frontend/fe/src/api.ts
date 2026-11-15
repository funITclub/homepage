// Django の API（apps/fe/api.py）とのやりとり。作りは bk_houmu3 の api.ts と同じ。
//
// 型は api.py が返す JSON の形に合わせてある。どちらかを変えたら、もう一方も合わせる。

// ---------------------------------------------------------------- 返ってくる形

export type Me = {
  entered: boolean
  code: string | null
  is_temporary: boolean
}

export type Dashboard = {
  question_total: number
  summary: {
    total: number
    correct: number
    rate_percent: number | null
    learners: number
    passers: number
  }
  my_report: { passed_on: string } | null
  today: string
  /** 自分の成績。ID があるときだけ（ID なしは null） */
  personal: Personal | null
}

export type CategoryInfo = {
  code: number
  label: string
  name: string
  field: string
  subject: string
  exam_weight: number
}

export type Personal = {
  overall: {
    rate_percent: number | null
    correct: number
    total: number
    recent_days: number
    recent_rate_percent: number | null
    pass_line_percent: number
    study_days: number
  }
  template_total: number
  weak: (CategoryInfo & { rate_percent: number | null; correct: number; total: number })[]
  untouched: CategoryInfo[]
  fields: FieldRow[]
  daily: { date: string; total: number; correct: number }[]
}

export type Guide = {
  exam_name: string
  question_total: number
  template_total: number
  me: Me
}

/** 分野の件数と選べるかどうか。モードごと（[件数, 選べるか]） */
export type CategoryOption = {
  code: number
  label: string
  subject: string
  question_count: number
  by_mode: Record<string, [number, boolean]>
}

export type Settings = {
  mode: string
  mode_label: string
  subject: string
  category: number | null
  modes: { value: string; label: string }[]
  subjects: { value: string; label: string }[]
  categories: CategoryOption[]
}

export type Choice = { label: string; text: string; figure: string | null }

export type Question = {
  id: number
  subject: string
  subject_label: string
  field: string
  category_code: number
  category_name: string
  category_label: string
  topic: string
  stem: string
  figures: { src: string; alt: string }[]
  choices: Choice[]
  origin_label: string
  source: string
}

/** 解答のあとに分かること（正解と解説） */
export type AnswerInfo = {
  answer_index: number
  answer_label: string
  answer_text: string
  answer_figure: string | null
  explanation: string
}

export type Progress = {
  name: string
  total: number
  correct: number
  rate_percent: number | null
}

export type QuizNext =
  | { question: null }
  | { question: Question; reason: string; progress: Progress }

export type QuizResult = AnswerInfo & {
  is_correct: boolean
  selected: number
  selected_label: string
  elapsed_ms: number | null
  progress: Progress
}

export type FieldRow = {
  label: string
  rate_percent: number | null
  correct: number
  total: number
  weight: number
}

export type StatsRow = {
  code: number
  label: string
  name: string
  field: string
  subject: string
  exam_weight: number
  total: number
  correct: number
  rate_percent: number | null
  question_count: number
  is_weak: boolean
  is_untouched: boolean
  /** おまかせで次の1問がこの分野から出る確率（％） */
  focus_share: number
}

export type Stats = {
  subject: string | null
  subjects: { value: string; label: string }[]
  rows: StatsRow[]
  fields: FieldRow[]
  daily: { date: string; total: number; correct: number }[]
}

export type HistoryItem = {
  id: number
  is_correct: boolean
  category: string
  topic: string
  answered_at: string
  stem: string
  answer_label: string
  selected_label: string
}

export type History = {
  results: HistoryItem[]
  count: number
  page: number
  num_pages: number
  categories: { code: number; label: string }[]
}

export type Mail = {
  registered: boolean
  masked_email: string
  pending: boolean
  /** ID で入っているか。ID ありならメールで答えた分をその ID に記録、ID なしならみんなの集計にだけ数える */
  with_id: boolean
}

export type LearnEntry = {
  note: number
  topic: string
  titles: string[]
  questions: number
  rounds: number
}

export type LearnGroup = {
  code: number
  name: string
  note_count: number
  rate_percent: number | null
  is_weak: boolean
  question_count: number
  /** 最初から開いておく（指定した分野と、直前に学習した中分類） */
  opened: boolean
  entries: LearnEntry[]
}

export type LearnStart = {
  minute_choices: number[]
  default_minutes: number
  count: number
  groups: LearnGroup[]
  recent: {
    id: number
    title: string
    has_note: boolean
    correct: number
    total: number
    started_at: string
  }[]
}

export type Round = {
  id: number
  phase: 'reading' | 'quiz' | 'done'
  title: string
  has_note: boolean
  total: number
  correct: number
  position: number
  rate_percent: number | null
}

export type Note = {
  id: number
  category_code: number
  category_name: string
  topic: string
  title: string
  body: string
  source: string
  audio_url: string | null
}

export type LearnRead = { round: Round; notes: Note[]; remaining: number }

export type LearnItem =
  | { round: Round; question: null }
  | ({ round: Round; question: Question; answered: false })
  | ({ round: Round; question: Question; answered: true; is_correct: boolean; selected: number; selected_label: string } & AnswerInfo)

export type LearnResult = {
  round: Round
  items: ({ is_correct: boolean | null; selected_label: string; question: Question } & AnswerInfo)[]
}

export type Message = { message: string }

// ---------------------------------------------------------------- やりとり

/** API がエラーを返したとき投げる */
export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 入れ物のページ（fe/app.html）が data-* で渡す値。main.tsx が最初に入れる
const config = { apiUrl: '', basePath: '/fe/' }

export function configureApi(apiUrl: string, basePath: string) {
  config.apiUrl = apiUrl
  config.basePath = basePath
}

/** Django が配る csrftoken の Cookie を読む（入れ物のページが ensure_csrf_cookie で配る） */
function csrfToken(): string {
  const hit = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))
  return hit ? decodeURIComponent(hit.split('=')[1]) : ''
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  headers.set('Accept', 'application/json')
  if (init.body) headers.set('Content-Type', 'application/json')
  // 書き込みには CSRF トークンが要る（api.CsrfOnly が確かめる）
  if (method !== 'GET') headers.set('X-CSRFToken', csrfToken())

  const res = await fetch(config.apiUrl + path, { ...init, headers, credentials: 'same-origin' })

  // 記録が無い（ブラウザを閉じて抜けた・始めていない）。入口を開き直すと、入口が記録を作る
  if (res.status === 401) {
    location.assign(config.basePath)
    throw new ApiError(401, '入口から開き直します。')
  }

  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    throw new ApiError(res.status, detail || `うまくいきませんでした（${res.status}）。`)
  }
  return data as T
}

const post = <T,>(path: string, body: unknown = {}) =>
  request<T>(path, { method: 'POST', body: JSON.stringify(body) })

export const api = {
  me: () => request<Me>('me/'),
  enter: (code: string, action: 'enter' | 'create') =>
    post<Me & Message>('enter/', { code, action }),
  pageview: (page: string) => post<void>('pageview/', { page }),
  dashboard: () => request<Dashboard>('dashboard/'),
  guide: () => request<Guide>('guide/'),
  settings: () => request<Settings>('settings/'),
  saveSettings: (mode: string, subject: string, category: number | null) =>
    post<Settings>('settings/', { mode, subject, category }),
  quizNext: () => request<QuizNext>('quiz/next/'),
  quizAnswer: (questionId: number, choice: number) =>
    post<QuizResult>('quiz/answer/', { question_id: questionId, choice }),
  stats: (subject: string) => request<Stats>(`stats/${subject ? `?subject=${subject}` : ''}`),
  history: (query: string) => request<History>(`history/${query ? `?${query}` : ''}`),
  reportPass: (passedOn: string) => post<Message>('pass/', { passed_on: passedOn }),
  withdrawPass: () => request<Message>('pass/', { method: 'DELETE' }),
  mail: () => request<Mail>('mail/'),
  registerMail: (email: string) => post<Mail & Message>('mail/', { email }),
  learn: () => request<LearnStart>('learn/'),
  startRound: (minutes: number, note: number | null) =>
    post<{ round: Round }>('learn/', { minutes, note }),
  learnRead: (id: number) => request<LearnRead>(`learn/${id}/read/`),
  finishReading: (id: number) => post<{ round: Round }>(`learn/${id}/read/`),
  learnTimer: (id: number, state: 'pause' | 'resume') =>
    post<{ remaining: number }>(`learn/${id}/timer/`, { state }),
  learnQuiz: (id: number) => request<LearnItem>(`learn/${id}/quiz/`),
  learnAnswer: (id: number, choice: number) => post<LearnItem>(`learn/${id}/quiz/`, { choice }),
  learnNext: (id: number) => post<{ round: Round }>(`learn/${id}/next/`),
  abandonRound: (id: number) =>
    post<{ abandoned: boolean; message?: string; round?: Round }>(`learn/${id}/abandon/`),
  learnResult: (id: number) => request<LearnResult>(`learn/${id}/result/`),
}
