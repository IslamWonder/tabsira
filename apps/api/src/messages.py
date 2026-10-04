"""
User-visible text that the API itself produces, in Arabic, in one place.

Error details stay in English: they are for developers and the web app maps the
error code to its own Arabic message. What reaches a person directly lives here:
the subject lines of the mail (the body of each mail lives in its template under
src/templates/email/<language>), the questions the pipeline puts to the person who took the
photo, and the statements of rules that forbid an inference.

A text with `{label}` takes the Arabic label of the entity it is about.

Every text is keyed by language (decision 36): `messages_for(language)` returns the
catalog of one language, the default one when the language is not given or not
known. Arabic is the only catalog today; a second language is a second catalog and
a second template folder, and no URL moves.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.config import DEFAULT_LANGUAGE


@dataclass(frozen=True)
class Messages:
    """Every text the API produces, in one language."""

    language: str
    direction: Literal["rtl", "ltr"]
    site_name: str
    # Mail subjects. The bodies are the templates of the language.
    verify_email_subject: str
    reset_password_subject: str
    # Cookie consent: the categories a visitor chooses between (decision 32).
    consent_necessary_title: str
    consent_necessary_description: str
    consent_analytics_title: str
    consent_analytics_description: str
    consent_behaviour_title: str
    consent_behaviour_description: str
    # تبصرة تواصل: why a post is in the feed, and what happened to a post or a comment.
    why_followed_author: str
    why_fresh: str
    why_new_topic: str
    why_community: str
    outcome_guard_unavailable: str
    outcome_guard_uncertain: str
    outcome_reported: str
    outcome_unknown: str
    outcome_rejected: str
    # What a moderator's or the guard's code is called when the author is told.
    outcome_reasons: dict[str, str]
    reason_labels: dict[str, str]
    # Clarification questions, one per constraint that asks something.
    question_specify_before_search: str
    question_confirm_scene_meaning: str
    question_confirm_role_or_relation: str
    question_confirm_action: str
    question_confirm_worship_action: str
    question_confirm_identity_of_thing: str
    # A constraint this version of the code does not know: ask, and assume nothing.
    question_unknown_constraint: str
    # Rules that forbid an inference, stated for the prompts and for the person.
    rule_no_diagnosis: str
    rule_no_person_identity: str


ARABIC = Messages(
    language="ar",
    direction="rtl",
    site_name="تبصرة",
    verify_email_subject="أكّد بريدك الإلكتروني في تبصرة",
    reset_password_subject="إعادة تعيين كلمة المرور في تبصرة",  # noqa: S106 - a mail subject  # nosec B106
    consent_necessary_title="ضرورية",
    consent_necessary_description=(
        "تُبقيك مسجّلًا للدخول وتحمي حسابك وهذا الموقع. لا يعمل التطبيق من دونها،"
        " ولذلك لا يمكن إيقافها، ولا تُستعمل في أي تحليل."
    ),
    consent_analytics_title="التحليلات",
    consent_analytics_description=(
        "تساعدنا على فهم كيف يُستعمل تبصرة: أي الصفحات تُزار، وكم يدوم البقاء فيها،"
        " وما الذي يُنقر عليه. تُستعمل لذلك خدمة Google Analytics. لا يُرسل إليها ملفك الشخصي،"
        " ولا صورك، ولا ما تكتبه، ولا نص أي بصيرة أو آية، ولا موقعك، ولا بريدك الإلكتروني."
    ),
    consent_behaviour_title="السلوك وخرائط التفاعل",
    consent_behaviour_description=(
        "تُسجَّل حركة المؤشر والتمرير والنقرات على صفحات تبصرة لنعرف أين يتعثّر الناس."
        " تُستعمل لذلك خدمة Microsoft Clarity، وتُخفى فيها كل خانة كتابة وكل نص كتبه المستخدمون."
    ),
    why_followed_author="لأنك تتابع {name}",
    why_fresh="بصيرة نُشرت قبل قليل",
    why_new_topic="لتنويع ما تقرؤه: موضوع مختلف عمّا قبله",
    why_community="من بصائر المجتمع",
    outcome_guard_unavailable="تعذّرت المراجعة الآلية الآن، فسيراجعه مشرف قبل نشره.",
    outcome_guard_uncertain="يحتاج إلى مراجعة مشرف قبل نشره.",
    outcome_reported="وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف.",
    outcome_unknown="لم يُقبل لأنه يخالف قواعد المجتمع.",
    outcome_rejected="لم يُقبل لأنه يخالف قواعد المجتمع: {reason}.",
    outcome_reasons={
        "guard_unavailable": "تعذّرت المراجعة الآلية الآن، فسيراجعه مشرف قبل نشره.",
        "guard_uncertain": "يحتاج إلى مراجعة مشرف قبل نشره.",
        "reported": "وصلتنا عنه بلاغات، فأُخفي مؤقتًا حتى يراجعه مشرف.",
    },
    reason_labels={
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
    },
    question_specify_before_search="ما نوع «{label}» الذي تقصده، أو ما الذي يحدث هنا بالضبط؟",
    question_confirm_scene_meaning="ما الذي يحدث في هذا المشهد كما تراه أنت؟",
    question_confirm_role_or_relation="ما الجانب الذي تريد أن ننظر إليه في هذا الموقف؟",
    question_confirm_action="ما الذي يُفعل بـ«{label}» في هذا المشهد؟",
    question_confirm_worship_action=(
        "لا نحكم على ما يجري من الصورة وحدها. ما الذي تريد أن نتأمله في «{label}»؟"
    ),
    question_confirm_identity_of_thing="هل تقصد «{label}» تحديدًا؟",
    question_unknown_constraint="وضّح لنا ما تقصده في «{label}» حتى نكمل.",
    rule_no_diagnosis="لا يُستنتج أي تشخيص طبي أو نفسي أو صحي من الصورة.",
    rule_no_person_identity="لا تُستنتج هوية أي شخص ولا علاقته بغيره من الصورة.",
)

CATALOGS: dict[str, Messages] = {ARABIC.language: ARABIC}


def messages_for(language: str | None = None) -> Messages:
    """Return the catalog of `language`, or of the default language when it is None or unknown."""
    return CATALOGS.get(language or DEFAULT_LANGUAGE, CATALOGS[DEFAULT_LANGUAGE])
