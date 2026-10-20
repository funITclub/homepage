# wgjoin/views.py
#
# WG への参加。WG 一覧の「WG に参加」から始まり、次の順に進む。
#
#   1. アドレスの入力（start）  … 大学のアドレスを入れてもらう。サイトが運営の権限で
#                                 Classroom のクラブのクラスの名簿を引き、メンバーか確かめる
#   2. 確認のメール（sent）      … メンバーならリンク付きのメール、そうでなければ「確認できません
#                                 でした」のメールを送る。画面はどちらも同じ（他人のアドレスで
#                                 メンバーかどうかを探れないように）
#   3. リンク（verify）          … メールのリンクを開いた＝そのアドレスの持ち主。確かめの画面を出し、
#                                 本人がボタンを押したら（POST）WG の Chat スペースに追加して
#                                 GitHub へ進める。開いただけでは何もしない（メールのリンクを
#                                 先に開いて確かめる仕組みが、本人の代わりに参加させないように）
#   4. GitHub（github_*）        … 本人の GitHub アカウント（なければその場で作る）を WG のチームに
#                                 追加する。まだ org にいなければ、そのアカウントに招待が届く
#
# Chat スペースは WG の開設の申し込みを受けて運営が作る（大学の Workspace 内の誰でも参加できる設定）。
# 追加に失敗したときは本人にスペースのリンクから入ってもらい、運営にも知らせる。GitHub の手続きは続ける。
# Chat スペースが登録されていない WG では、クラブのクラスの「授業」にあるリンクから本人が入る。
#
# 会員の情報はサイトに持たない方針なので、アドレスは名簿を引いてメールを送り、Chat に追加する
# のに使うだけで、保存もログ出力もしない（確認のリンクには暗号化して入れる）。session に置くのは
# 「どの WG の手続きか」とリンクの番号、Chat に追加できたか、OAuth の state だけ。GitHub の
# ユーザー名とトークンもその場で使って捨てる。
# 最後の画面の「Chat を開く」を申請したアカウントで開くため（authuser）、アドレスは暗号化して
# 申請者のブラウザの Cookie にだけ預け、最後の画面を出したら消す（ADDRESS_COOKIE）。

import logging
import secrets
import smtplib
import time

from django.conf import settings
from django.contrib.auth.decorators import login_not_required
from django.core.mail import BadHeaderError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from catalog.models import Wg
from home.netutils import client_ip

from . import github, google, mail
from .config import chat_space_url, club_classroom_url, club_course_id, is_enabled, repo_url
from .forms import JoinEmailForm
from .http import ServiceError
from .verify import (LinkInvalid, allow_send, decrypt_address, encrypt_address, is_used, make_link_token,
                     mark_used, read_link_token)

logger = logging.getLogger(__name__)

SESSION_KEY = 'wgjoin'

#: 最後の画面の「Chat を開く」を申請したアカウントで開くため、アドレスを暗号化して申請者の
#: ブラウザに預ける Cookie。サイトの DB・セッションには置かない。最後の画面を出したら消す。
ADDRESS_COOKIE = 'wgjoin_address'
ADDRESS_COOKIE_PATH = '/wg/'


def _wg_or_404(pk):
    if not is_enabled():
        raise Http404
    wg = get_object_or_404(Wg.objects.published(), pk=pk)
    if not wg.accepts_join:
        raise Http404
    return wg


def _page(request, template, wg, status=200, **extra):
    context = {'nav': 'wg', 'wg': wg, 'classroom_url': club_classroom_url(),
               'repo_url': repo_url(wg.github_team), 'chat_url': chat_space_url(wg.chat_space), **extra}
    return render(request, template, context, status=status)


def _result(request, wg, outcome, status=200, **extra):
    """結果の画面。outcome ごとの文言はテンプレート側に持つ。

    預けたアドレスがあれば「Chat を開く」をそのアカウントで開くようにし、Cookie は消す。
    """
    request.session.pop(SESSION_KEY, None)
    email = decrypt_address(request.COOKIES.get(ADDRESS_COOKIE, ''))
    response = _page(request, 'wgjoin/result.html', wg, status=status, outcome=outcome,
                     chat_url=chat_space_url(wg.chat_space, email), **extra)
    response.delete_cookie(ADDRESS_COOKIE, path=ADDRESS_COOKIE_PATH)
    return response


@login_not_required
def start(request, pk):
    wg = _wg_or_404(pk)
    form = JoinEmailForm(request.POST or None)
    if request.method != 'POST' or not form.is_valid():
        return _page(request, 'wgjoin/start.html', wg, form=form)

    email = form.cleaned_data['email']
    if not allow_send(client_ip(request), email):
        form.add_error(None, '短い時間に何度も送られています。しばらく時間をおいてから、もう一度お試しください。')
        return _page(request, 'wgjoin/start.html', wg, status=429, form=form)

    try:
        if google.is_club_member(email, club_course_id()):
            # Chat に追加するときだけ、リンクにアドレスを（暗号化して）入れる
            token = make_link_token(wg.pk, email if wg.chat_space else None)
            url = request.build_absolute_uri(reverse('wgjoin:verify', args=[token]))
            mail.send_link(email, wg, url, repo_url(wg.github_team),
                           request.build_absolute_uri(reverse('home:guide')))
            logger.info('WG への参加: %s 確認のメールを送りました', wg.code)
        else:
            mail.send_not_member(email, wg, request.build_absolute_uri(reverse('home:join')))
            logger.info('WG への参加: %s メンバーとして確認できませんでした', wg.code)
    except ServiceError:
        # 運営の許可が切れた・クラスの先生でなくなった、など。管理者に通知される（ERROR）。
        logger.error('WG への参加: %s Classroom の名簿を確かめられませんでした', wg.code, exc_info=True)
        return _result(request, wg, 'error', status=502)
    except (smtplib.SMTPException, OSError, BadHeaderError) as e:
        # 例外の文言には宛先のアドレスが入ることがある（SMTPRecipientsRefused など）ので、種類だけ残す
        logger.error('WG への参加: %s 確認のメールを送れませんでした（%s）', wg.code, type(e).__name__)
        return _result(request, wg, 'error', status=502)

    # 送信後は完了の画面へ（戻る・再読み込みで送り直さないように）
    return redirect('wgjoin:sent', pk=wg.pk)


@login_not_required
def sent(request, pk):
    wg = _wg_or_404(pk)
    return _page(request, 'wgjoin/sent.html', wg, minutes=settings.WG_JOIN_LINK_MAX_AGE // 60)


@login_not_required
def verify(request, token):
    """GET は確かめの画面だけ。POST で Chat スペースに追加し、GitHub へ進める。"""
    try:
        wg_pk, nonce, email = read_link_token(token)
    except LinkInvalid:
        wg_pk = None
    if not is_enabled():
        raise Http404
    wg = Wg.objects.published().filter(pk=wg_pk).first() if wg_pk else None
    if wg is None or not wg.accepts_join:
        return render(request, 'wgjoin/link_invalid.html', {'nav': 'wg'}, status=400)

    if request.method != 'POST':
        return _page(request, 'wgjoin/confirm.html', wg, token=token)

    chat = None  # Chat スペースのない WG（授業のリンクから本人が入る）
    if wg.chat_space and email:
        try:
            google.add_to_chat_space(wg.chat_space, email)
            chat = 'added'
            logger.info('WG への参加: %s の Chat スペースに追加しました', wg.code)
        except ServiceError:
            # 運営の許可に Chat の権限がない・運営がスペースのメンバーでない、など。管理者に通知される
            # （ERROR）。本人には最後の画面でスペースのリンクから入るよう案内し、運営にも知らせる
            # （アドレスはこのメールにだけ載せる）。GitHub の手続きは続ける
            chat = 'failed'
            logger.error('WG への参加: %s の Chat スペースに追加できませんでした', wg.code, exc_info=True)
            try:
                mail.send_chat_failed(email, wg)
            except (smtplib.SMTPException, OSError, BadHeaderError) as e:
                logger.error('WG への参加: %s 運営への通知を送れませんでした（%s）', wg.code, type(e).__name__)

    request.session[SESSION_KEY] = {'wg': wg.pk, 'member_at': time.time(), 'nonce': nonce, 'chat': chat}
    response = redirect('wgjoin:github_start', pk=wg.pk)
    if chat:
        # 最後の画面の「Chat を開く」を申請したアカウントで開くため、申請者のブラウザに預ける
        response.set_cookie(ADDRESS_COOKIE, encrypt_address(email), max_age=settings.WG_JOIN_STEP_TIMEOUT,
                            path=ADDRESS_COOKIE_PATH, secure=settings.SESSION_COOKIE_SECURE,
                            httponly=True, samesite='Lax')
    return response


def _member_flow(request, wg):
    """確認のメールのリンクを開いた、同じ WG の手続きなら session の中身を返す。"""
    flow = request.session.get(SESSION_KEY) or {}
    checked_at = flow.get('member_at')
    if flow.get('wg') != wg.pk or not checked_at:
        return None
    if time.time() - checked_at > settings.WG_JOIN_STEP_TIMEOUT:
        return None
    return flow


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
    if is_used(flow['nonce']):
        # 同じリンクを別のブラウザでも開き、先にそちらで登録を終えた
        return _result(request, wg, 'link_used')

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

    # このリンクではもう登録させない（転送されたリンクで別の人が入れないように）
    mark_used(flow['nonce'])
    logger.info('WG への参加: %s の GitHub のチームに登録しました（%s）', wg.code, state)
    return _result(request, wg, 'done', invited=(state == github.PENDING), chat=flow.get('chat'))
