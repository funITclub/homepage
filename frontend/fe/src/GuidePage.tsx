// このアプリについて。ダッシュボードと入口から外した説明をまとめる。始めていなくても読める。
// アドレスの #id（ID の入力欄からのリンク）で開いたら、「ID と記録」まで送る。

import { useEffect } from 'react'
import { Link, useLocation } from 'react-router'

import { api } from './api'
import { Icon } from './Icon'
import { LoadError, Loading } from './Status'
import { usePageView } from './usePageView'
import { useLoad } from './useLoad'

export function GuidePage() {
  usePageView('guide')
  const { data, error, reload } = useLoad(api.guide)
  const { hash } = useLocation()

  useEffect(() => {
    if (data && hash) document.getElementById(hash.slice(1))?.scrollIntoView()
  }, [data, hash])

  if (error) return <LoadError message={error} onRetry={() => void reload()} />
  if (!data) return <Loading rows={4} />

  return (
    <>
      <section className="fe-section">
        <h2 className="fe-section-title">試験と収録問題</h2>
        <div className="fe-card fe-prose">
          <p>
            {data.exam_name}は、科目A 60問／90分・科目B 20問／100分。合格には両科目とも 600点／1,000点 以上が必要です。
          </p>
          <p>収録問題は {data.question_total} 問。ほかに計算問題が {data.template_total} 型あり、毎回数値が変わります。</p>
        </div>
      </section>

      <section className="fe-section">
        <h2 className="fe-section-title">苦手分野の判定</h2>
        <div className="fe-card fe-prose">
          <p>
            3問以上解いた分野のうち，60％ に寄せて平滑化した正答率が 60％ を下回るものを苦手と判定し，苦手な順で並べます。
            解答数が少ないうちに極端な判定にならないよう，平滑化してから比較しています。
          </p>
          <p>
            「おまかせ」モードでは，苦手分野が本番の出題比率より高い頻度で出ます。
            まだ手を付けていない分野も，実力が分からないので優先的に出題されます。
          </p>
        </div>
      </section>

      <section className="fe-section">
        <h2 className="fe-section-title">このアプリが対応していない問題・問題形式</h2>
        <div className="fe-card fe-warning fe-notice">
          <div className="fe-notice-title"><Icon name="exclamation-triangle" className="me-2" />本番と違うところ</div>
          <ul>
            <li>
              <strong>図を見ないと解けない問題（自作の分）</strong>
              — 流れ図、論理回路とタイミングチャート、アローダイアグラム、木構造の図などの図は、
              IPA の公開問題から転記した問題にだけ付いています（冊子の図をそのまま載せています）。
              自作の問題には図を使っていないので、図を読む問題の練習は公開問題の数に限られます。
            </li>
            <li>
              <strong>本番どおりの模擬試験</strong>
              — 科目A 60問を90分、科目B 20問を100分で通して解く形式はありません。出題は1問ずつです。
              本番の採点は IRT（項目応答理論）で1,000点満点・基準点600点なので、
              このアプリの正答率とは別物です。正答率は目安として見てください。
            </li>
            <li>
              <strong>記述・入力・並べ替え</strong>
              — 択一だけです。本番も科目A・科目Bとも多肢選択式なので形式は同じですが、
              正解は1つで部分点はありません。空欄が複数ある問題は、組合せを1つの選択肢にまとめています。
            </li>
          </ul>
          <div className="small">
            科目Aの分野ごとの「想定出題数」は IPA が公表していないため、公開問題から数えた推定値です。
            科目Bは要綱に明記のある内訳（アルゴリズムとプログラミング16問・情報セキュリティ4問）に合わせていますが、
            その中の分け方は推定です。
            問題には過去問の転記のほかに自作と自動生成の計算問題が混ざります。どれに当たるかは、答えた後に出るラベル（IPA公開問題・IPAサンプル問題・自作・自動生成）で見分けられます。
          </div>
        </div>
      </section>

      <section className="fe-section" id="id">
        <h2 className="fe-section-title">ID と記録</h2>
        <div className="fe-card fe-prose">
          <p>
            ID なしでそのまま使えます。苦手を重点的に出題し、学習モードも分野別の正答率も使えますが、
            記録はこのブラウザの中だけで、ブラウザを閉じたり、しばらく使わなかったりすると消えます。
          </p>
          <p>
            ID を作ると、解答の記録と分野ごとの理解度がその ID に残り、別の端末でも同じ ID を入れれば続きから使えます。
            合格の申告は ID があるときだけ使えます。問題メールは ID なしでも受け取れますが、メールで答えた分が個人の成績に残るのは ID で登録したときだけです（ID なしならみんなの集計にだけ数えます）。ID を作る前の解答は引き継がれません。
          </p>
          <p>
            ID をお持ちの方の入口は <Link to="/id/">ID で入る（/fe/id/）</Link> です。
            ブックマークしておくと、次から ID を入れるだけで続きを開けます。URL に ID は入りません。
          </p>
          <p>
            ID は編集画面のアカウントとは別のもので、合言葉はありません。
            ID を知っている人は誰でもその ID で入れるので、人と同じ ID は使わないでください。
            成績と出題設定は ID ごとに分かれ、問題集は全員で共通です。
            誰でも使える公開のアプリです。本名や学籍番号など、本人が分かるものは ID にしないでください。
          </p>
          <p>
            解答の記録は、ID ごとの成績が分からない形に集計して、みんなの集計の表示、問題の改善、クラブの活動紹介に使います。運営は ID ごとの記録を見られます。
          </p>
          {!data.me.code && <Link to="/id/" className="btn btn-primary btn-sm">ID を作って記録を残す</Link>}
        </div>
      </section>
    </>
  )
}
