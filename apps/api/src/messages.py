"""
User-visible text that the API itself produces, in Arabic, in one place.

Error details stay in English: they are for developers and the web app maps the
error code to its own Arabic message. What reaches a person directly lives here:
the subject lines of the mail (the body of each mail lives in its template under
src/templates/email), the questions the pipeline puts to the person who took the
photo, and the statements of rules that forbid an inference.

A text with `{label}` takes the Arabic label of the entity it is about.
"""

from __future__ import annotations

SITE_NAME = "تبصرة"

VERIFY_EMAIL_SUBJECT = "أكّد بريدك الإلكتروني في تبصرة"
RESET_PASSWORD_SUBJECT = "إعادة تعيين كلمة المرور في تبصرة"  # noqa: S105 - a mail subject  # nosec B105
# ─── Clarification questions, one per constraint that asks something ───

QUESTION_SPECIFY_BEFORE_SEARCH = "ما نوع «{label}» الذي تقصده، أو ما الذي يحدث هنا بالضبط؟"
QUESTION_CONFIRM_SCENE_MEANING = "ما الذي يحدث في هذا المشهد كما تراه أنت؟"
QUESTION_CONFIRM_ROLE_OR_RELATION = "ما الجانب الذي تريد أن ننظر إليه في هذا الموقف؟"
QUESTION_CONFIRM_ACTION = "ما الذي يُفعل بـ«{label}» في هذا المشهد؟"
QUESTION_CONFIRM_WORSHIP_ACTION = (
    "لا نحكم على ما يجري من الصورة وحدها. ما الذي تريد أن نتأمله في «{label}»؟"
)
QUESTION_CONFIRM_IDENTITY_OF_THING = "هل تقصد «{label}» تحديدًا؟"
# A constraint this version of the code does not know: ask, and assume nothing.
QUESTION_UNKNOWN_CONSTRAINT = "وضّح لنا ما تقصده في «{label}» حتى نكمل."

# ─── Rules that forbid an inference, stated for the prompts and for the person ───

RULE_NO_DIAGNOSIS = "لا يُستنتج أي تشخيص طبي أو نفسي أو صحي من الصورة."
RULE_NO_PERSON_IDENTITY = "لا تُستنتج هوية أي شخص ولا علاقته بغيره من الصورة."
