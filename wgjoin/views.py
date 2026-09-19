# wgjoin/views.py
#
# WG への参加。WG 一覧の「WG に参加」から始まり、次の順に進む。
#
#   1. 案内（start）        … 何が起きるかを見せる
#   2. Google（google_*）   … 本人の大学のアカウントで、クラブの Classroom のクラスにいるか
#                             （＝メンバーか）を確かめる。WG の授業と Chat のリンクはそのクラスの
#                             中にあるので、Chat には本人が自分で入る（サイトは何もしない）
#   3. GitHub（github_*）   … 本人の GitHub アカウント（なければその場で作る）を WG のチームに
#                             追加する。まだ org にいなければ、そのアカウントに招待が届く
#
# 2 を通った同じブラウザの、同じ WG の手続きでしか 3 に進めない（session に印を持つ）。
# メンバーでない人は 2 で止まる。
#
# 会員の情報はサイトに持たない方針なので、session に置くのは「どの WG の手続きか」と
# OAuth の state だけ。トークン・ユーザー名・メールアドレスは保存もログ出力もしない。

import logging
import secrets
import time

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from catalog.models import Wg

from . import github, google
from .config import club_classroom_url, club_course_id, is_enabled
from .http import ServiceError

logger = logging.getLogger(__name__)

SESSION_KEY = 'wgjoin'


def _wg_or_404(pk):
    if not is_enabled():
        raise Http404
    wg = get_object_or_404(Wg.objects.published(), pk=pk)
    if not wg.accepts_join:
        raise Http404
    return wg


def _result(request, wg, outcome, status=200, **extra):
    """結果の画面。outcome ごとの文言はテンプレート側に持つ。"""
    request.session.pop(SESSION_KEY, None)
    context = {'nav': 'wg', 'wg': wg, 'outcome': outcome, 'classroom_url': club_classroom_url(), **extra}
    return render(request, 'wgjoin/result.html', context, status=status)


@login_not_required
def start(request, pk):
    wg = _wg_or_404(pk)
    return render(request, 'wgjoin/start.html', {'nav': 'wg', 'wg': wg})


@login_not_required
def google_start(request, pk):
    wg = _wg_or_404(pk)
    state = secrets.token_urlsafe(24)
    verifier, challenge = google.new_pkce()
    request.session[SESSION_KEY] = {'wg': wg.pk, 'google_state': state, 'verifier': verifier}
    redirect_uri = request.build_absolute_uri(reverse('wgjoin:google_callback'))
    return redirect(google.authorize_url(state, challenge, redirect_uri))


@login_not_required
def google_callback(request):
    flow = request.session.get(SESSION_KEY) or {}
    state = flow.get('google_state')
    if not state or not secrets.compare_digest(state, request.GET.get('state', '')):
        # 別のタブで始め直した・古いリンクを開いた、など。どの WG か分からないので一覧へ。
        return redirect('home:wg_list')
    wg = _wg_or_404(flow['wg'])

    if request.GET.get('error') or not request.GET.get('code'):
        return _result(request, wg, 'cancelled')

    redirect_uri = request.build_absolute_uri(reverse('wgjoin:google_callback'))
    try:
        token = google.exchange_code(request.GET['code'], flow['verifier'], redirect_uri)
        try:
            is_member = google.is_club_member(token, club_course_id())
        finally:
            google.revoke(token)
    except ServiceError:
        logger.warning('WG への参加: %s の Google の手続きに失敗しました', wg.code, exc_info=True)
        return _result(request, wg, 'error', status=502)

    if not is_member:
        logger.info('WG への参加: %s メンバーとして確認できなかったため止めました', wg.code)
        return _result(request, wg, 'not_member', status=403)

    logger.info('WG への参加: %s メンバーであることを確認しました', wg.code)
    request.session[SESSION_KEY] = {'wg': wg.pk, 'member_at': time.time()}
    return redirect('wgjoin:github_step', pk=wg.pk)


def _member_flow(request, wg):
    """Google の確認を通った、同じ WG の手続きなら session の中身を返す。"""
    flow = request.session.get(SESSION_KEY) or {}
    checked_at = flow.get('member_at')
    if flow.get('wg') != wg.pk or not checked_at:
        return None
    if time.time() - checked_at > settings.WG_JOIN_STEP_TIMEOUT:
        return None
    return flow


@login_not_required
def github_step(request, pk):
    wg = _wg_or_404(pk)
    flow = _member_flow(request, wg)
    if flow is None:
        return redirect('wgjoin:start', pk=wg.pk)
    return render(request, 'wgjoin/github.html', {'nav': 'wg', 'wg': wg})


@login_not_required
def github_start(request, pk):
    wg = _wg_or_404(pk)
    flow = _member_flow(request, wg)
    if flow is None:
        return redirect('wgjoin:start', pk=wg.pk)
    flow['github_state'] = secrets.token_urlsafe(24)
    request.session[SESSION_KEY] = flow
    redirect_uri = request.build_absolute_uri(reverse('wgjoin:github_callback'))
    return redirect(github.authorize_url(flow['github_state'], redirect_uri))


@login_not_required
def github_callback(request):
    flow = request.session.get(SESSION_KEY) or {}
    state = flow.get('github_state')
    if not state or not secrets.compare_digest(state, request.GET.get('state', '')):
        return redirect('home:wg_list')
    wg = _wg_or_404(flow['wg'])
    if _member_flow(request, wg) is None:
        return _result(request, wg, 'expired')

    if request.GET.get('error') or not request.GET.get('code'):
        return _result(request, wg, 'github_cancelled')

    redirect_uri = request.build_absolute_uri(reverse('wgjoin:github_callback'))
    try:
        token = github.exchange_code(request.GET['code'], redirect_uri)
        try:
            username = github.login_name(token)
        finally:
            github.revoke_user_token(token)
        state = github.add_to_team(wg.github_team, username)
    except ServiceError:
        logger.warning('WG への参加: %s の GitHub の手続きに失敗しました', wg.code, exc_info=True)
        return _result(request, wg, 'github_error', status=502)

    logger.info('WG への参加: %s の GitHub のチームに登録しました（%s）', wg.code, state)
    return _result(request, wg, 'done', invited=(state == github.PENDING))
