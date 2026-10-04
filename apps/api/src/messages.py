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

from src.config import Settings, get_settings


@dataclass(frozen=True)
class Messages:
    """Every text the API produces, in one language."""

    language: str
    direction: Literal["rtl", "ltr"]
    site_name: str
    # Mail subjects. The bodies are the templates of the language.
    verify_email_subject: str
    reset_password_subject: str
    # The support form's mail, which reaches the team, not the visitor: its subject
    # (`{topic}` is the topic label below), the labels of its plain-text body, and the
    # label of each topic keyed by the topic's code.
    support_subject: str
    support_label_topic: str
    support_label_name: str
    support_label_email: str
    support_label_match: str
    support_match_yes: str
    support_match_no: str
    support_match_guest: str
    support_label_message: str
    support_topics: dict[str, str]
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
    support_subject="[تبصرة] {topic}",
    support_label_topic="الموضوع",
    support_label_name="الاسم",
    support_label_email="البريد",
    support_label_match="تطابق بريد الحساب",
    support_match_yes="نعم",
    support_match_no="لا",
    support_match_guest="غير مسجّل الدخول",
    support_label_message="الرسالة",
    support_topics={
        "account": "الحساب",
        "privacy": "الخصوصية",
        "bug": "مشكلة تقنية",
        "content": "المحتوى",
        "suggestion": "اقتراح",
        "other": "أخرى",
    },
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


def messages_for(language: str | None = None, *, settings: Settings | None = None) -> Messages:
    """
    Return the catalog of `language`.

    The settings decide: `language` is used when it is one of SUPPORTED_LANGUAGES, else
    DEFAULT_LANGUAGE is. A language with no catalog yet falls back to Arabic, the one
    every text exists in. Without `settings` the process's own are read.
    """
    settings = settings or get_settings()
    wanted = language if language in settings.supported_languages else settings.default_language
    return CATALOGS.get(wanted, ARABIC)


# ─── Insights: labels, disclosure and statuses shown with every result ───

# v2 §12: shown in the chat and on every result.
AI_DISCLOSURE = "تبصرة أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا عالمًا"
# v2 §4 and tajriba §2: on every prepared, reviewed example.
PREPARED_EXAMPLE = "مثال موثّق مُعدّ"
# On every insight of the development simulation (SCAN_ENGINE=demo).
DEMO_ENGINE = "محاكاة معلنة للتطوير: ليست تحليلًا حيًا لصورتك"
# Decision 18: a hadith without an editor's ruling is not shown.
HADITH_AWAITS_VERIFICATION = (
    "الحديث المرتبط بهذه البصيرة بانتظار التحقق من حكمه في الدرر؛ تُعرض الآية وحدها حتى يُسجَّل الحكم."
)

RELATION_LABELS = {
    "direct": "صلة مباشرة",
    "action_based": "صلة بالفعل",
    "close_conceptual": "صلة مفهومية",
    "opposite": "من المعنى المقابل",
    "thematic_reminder": "تذكير عام",
}
EXPLANATION_LABELS = {
    "seen": "ما ظهر",
    "value": "القيمة",
    "quran": "ماذا تضيف الآية",
    "sunnah": "ماذا يضيف الحديث",
    "life": "كيف يتصل بالحياة",
}
# The fixed tags that keep quotation apart from the platform's words (v2 §12).
QURAN_TAG = "القرآن"
SUNNAH_TAG = "السنة"
EXPLANATION_TAG = "شرح تبصرة"
# v2 §14: a step is «من السنة» only with a direct grounding; otherwise it is a suggestion.
STEP_FROM_SUNNAH = "من السنة"
STEP_SUGGESTION = "اقتراح عملي"

STAGE_LABELS = {
    "understanding": "أفهم المشهد",
    "searching": "أبحث عن الأدلة",
    "verifying": "أتحقق من المصادر",
    "composing": "أعدّ بصيرتك",
}

# ─── The small step: a declaration, never a proof or a reward (tajriba §9) ───

ACTION_DONE = "نفّذته"
ACTION_LATER = "سأفعله لاحقًا"
ACTION_DONE_MEANS = "تصريح منك بما فعلت؛ لا تتحقق منه تبصرة ولا تحتسب له أجرًا."
ACTION_LATER_MEANS = "حُفظ تأجيلك؛ لا يُحتسب إنجازًا ولا يُنقص من شيء."

# ─── «تمّ» and what follows it (v2 §4 and §15) ───

OPTION_OPEN_WORLD = "افتح عالمي"
OPTION_NEW_SCAN = "صوّر مشهدًا آخر"
OPTION_SHARE = "شارك البصيرة"
SUGGEST_ACCOUNT = "هل تحفظ ما تعلّمته لنواصل من هنا؟"
CONTINUE_AS_GUEST = "أتابع كضيف"

# ─── Chat (v2 §14) ───

CHAT_LIMIT_REACHED = "اكتمل النقاش حول هذه البصيرة"
CHAT_NEEDS_NEW_SEARCH = (
    "طلب نص آخر يحتاج بحثًا جديدًا في المصادر وتحققًا منها، ولا أذكر نصًا من الذاكرة."
    " صوّر المشهد من جديد أو وضّح ما تقصد لنبحث لك."
)
# Level د: general information first (the answer), then this referral.
CHAT_REFERRAL = (
    "هذه مسألة تخصّ حالتك، والحكم فيها لمن يعرف تفاصيلها:"
    " اسأل أهل العلم المؤهلين أو جهة الفتوى المعتمدة في بلدك."
)

# ─── The world and its treasures (v2 §16 and §17) ───

TREASURE_KIND_LABELS = {
    "alternative": "نص آخر متحقَّق بالوزن نفسه",
    "deeper": "معنى أعمق في الطريق نفسه",
}
RELATION_THREAD_QUESTION = "كيف ترتبطان؟"
WORLD_RELATION_REASONS = {
    "same_scene": "من المشهد نفسه",
    "prerequisite": "خطوة تمهّد للأخرى في المسار",
}

# ─── Practice, never piety (decision 27) ───

PRACTICE_DISCLAIMER = (
    "هذه علامات على التمرين والمواظبة لا على الإيمان ولا على القبول؛ تُحتسب من أفعالك المسجلة فقط."
)
# (id, title, hint), lowest first; the thresholds live in src/services/practice.py.
PRACTICE_RANKS = (
    ("nazir", "ناظر", "بدأت تنظر."),
    ("mutaammil", "متأمّل", "ثلاثة مشاهد فأكثر."),
    ("mustabsir", "مستبصر", "عشرة مشاهد فأكثر."),
    ("basir", "بصير بالتمرين", "ثلاثون مشهدًا فأكثر."),
)
DAILY_QUEST_TITLE = "بصيرة اليوم"
DAILY_QUEST_STEPS = {
    "look": "انظر في مشهد واحد اليوم",
    "complete": "أتمّ بصيرة واحدة اليوم",
}
# id: (title, description); the rules live in src/services/practice.py.
BADGES = {
    "first-look": ("أول نظرة", "أكملت أول مشهد عبر تبصرة."),
    "seven-looks": ("سبع نظرات", "سبعة مشاهد اكتملت حتى آخر مرحلة."),
    "thirty-looks": ("ثلاثون نظرة", "ثلاثون مشهدًا؛ صار النظر عادة."),
    "both-insights": ("البصيرتان", "أتممت بصيرتي المطر والغرس معًا."),
    "first-action": ("فعل صغير", "أقررت بفعل صغير بعد بصيرة."),
    "first-place": ("أول بقعة", "انقشع الضباب عن أول موضع في عالمك."),
    "first-treasure": ("أول كنز", "كشفت أول كنز مخبوء في عالمك."),
    "ten-concepts": ("عشرة معانٍ", "عشرة معانٍ مختلفة أضاءت في سمائك."),
    "asked": ("سائل", "سألت عمّا أمامك في الحوار."),
    "streak-3": ("ثلاثة أيام", "نظرت ثلاثة أيام متتالية."),
    "streak-7": ("أسبوع من النظر", "سبعة أيام متتالية من النظر."),
    "daily-quest": ("مهمة اليوم", "أتممت بصيرة اليوم."),
}
