"""
User-visible text that the API itself produces, in Arabic, in one place.

Error details stay in English: they are for developers and the web app maps the
error code to its own Arabic message. What lands in a person's inbox is
different, so the subject lines of the mail live here, and the body of each mail
lives in its template (src/templates/email).
"""

from __future__ import annotations

SITE_NAME = "تبصرة"

VERIFY_EMAIL_SUBJECT = "أكّد بريدك الإلكتروني في تبصرة"
RESET_PASSWORD_SUBJECT = "إعادة تعيين كلمة المرور في تبصرة"  # noqa: S105 - a mail subject  # nosec B105
