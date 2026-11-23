from django.contrib.auth.decorators import login_not_required
from django.urls import path
from django.views.generic import RedirectView

from . import api, views

app_name = 'fe'

# 学習の画面は React（frontend/fe）が描く。どのアドレスでも入れ物のページ（AppView）を返し、
# 画面の切りかえは React Router が行う。名前は他の画面・メール・テストからのリンクに使う。
app = views.AppView.as_view

urlpatterns = [
    # 入口。ID の有無にかかわらず、ここがダッシュボード（まだ始めていなければ ID なしの記録を作る）
    path('', app(entry='index'), name='index'),
    # ID で入る・作る・切り替える。ID で入っていれば（?switch でなければ）ダッシュボードへ戻す
    path('id/', app(entry='open'), name='id_entry'),
    # 以前の ID ありの入口（マイページ）。ブックマークが残っていても困らないよう、入口へ送る
    # （サイト全体のログイン必須を外す。学習の画面と同じくログインなしで開けるように）
    path('mypage/', login_not_required(RedirectView.as_view(pattern_name='fe:index')), name='mypage'),
    # このアプリについて（試験の概要・使い方・対応していない問題・ID と記録）
    path('about/', app(entry='open'), name='about'),
    # 以前の「このアプリについて」の URL。ブックマークが残っていても困らないよう、新しい URL へ送る
    path('guide/', login_not_required(RedirectView.as_view(pattern_name='fe:about', permanent=True)),
         name='guide'),
    # 1問1答。問題メールの「1問1答を解く」からも案内するので、記録が無ければその場で作る
    path('quiz/', app(entry='start'), name='quiz'),
    # 学習モード（先に解説を読み、そのあと同じ範囲を解く）
    path('learn/', app(), name='learn_start'),
    path('learn/<int:pk>/read/', app(), name='learn_read'),
    path('learn/<int:pk>/quiz/', app(), name='learn_quiz'),
    path('learn/<int:pk>/result/', app(), name='learn_result'),
    path('stats/', app(), name='stats'),
    path('history/', app(), name='history'),
    path('planandcheck/', app(), name='plan'),

    # React の画面が呼ぶ API（api.py）
    path('api/me/', api.MeAPI.as_view(), name='api_me'),
    path('api/enter/', api.EnterAPI.as_view(), name='api_enter'),
    path('api/leave/', api.LeaveAPI.as_view(), name='api_leave'),
    path('api/pageview/', api.PageViewAPI.as_view(), name='api_pageview'),
    path('api/dashboard/', api.DashboardAPI.as_view(), name='api_dashboard'),
    path('api/guide/', api.GuideAPI.as_view(), name='api_guide'),
    path('api/settings/', api.SettingsAPI.as_view(), name='api_settings'),
    path('api/quiz/next/', api.QuizNextAPI.as_view(), name='api_quiz_next'),
    path('api/quiz/answer/', api.QuizAnswerAPI.as_view(), name='api_quiz_answer'),
    path('api/stats/', api.StatsAPI.as_view(), name='api_stats'),
    path('api/history/', api.HistoryAPI.as_view(), name='api_history'),
    # 本番合格の申告（集計はダッシュボードに出す）
    path('api/pass/', api.PassReportAPI.as_view(), name='api_pass'),
    path('api/plan/', api.PlanAPI.as_view(), name='api_plan'),
    # 問題メール（9〜18時の毎時に3問。登録はダッシュボードから、確定と解除はメールのリンクから）
    path('api/mail/', api.MailAPI.as_view(), name='api_mail'),
    path('api/learn/', api.LearnStartAPI.as_view(), name='api_learn'),
    path('api/learn/<int:pk>/read/', api.LearnReadAPI.as_view(), name='api_learn_read'),
    # 読み上げを再生している間は、読む時間を止める
    path('api/learn/<int:pk>/timer/', api.LearnTimerAPI.as_view(), name='api_learn_timer'),
    path('api/learn/<int:pk>/quiz/', api.LearnQuizAPI.as_view(), name='api_learn_quiz'),
    path('api/learn/<int:pk>/next/', api.LearnNextAPI.as_view(), name='api_learn_next'),
    path('api/learn/<int:pk>/abandon/', api.LearnAbandonAPI.as_view(), name='api_learn_abandon'),
    path('api/learn/<int:pk>/result/', api.LearnResultAPI.as_view(), name='api_learn_result'),

    # 技術解説の読み上げ音声（manage.py make_note_audio で作ったもの）
    path('learn/audio/<str:name>', views.NoteAudioView.as_view(), name='note_audio'),

    # 問題メールの確定と解除（メールのリンクから開く）。Django の画面のまま
    path('mail/confirm/<str:token>/', views.MailConfirmView.as_view(), name='mail_confirm'),
    path('mail/stop/<str:token>/', views.MailStopView.as_view(), name='mail_stop'),
    path('tasks/send-mails/', views.SendMailsView.as_view(), name='send_mails'),

    # 問題メールの1問ごとの解答ページ（答えると、メールを送った ID の成績に記録する）。Django の画面
    path('m/<str:code>/', views.MailAnswerView.as_view(), name='mail_answer'),

    # 問題の管理（全 ID で共有する問題集。学習の画面とは別ページで、編集画面のログインが要る。
    # 登録は JSON の一括差し替えで行う）。Django の画面のまま
    path('console/', RedirectView.as_view(pattern_name='fe:manage_list'), name='console'),
    path('console/questions/', views.ManageListView.as_view(), name='manage_list'),
    path('console/upload/', views.QuestionUploadView.as_view(), name='manage_upload'),
    # 学習の画面のページビュー（直近30日）
    path('console/pageviews/', views.PageViewListView.as_view(), name='manage_pageviews'),
]
