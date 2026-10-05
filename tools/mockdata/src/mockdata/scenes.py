"""
A filename becomes labels and one Arabic line, from a small reviewed word map (no model).

Words not in the map are dropped. The Arabic line is a plain noun phrase about what the file name
says; it states no belief, no identity and no verse.
"""

from __future__ import annotations

from mockdata.catalogue import words
from mockdata.output import Scene

# English word -> (label, Arabic noun). What the picture is of.
SUBJECTS: dict[str, tuple[str, str]] = {
    "cat": ("cat", "قطة"), "kitten": ("cat", "قطة صغيرة"), "kitty": ("cat", "قطة"),
    "feline": ("cat", "قطة"), "tabby": ("cat", "قطة"), "tomcat": ("cat", "قط"),
    "mieze": ("cat", "قطة"), "mietze": ("cat", "قطة"), "siamese": ("cat", "قطة"),
    "dog": ("dog", "كلب"), "puppy": ("dog", "جرو"), "horse": ("horse", "حصان"),
    "pony": ("horse", "مهر"), "mare": ("horse", "فرس"), "camel": ("camel", "جمل"),
    "goat": ("goat", "ماعز"), "sheep": ("sheep", "أغنام"), "cow": ("cow", "بقرة"),
    "elephant": ("elephant", "فيل"), "zebra": ("zebra", "حمار وحشي"), "tiger": ("tiger", "نمر"),
    "lion": ("lion", "أسد"), "bear": ("bear", "دب"), "bee": ("bee", "نحلة"),
    "duck": ("duck", "بط"), "swan": ("swan", "بجعة"), "bird": ("bird", "طائر"),
    "parrot": ("parrot", "ببغاء"), "seagull": ("seagull", "نورس"), "frog": ("frog", "ضفدع"),
    "lizard": ("lizard", "سحلية"), "iguana": ("iguana", "إغوانا"), "meerkat": ("meerkat", "سرقاط"),
    "yak": ("yak", "ياك"), "mackerel": ("fish", "سمك"), "animal": ("animal", "حيوان"),
    "pet": ("pet", "حيوان أليف"),
    "flower": ("flower", "زهرة"), "blossom": ("flower", "أزهار"), "rose": ("rose", "وردة"),
    "tulip": ("tulip", "توليب"), "sunflower": ("sunflower", "عباد الشمس"),
    "daisy": ("daisy", "أقحوان"), "lotus": ("lotus", "لوتس"), "lily": ("lily", "زنبق"),
    "lilium": ("lily", "زنبق"), "violet": ("violet", "بنفسج"), "aloe": ("aloe", "ألوفيرا"),
    "tree": ("tree", "شجرة"), "grass": ("grass", "عشب"),
    "food": ("food", "طعام"), "vegetable": ("vegetable", "خضار"), "fruit": ("fruit", "فاكهة"),
    "strawberry": ("strawberry", "فراولة"), "strawberrie": ("strawberry", "فراولة"),
    "garlic": ("garlic", "ثوم"), "onion": ("onion", "بصل"), "tomato": ("tomato", "طماطم"),
    "tomatoe": ("tomato", "طماطم"), "pepper": ("pepper", "فلفل"), "paprika": ("pepper", "فلفل"),
    "chili": ("pepper", "فلفل"), "chilli": ("pepper", "فلفل"), "carrot": ("carrot", "جزر"),
    "apple": ("apple", "تفاح"), "peache": ("peach", "خوخ"), "pineapple": ("pineapple", "أناناس"),
    "kiwi": ("kiwi", "كيوي"), "grape": ("grape", "عنب"), "potatoe": ("potato", "بطاطس"),
    "beet": ("beet", "شمندر"), "beetroot": ("beet", "شمندر"), "radish": ("radish", "فجل"),
    "radishe": ("radish", "فجل"), "broccoli": ("broccoli", "بروكلي"), "lettuce": ("lettuce", "خس"),
    "parsley": ("parsley", "بقدونس"), "salad": ("salad", "سلطة"), "bread": ("bread", "خبز"),
    "honey": ("honey", "عسل"), "cheese": ("cheese", "جبن"), "pizza": ("pizza", "بيتزا"),
    "spaghetti": ("pasta", "معكرونة"), "lasagne": ("pasta", "معكرونة"),
    "sushi": ("sushi", "سوشي"), "dessert": ("dessert", "حلوى"), "sweet": ("sweets", "حلويات"),
    "candy": ("sweets", "حلويات"), "chocolate": ("chocolate", "شوكولاتة"),
    "wheat": ("wheat", "قمح"), "cereal": ("cereal", "حبوب"), "grain": ("grain", "حبوب"),
    "pumpkin": ("pumpkin", "يقطين"), "bean": ("bean", "فاصولياء"), "herb": ("herb", "أعشاب"),
    "spice": ("spice", "توابل"), "lime": ("lime", "ليمون"),
    "skyscraper": ("skyscraper", "ناطحات سحاب"), "cityscape": ("city", "أفق المدينة"),
    "bridge": ("bridge", "جسر"), "tower": ("tower", "برج"), "building": ("building", "مبنى"),
    "house": ("house", "منزل"), "mosque": ("mosque", "مسجد"), "minaret": ("minaret", "مئذنة"),
    "palace": ("palace", "قصر"), "castle": ("castle", "قلعة"), "train": ("train", "قطار"),
    "tram": ("tram", "ترام"), "car": ("car", "سيارة"), "bike": ("bicycle", "دراجة"),
    "bicycle": ("bicycle", "دراجة"), "ship": ("ship", "سفينة"), "ferry": ("ship", "عبارة"),
    "plane": ("plane", "طائرة"), "stadium": ("stadium", "ملعب"), "hotel": ("hotel", "فندق"),
    "restaurant": ("restaurant", "مطعم"), "kitchen": ("kitchen", "مطبخ"), "book": ("book", "كتاب"),
    "bookcase": ("bookcase", "مكتبة"), "chair": ("chair", "كرسي"),
    "sunset": ("sunset", "غروب الشمس"), "cloud": ("cloud", "غيوم"), "snow": ("snow", "ثلج"),
    "rainbow": ("rainbow", "قوس قزح"), "rock": ("rock", "صخرة"), "canyon": ("canyon", "وادٍ عميق"),
}  # fmt: skip

# English word -> (label, Arabic place, used after "في"). Where it is.
PLACES: dict[str, tuple[str, str]] = {
    "city": ("city", "المدينة"), "street": ("street", "الشارع"), "market": ("market", "السوق"),
    "station": ("station", "المحطة"), "garden": ("garden", "الحديقة"), "park": ("park", "المتنزه"),
    "forest": ("forest", "الغابة"), "lake": ("lake", "البحيرة"), "beach": ("beach", "الشاطئ"),
    "desert": ("desert", "الصحراء"), "mountain": ("mountain", "الجبال"),
    "river": ("river", "النهر"), "field": ("field", "الحقل"), "meadow": ("meadow", "المرج"),
    "pond": ("pond", "البركة"), "stream": ("stream", "الجدول"), "sky": ("sky", "السماء"),
    "night": ("night", "الليل"),
}  # fmt: skip

CATEGORY_LINES: dict[str, str] = {
    "animal": "حيوان", "bird": "طائر", "cat": "قطة", "dog": "كلب", "flower": "زهرة",
    "food": "طعام", "nature": "منظر من الطبيعة", "city": "منظر من المدينة",
    "travel": "منظر من السفر", "interior": "مكان من الداخل", "education": "أدوات التعلم",
    "transportation": "وسيلة نقل",
}  # fmt: skip
MAX_SUBJECTS = 2


def _lookup[T](table: dict[str, T], word: str) -> T | None:
    """The word, or its singular (`tomatoes` -> `tomatoe` is in the map on purpose)."""
    return (
        table.get(word) or table.get(word.removesuffix("s")) or table.get(word.removesuffix("es"))
    )


def describe(filename: str, category: str = "") -> Scene:
    """Labels (known words only, in filename order) and an Arabic line."""
    subjects: list[tuple[str, str]] = []
    place: tuple[str, str] | None = None
    for word in words(filename):
        if (found := _lookup(SUBJECTS, word)) and found[0] not in {s[0] for s in subjects}:
            subjects.append(found)
        elif (spot := _lookup(PLACES, word)) and place is None:
            place = spot
    picked = subjects[:MAX_SUBJECTS]
    labels = list(dict.fromkeys([label for label, _ in picked] + ([place[0]] if place else [])))
    nouns = list(dict.fromkeys(noun for _, noun in picked))
    if nouns and place:
        line = f"{' و'.join(nouns)} في {place[1]}"
    elif nouns:
        line = " و".join(nouns)
    elif place:
        line = f"منظر من {place[1]}"
    else:
        line = CATEGORY_LINES.get(category, "منظر")
        labels = [category] if category else []
    return Scene(labels=labels, ar=line)
