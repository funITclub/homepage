# home/templatetags/gate.py
#
# 一覧のリンクに、サブアプリの通行証を付けるフィルタ（config/gate.py）。
# 外部の URL や通行証の要らない URL は、そのまま返る。

from django import template
from django.conf import settings

from config import gate

register = template.Library()


@register.filter
def gate_link(url):
    return gate.link(url, settings)
