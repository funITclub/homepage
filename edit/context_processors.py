# edit/context_processors.py
#
# どのテンプレートからも問い合わせ先を出せるようにする。
# 実体は管理者テーブル（edit.Administrator）にあるので、テンプレートには
# アドレスを書かない。担当者が代わってもテーブルを直すだけで全ページに反映される。

import logging

from django.core.cache import cache

from .models import public_contact_email

logger = logging.getLogger(__name__)

#: 毎リクエスト DB を引かないためのキャッシュ
CACHE_KEY = 'public-contact-email'
CACHE_SECONDS = 60


def public_contact(request):
    """{{ public_contact }} で問い合わせ先を参照できるようにする。"""
    try:
        email = cache.get(CACHE_KEY)
        if email is None:
            email = public_contact_email()
            cache.set(CACHE_KEY, email, CACHE_SECONDS)
    except Exception:
        # キャッシュが落ちていても表示は続ける
        email = public_contact_email()

    return {'public_contact': email}
