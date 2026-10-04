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

# ─── Cookie consent: the categories a visitor chooses between (decision 32) ───

CONSENT_NECESSARY_TITLE = "ضرورية"
CONSENT_NECESSARY_DESCRIPTION = (
    "تُبقيك مسجّلًا للدخول وتحمي حسابك وهذا الموقع. لا يعمل التطبيق من دونها،"
    " ولذلك لا يمكن إيقافها، ولا تُستعمل في أي تحليل."
)
CONSENT_ANALYTICS_TITLE = "التحليلات"
CONSENT_ANALYTICS_DESCRIPTION = (
    "تساعدنا على فهم كيف يُستعمل تبصرة: أي الصفحات تُزار، وكم يدوم البقاء فيها،"
    " وما الذي يُنقر عليه. تُستعمل لذلك خدمة Google Analytics. لا يُرسل إليها ملفك الشخصي،"
    " ولا صورك، ولا ما تكتبه، ولا نص أي بصيرة أو آية، ولا موقعك، ولا بريدك الإلكتروني."
)
CONSENT_BEHAVIOUR_TITLE = "السلوك وخرائط التفاعل"
CONSENT_BEHAVIOUR_DESCRIPTION = (
    "تُسجَّل حركة المؤشر والتمرير والنقرات على صفحات تبصرة لنعرف أين يتعثّر الناس."
    " تُستعمل لذلك خدمة Microsoft Clarity، وتُخفى فيها كل خانة كتابة وكل نص كتبه المستخدمون."
)

# ─── تبصرة تواصل: why a post is in the feed, and what happened to a post or a comment ───

WHY_FOLLOWED_AUTHOR = "لأنك تتابع {name}"
WHY_FRESH = "بصيرة نُشرت قبل قليل"
WHY_NEW_TOPIC = "لتنويع ما تقرؤه: موضوع مختلف عمّا قبله"
WHY_COMMUNITY = "من بصائر المجتمع"

# The code a post or a comment carries as `status_reason`, and what the author is told.
# A code that is not here gets OUTCOME_UNKNOWN: a moderator's reason is never shown raw.
OUTCOME_GUARD_UNAVAILABLE = "تعذّرت المراجعة الآلية الآن، فسيراجعه مشرف قبل نشره."
OUTCOME_GUARD_UNCERTAIN = "يحتاج إلى مراجعة مشرف قبل نشره."
OUTCOME_REPORTED = "وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف."
OUTCOME_UNKNOWN = "لم يُقبل لأنه يخالف قواعد المجتمع."
OUTCOME_REJECTED = "لم يُقبل لأنه يخالف قواعد المجتمع: {reason}."
OUTCOME_REASONS: dict[str, str] = {
    "guard_unavailable": OUTCOME_GUARD_UNAVAILABLE,
    "guard_uncertain": OUTCOME_GUARD_UNCERTAIN,
    "reported": OUTCOME_REPORTED,
}
# What a guard category, or a moderator's reason, is called when the author is told.
REASON_LABELS: dict[str, str] = {
    "harassment": "إساءة أو مضايقة",
    "hate": "خطاب كراهية",
    "sexual": "محتوى جنسي",
    "violence": "عنف",
    "self_harm": "إيذاء النفس",
    "illicit": "نشاط غير مشروع",
    "abuse": "إساءة أو مضايقة",
    "spam": "محتوى مزعج أو إعلاني",
    "false_religious_claim": "نسبة قول ديني إلى غير قائله",
    "unauthorised_photo": "صورة منشورة دون إذن",
    "private_information": "معلومات خاصة",
    "wrong_place": "مكان غير صحيح",
    "other": "مخالفة أخرى",
}
