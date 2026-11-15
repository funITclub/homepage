// 読み込み中と、読めなかったときの表示。

import { Icon } from './Icon'

/** 読み込み中。空白のまま待たせず、形だけ先に出す（countdown のスケルトンと同じ考え） */
export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="fe-card fe-skeleton">
          <div className="fe-bone" style={{ width: '40%', height: '1.2rem' }} />
          <div className="fe-bone" style={{ width: '75%' }} />
          <div className="fe-bone" style={{ width: '55%' }} />
        </div>
      ))}
    </div>
  )
}

export function LoadError({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="fe-card fe-error" role="alert">
      <Icon name="exclamation-circle" className="me-2" />
      {message}
      <button type="button" className="btn btn-sm btn-outline-primary ms-3" onClick={onRetry}>再読み込み</button>
    </div>
  )
}
