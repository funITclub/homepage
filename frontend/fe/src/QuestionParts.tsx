// 問題の表示の部品。1問1答・学習モードの解く段階・学習モードの結果で共有する。
//
// ・問題文は改行と字下げを保つ（擬似言語のプログラム）。科目Bは等幅の字にする
// ・図は公開問題の冊子から切り出した PNG（data URI）。冊子は白地に黒なので、暗い画面でも
//   白地のまま見せる（反転すると図が読めない）
// ・選択肢そのものが図の問題は、選択肢の本文の下に図を出す

import type { AnswerInfo, Question } from './api'

export function Stem({ question, small = false }: { question: Question; small?: boolean }) {
  return (
    <>
      <div className={`fe-stem${question.subject === 'B' ? ' fe-stem-b' : ''}${small ? ' fe-stem-small' : ''}`}>
        {question.stem}
      </div>
      <Figures figures={question.figures} />
    </>
  )
}

export function Figures({ figures }: { figures: Question['figures'] }) {
  if (!figures.length) return null
  return (
    <>
      {figures.map((figure, i) => (
        <figure key={i} className="fe-figure">
          <img src={figure.src} alt={figure.alt} loading="lazy" />
        </figure>
      ))}
    </>
  )
}

/**
 * 選択肢。picked/onPick を渡すと選べる（解答の前）。answer を渡すと正解と自分の解答に色を付ける（解答の後）。
 */
export function Choices({
  question,
  picked = null,
  onPick,
  answer,
  selected = null,
}: {
  question: Question
  picked?: number | null
  onPick?: (index: number) => void
  answer?: number
  selected?: number | null
}) {
  const answered = answer !== undefined
  return (
    <div className="fe-choices">
      {question.choices.map((choice, index) => {
        const tone = !answered ? ''
          : index === answer ? ' fe-choice-good'
          : index === selected ? ' fe-choice-bad' : ''
        const body = (
          <>
            <span className="fe-choice-label">{choice.label}</span>
            <span className="fe-choice-text">
              {choice.text}
              {choice.figure && (
                <img className="fe-choice-figure" src={choice.figure} alt={`${choice.label}：${choice.text}`} loading="lazy" />
              )}
            </span>
            {answered && index === answer && <span className="fe-choice-note">正解</span>}
            {answered && index === selected && index !== answer && <span className="fe-choice-note">あなたの解答</span>}
          </>
        )
        if (answered || !onPick) {
          return <div key={index} className={`fe-choice${tone}`}>{body}</div>
        }
        return (
          <label key={index} className={`fe-choice fe-choice-pickable${picked === index ? ' fe-choice-picked' : ''}`}>
            <input type="radio" className="form-check-input" name="choice" checked={picked === index}
                   onChange={() => onPick(index)} />
            {body}
          </label>
        )
      })}
    </div>
  )
}

export function Source({ question }: { question: Question }) {
  if (!question.source) return null
  return (
    <p className="fe-source">
      {question.origin_label && <span className="fe-badge me-1">{question.origin_label}</span>}
      {question.source}
    </p>
  )
}

export function Explanation({ info, title = '解説' }: { info: AnswerInfo; title?: string }) {
  if (!info.explanation) return null
  return (
    <section className="fe-explanation">
      <h2 className="fe-explanation-title">{title}</h2>
      <p>{info.explanation}</p>
    </section>
  )
}
