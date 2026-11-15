"""問題メール。9〜18時の毎時0分に、登録しているアドレスへ1通・3問ずつ届く。

登録 … ダッシュボードから。ID で入っていれば その ID に1件、ID なしでも登録できる（learner なし）。
       1つのアドレスで受け取れる登録は1つだけ（confirm が、同じアドレスのほかの登録を止める）。
       ID には合言葉がなく、ID を知っている人なら
       誰でも操作できるので、入力されたアドレスに確認のメールを送り、そのリンクを
       開いて「受け取る」を押したアドレスだけを配信先にする。確認待ちのアドレスは、
       確認の期限を過ぎたら消す（purge_pending）。登録したあとは、画面から
       アドレスを変えられない（変えたいときは解除して登録し直す）。
解除 … 登録されたアドレスに届く問題メールの末尾のリンクからだけできる（ID のあり・なしとも。
       画面からは解除しない）。
送信 … GitHub Actions（.github/workflows/fe-mails.yml）が9〜18時の毎時に /fe/tasks/send-mails/ を
       時間帯（h09〜h18）と日付つきで呼ぶ（send_slot）。問題は科目Aの IPA 公開問題から、
       1問1答の「IPA公開問題からおまかせ」と同じ選び方（その ID の苦手を重く）で3問。
       メールには問題と選択肢だけを載せ、1問ごとの解答ページ（/fe/m/<記号>/）で答えると、
       その ID の解答履歴と分野別の理解度に記録する（MailQuestion・record_answer）。
       ID なしの登録は、個人の記録には残さず、みんなの集計（OpenProgress）にだけ足す。
       登録・日付・時間帯の組で、同じ枠には二重に送らない。

2026-11 までの「マラソン」「特訓」（毎日0時に1通・最大10問・解答つき）はやめた。

メールはテキストだけ（HTML のメールにはしない）。図はテキストに載せられないので、
図のある問題は解答ページで見てもらう。
アドレスは DB に暗号化して持ち（fe.crypto）、ログに出さない。
"""

import datetime
import hashlib
import logging
import random
import secrets
import smtplib
import string

from django.conf import settings
from django.core import signing
from django.core.mail import BadHeaderError, EmailMessage
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .models import (Attempt, MailQuestion, MailSubscription, OpenProgress, Question, StudySession,
                     SUBJECT_A)
from .selection import pick_question
from .stats import category_stats, record_progress
from .slots import SLOT_HOURS, WEEKDAYS, citation, slot_date

logger = logging.getLogger(__name__)

CONFIRM_SALT = 'fe.mail.confirm'
STOP_SALT = 'fe.mail.stop'
# 1通に載せる問題の数
QUESTIONS_PER_MAIL = 3
# 同じ問題を続けて送らないよう、直近これだけの時間に送った問題は避ける（尽きたら避けない）
RECENT_HOURS = 24
CODE_LENGTH = 10
CODE_ALPHABET = string.ascii_letters + string.digits


class LinkInvalid(Exception):
    """リンクが壊れている・期限切れ・いまのアドレスあてのものではない。"""


def _address_key(email):
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def absolute(path):
    return settings.SITE_URL.rstrip('/') + path


def can_send_link(subscription, now=None):
    """確認のメールを送ってよいか。続けて送らせない（settings.FE_MAIL_LINK_INTERVAL）。"""
    if subscription.link_sent_at is None:
        return True
    now = now or timezone.now()
    return (now - subscription.link_sent_at).total_seconds() >= settings.FE_MAIL_LINK_INTERVAL


# ---- 確認と解除のリンク ----

def make_confirm_token(subscription):
    """確認のリンクに入れる値。アドレスは入れず、確認待ちのアドレスの印だけを入れる。"""
    return signing.dumps(
        {'s': subscription.pk, 'a': _address_key(subscription.pending_email)}, salt=CONFIRM_SALT,
    )


def read_confirm_token(token):
    """MailSubscription。確認待ちのアドレスが替わっていたり、登録済みなら LinkInvalid。"""
    try:
        data = signing.loads(token, salt=CONFIRM_SALT, max_age=settings.FE_MAIL_CONFIRM_MAX_AGE)
    except signing.BadSignature as e:  # SignatureExpired も含む
        raise LinkInvalid from e
    subscription = MailSubscription.objects.filter(pk=data['s']).first()
    if subscription is None or subscription.email or not subscription.pending_email:
        raise LinkInvalid
    if _address_key(subscription.pending_email) != data['a']:
        raise LinkInvalid
    return subscription


def same_address(email, exclude=None):
    """そのアドレスで受け取っている登録。アドレスは暗号化して持っているので、読んで比べる
    （登録は多くないので、すべて読んでも重くない）。"""
    key = _address_key(email)
    found = []
    for subscription in MailSubscription.objects.exclude(email_enc=''):
        if subscription.pk != (exclude.pk if exclude else None) and subscription.email \
                and _address_key(subscription.email) == key:
            found.append(subscription)
    return found


def confirm(subscription):
    """確認待ちのアドレスを配信先にする。

    1つのアドレスで受け取れる登録は1つだけ。同じアドレスで受け取っていたほかの登録
    （別の ID や ID なし）は止める。アドレスの持ち主が確認のリンクを開いたので、新しい方を正とする。
    """
    email = subscription.pending_email
    for other in same_address(email, exclude=subscription):
        stop(other)
    subscription.email = email
    subscription.pending_email = ''
    subscription.save(update_fields=['email_enc', 'pending_email_enc'])


def purge_pending(now=None):
    """確認の期限（FE_MAIL_CONFIRM_MAX_AGE）を過ぎた確認待ちのアドレスを消す。消した件数を返す。

    期限を過ぎたリンクはもう使えないので、アドレスを残しておく理由がない。
    毎日の送信のたびと、ダッシュボードを開いたときに呼ぶ。
    """
    now = now or timezone.now()
    limit = now - datetime.timedelta(seconds=settings.FE_MAIL_CONFIRM_MAX_AGE)
    purged = (
        MailSubscription.objects.exclude(pending_email_enc='')
        .filter(Q(link_sent_at__lt=limit) | Q(link_sent_at__isnull=True))
        .update(pending_email_enc='')
    )
    # ID なしの登録は、アドレスが無くなったら（期限切れ・解除）残しておく理由がない
    MailSubscription.objects.filter(learner__isnull=True, email_enc='', pending_email_enc='').delete()
    return purged


def make_stop_token(subscription):
    """解除のリンクに入れる値。配信先が替わったら、前のアドレスあてのリンクは効かなくなる。"""
    return signing.dumps(
        {'s': subscription.pk, 'a': _address_key(subscription.email)}, salt=STOP_SALT,
    )


def read_stop_token(token):
    """MailSubscription。いまの配信先あてのリンクでなければ LinkInvalid。"""
    try:
        data = signing.loads(token, salt=STOP_SALT)
    except signing.BadSignature as e:
        raise LinkInvalid from e
    subscription = MailSubscription.objects.filter(pk=data['s']).first()
    if subscription is None or not subscription.email:
        raise LinkInvalid
    if _address_key(subscription.email) != data['a']:
        raise LinkInvalid
    return subscription


def stop(subscription):
    """解除する。アドレスを消し、送り方の選択と進み具合は残す（登録し直したら続きから）。"""
    subscription.email = ''
    subscription.save(update_fields=['email_enc'])


def _footer():
    return (
        '--\n'
        '{} 基本情報技術者試験 対策\n'
        'このメールは自動送信です。\n'
    ).format(settings.SITE_NAME)


def whose(subscription):
    """文面の「の ID「○○」」。ID なしの登録なら空。"""
    return 'の ID「{}」'.format(subscription.learner.code) if subscription.learner else ''


def record_note(subscription):
    """メールで答えた分がどこに記録されるか。"""
    if subscription.learner:
        return 'メールの「この問題に答える」から答えると、ID「{}」の成績に記録されます。'.format(
            subscription.learner.code)
    return ('ID なしで登録しているので、メールの「この問題に答える」から答えた分は、\n'
            'みんなの集計にだけ数えます（個人の成績には残りません）。')


def send_confirmation(subscription):
    """確認待ちのアドレスあて。リンクを開いて「受け取る」を押すと配信先になる。"""
    url = absolute(reverse('fe:mail_confirm', args=[make_confirm_token(subscription)]))
    minutes = settings.FE_MAIL_CONFIRM_MAX_AGE // 60
    EmailMessage(
        subject='[{}] 基本情報の問題メールの確認'.format(settings.SITE_NAME),
        body=(
            '基本情報技術者試験 対策{whose}で、このアドレスに問題メールを送る手続きがありました。\n\n'
            '次のリンクを開いて「受け取る」を押すと、登録されます（{minutes}分以内）。\n'
            '{url}\n\n'
            '登録すると、毎日9時から18時まで毎時、IPA の公開問題が3問ずつ届きます。\n'
            '{record}\n\n'
            '■ 解除について\n'
            '登録したあとは、このアドレスに届くメールのリンクからしか解除できません\n'
            '（画面からはアドレスの変更も解除もできません）。解除のリンクは毎回のメールに付いています。\n\n'
            '■ このメールに心当たりがない場合\n'
            '第三者があなたのメールアドレスを入力した可能性があります。\n'
            'このメールを破棄していただければ、登録されず、今後メールは届きません。\n\n'
        ).format(whose=whose(subscription), record=record_note(subscription),
                 minutes=minutes, url=url) + _footer(),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[subscription.pending_email],
    ).send()


# ---- 送る問題を選ぶ ----

def pick_questions(subscription, count=QUESTIONS_PER_MAIL):
    """その ID に送る問題。科目Aの IPA 公開問題から、1問1答の「IPA公開問題からおまかせ」と
    同じ選び方（selection.pick_question。苦手な分野を重く、未出題・前回まちがえた問題を先に）で選ぶ。

    出題設定は使わず（分野は指定しない）、その ID の設定も書き換えない。直近 RECENT_HOURS 時間に
    メールで送った問題は避ける。避けると選べなくなったら、避けずに選ぶ。
    ID なしの登録は、苦手が分からないので偏りを付けずに選ぶ。
    """
    learner = subscription.learner
    since = timezone.now() - datetime.timedelta(hours=RECENT_HOURS)
    recent = list(
        MailQuestion.objects.filter(subscription=subscription, created_at__gte=since)
        .values_list('question_id', flat=True)
    )
    if learner is None:
        # ID なしは苦手が分からないので、偏りを付けずに選ぶ
        pool = list(Question.objects.active().from_ipa().filter(subject=SUBJECT_A))
        fresh = [q for q in pool if q.id not in recent]
        return random.sample(fresh if len(fresh) >= count else pool, min(count, len(pool)))
    session = StudySession(learner=learner, mode=StudySession.MODE_IPA, subject=SUBJECT_A)
    picked = []
    for _ in range(count):
        taken = [q.id for q in picked]
        question, _reason = pick_question(learner, session, exclude_ids=recent + taken)
        if question is None or question.id in taken or question.id in recent:
            question, _reason = pick_question(learner, session, exclude_ids=taken)
        if question is None or question.id in taken:
            break
        picked.append(question)
    return picked


def new_code():
    while True:
        code = ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if not MailQuestion.objects.filter(code=code).exists():
            return code


def answer_url(mail_question):
    return absolute(reverse('fe:mail_answer', args=[mail_question.code]))


def purge_old(now=None):
    """送ってから FE_MAIL_KEEP_DAYS 日たった問題を、行ごと消す。消した件数を返す。"""
    today = timezone.localdate(now or timezone.now())
    limit = today - datetime.timedelta(days=settings.FE_MAIL_KEEP_DAYS)
    deleted, _ = MailQuestion.objects.filter(date__lte=limit).delete()
    return deleted


def is_open(mail_question, now=None):
    """解答ページを見せてよいか。消す前でも、期限を過ぎたら案内ページにする。"""
    today = timezone.localdate(now or timezone.now())
    return mail_question.date > today - datetime.timedelta(days=settings.FE_MAIL_KEEP_DAYS)


def record_answer(mail_question, selected):
    """解答ページで選んだ答えを、その ID の解答履歴と分野別の理解度に記録する。正誤を返す。

    1問につき記録は1回だけ。答えたあとに開き直したり別の選択肢を押したりしても、
    最初の答えのまま（二重に数えない）。ID が消えていれば行ごと消えているので、ここには来ない。
    ID なしの登録なら、個人の記録には残さず、みんなの集計（OpenProgress）にだけ足す。
    """
    if mail_question.selected_index is not None:
        return mail_question.is_correct
    question = mail_question.question
    learner = mail_question.subscription.learner
    is_correct = selected == question.answer_index
    if learner is None:
        # ID なしの登録。個人の記録には残さず、みんなの集計にだけ足す（X の解答ページと同じ）
        with transaction.atomic():
            updated = MailQuestion.objects.filter(
                pk=mail_question.pk, selected_index__isnull=True,
            ).update(selected_index=selected, is_correct=is_correct, answered_at=timezone.now())
            if not updated:
                mail_question.refresh_from_db()
                return mail_question.is_correct
            progress, _ = OpenProgress.objects.get_or_create(
                category=question.category, subject=question.subject,
            )
            OpenProgress.objects.filter(pk=progress.pk).update(
                answered=F('answered') + 1, correct=F('correct') + (1 if is_correct else 0),
            )
        mail_question.selected_index, mail_question.is_correct = selected, is_correct
        return is_correct
    with transaction.atomic():
        updated = MailQuestion.objects.filter(
            pk=mail_question.pk, selected_index__isnull=True,
        ).update(selected_index=selected, is_correct=is_correct, answered_at=timezone.now())
        if not updated:
            # 同時に答えられた。先に記録した方に任せる
            mail_question.refresh_from_db()
            return mail_question.is_correct
        Attempt.objects.create(
            learner=learner, question=question, category=question.category,
            selected_index=selected, is_correct=is_correct,
        )
        record_progress(learner, question, is_correct)
    mail_question.selected_index, mail_question.is_correct = selected, is_correct
    return is_correct


# ---- 組み立てと送信 ----

def subject_line(today, slot):
    return '[{}] 基本情報 {}/{}（{}）{}時の問題（{}問）'.format(
        settings.SITE_NAME, today.month, today.day, WEEKDAYS[today.weekday()],
        SLOT_HOURS[slot], QUESTIONS_PER_MAIL,
    )


def build_message(subscription, mail_questions, today, slot):
    """1通ぶんのメール（テキストだけ）。問題と選択肢、1問ごとの解答ページへのリンク、自分の分野別正答率。

    HTML のメールにはしない（ユーザーの指示）。図はテキストに載せられないので、図のある問題には
    「図は解答ページで見られる」と書き添える。解答ページには図をそのまま出している。
    """
    learner = subscription.learner
    rows = []
    for mail_question in mail_questions:
        question = mail_question.question
        rows.append({
            'number': mail_question.number,
            'question': question,
            'figure_count': len(question.figures or []),
            'choices': [
                {'label': label, 'text': text, 'figure': bool(question.choice_figure(i))}
                for i, label, text in question.labeled_choices()
            ],
            'answer_url': answer_url(mail_question),
            # IPA の求める形の出典（X の投稿と同じ。「出典：令和7年度 基本情報技術者試験 科目A 問2」）
            'citation': citation(question.source),
        })
    stats = (
        [row for row in category_stats(learner, subject=SUBJECT_A) if row['question_count']]
        if learner else []
    )
    context = {
        'today': today,
        'hour': SLOT_HOURS[slot],
        'weekday': WEEKDAYS[today.weekday()],
        'rows': rows,
        'stats': stats,
        'learner': learner,
        'record_note': record_note(subscription),
        # メールを読んだその流れで、すぐ解けるよう1問1答へ
        'quiz_url': absolute(reverse('fe:quiz')),
        'stop_url': absolute(reverse('fe:mail_stop', args=[make_stop_token(subscription)])),
        'site_name': settings.SITE_NAME,
        'keep_days': settings.FE_MAIL_KEEP_DAYS,
    }
    return EmailMessage(
        subject=subject_line(today, slot),
        body=render_to_string('fe/email/daily.txt', context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[subscription.email],
    )


def _send(message, subscription):
    try:
        message.send()
    except (smtplib.SMTPException, OSError, BadHeaderError) as e:
        # 例外の文言には宛先のアドレスが入ることがあるので、種類だけ残す
        logger.error('問題メールを送れませんでした（ID %s、%s）',
                     subscription.learner.code if subscription.learner else 'なし', type(e).__name__)
        return False
    return True


def send_slot(slot, today=None):
    """その日のその時間帯の分を送る。通数を返す。何度呼んでも、同じ枠には1通だけ。

    today はその枠の予定の日付。渡されなければ slots.slot_date で決める（遅れて届いた
    呼び出しを前の日の枠とみなす決まりも同じ）。1件の失敗でほかを止めない。送れなかった
    枠の問題は消すので、次に同じ枠で呼ばれたときに送り直す。
    """
    today = today or slot_date(slot)
    purge_pending()
    purged = purge_old()
    result = {'sent': 0, 'already': 0, 'failed': 0, 'purged': purged}
    subscriptions = (
        MailSubscription.objects.exclude(email_enc='').select_related('learner')
        # ID で登録したもの（ID が残っているもの）と、ID なしで登録したもの
        .filter(Q(learner__isnull=True) | Q(learner__code__isnull=False))
    )
    for subscription in subscriptions:
        if not subscription.email:
            # 鍵が替わって読めなくなったもの。送れないので飛ばす
            continue
        if MailQuestion.objects.filter(subscription=subscription, date=today, slot=slot).exists():
            result['already'] += 1
            continue
        questions = pick_questions(subscription)
        if not questions:
            continue
        try:
            with transaction.atomic():
                rows = [
                    MailQuestion.objects.create(
                        subscription=subscription, question=question, date=today, slot=slot,
                        number=number, code=new_code(),
                    )
                    for number, question in enumerate(questions, start=1)
                ]
        except IntegrityError:
            # 同じ枠の呼び出しが重なった。先に作った方に任せる
            result['already'] += 1
            continue
        if not _send(build_message(subscription, rows, today, slot), subscription):
            MailQuestion.objects.filter(pk__in=[row.pk for row in rows]).delete()
            result['failed'] += 1
            continue
        result['sent'] += 1
    return result
