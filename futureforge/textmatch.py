"""Turn what a student types into the tag vocabulary the engine scores on.

The matching engine only understands tags from VOCABULARIES -- a student typing
"i like helping sick people" has to become ["health", "helping_people"] before
rank_careers can do anything with it. This module is that translation layer, and
it is pure stdlib so the wizard stays offline.

Each tag carries a keyword list, matched in three tiers so a student never has to
phrase things our way: exact whole words first (so "art" does not fire on
"start"), then stems ("fixing" -> "fix"), then fuzzy similarity for typos
("buisness" -> business). If nothing clears the confident bar, the closest tags
are taken anyway -- the wizard should always pick something up rather than tell a
student their answer wasn't understood.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from .dataset import VOCABULARIES

# tag -> the words a student is likely to actually type for it.
KEYWORDS: Dict[str, List[str]] = {
    # ---------------------------------------------------------- interests
    "technology": ["computer", "computers", "tech", "technology", "coding", "code",
                   "programming", "software", "it", "cyber", "games", "gaming", "ai"],
    "building": ["building", "build", "fixing", "fix", "repair", "construction",
                 "carpentry", "woodworking", "hands", "making", "assemble"],
    "machines": ["machines", "machine", "engines", "engine", "cars", "car", "mechanic",
                 "tools", "motor", "automotive", "welding", "equipment"],
    "science": ["science", "experiments", "experiment", "lab", "research", "chemistry",
                "physics", "scientific", "biology"],
    "health": ["medicine", "medical", "health", "healthcare", "doctor", "nurse", "nursing",
               "body", "anatomy", "hospital", "patients", "sick", "dental", "dentist"],
    "helping_people": ["helping", "help", "people", "caring", "care", "support",
                       "counseling", "social work", "others"],
    "teaching": ["teaching", "teach", "explaining", "explain", "tutor", "school",
                 "educator", "coach", "mentor", "kids", "children"],
    "animals": ["animals", "animal", "pets", "pet", "dogs", "cats", "vet",
                "veterinary", "wildlife", "horses"],
    "outdoors": ["outdoors", "outdoor", "outside", "nature", "hiking", "fresh air",
                 "field", "forest"],
    "environment": ["environment", "environmental", "nature", "climate", "sustainability",
                    "conservation", "ecology", "green", "earth"],
    "art_design": ["art", "design", "drawing", "draw", "painting", "paint", "creative",
                   "graphic", "illustration", "photography", "fashion"],
    "performing": ["music", "acting", "act", "performing", "perform", "theater", "theatre",
                   "dance", "singing", "sing", "band", "drama"],
    "writing": ["writing", "write", "storytelling", "stories", "journalism", "author",
                "books", "reading", "english"],
    "business": ["business", "running things", "management", "manager", "entrepreneur",
                 "company", "startup", "marketing", "sales"],
    "money_markets": ["money", "investing", "invest", "markets", "finance", "financial",
                      "stocks", "banking", "accounting", "economics"],
    "data_numbers": ["numbers", "data", "puzzles", "puzzle", "math", "statistics", "stats",
                     "analytics", "analysis", "problem solving", "logic"],
    "law_order": ["law", "justice", "public safety", "police", "legal", "lawyer",
                  "firefighter", "court", "crime", "security", "military"],
    "food": ["food", "cooking", "cook", "baking", "bake", "chef", "culinary",
             "restaurant", "kitchen"],
    "travel": ["travel", "traveling", "travelling", "moving around", "flying", "trips",
               "driving", "aviation", "pilot"],
    "sports": ["sports", "sport", "fitness", "athletic", "athletics", "gym", "exercise",
               "training", "coaching"],
    # ----------------------------------------------------------- subjects
    "math": ["math", "maths", "mathematics", "algebra", "calculus", "geometry",
             "trigonometry", "statistics"],
    "biology": ["biology", "bio", "life science", "anatomy", "botany"],
    "chemistry": ["chemistry", "chem", "organic"],
    "physics": ["physics", "mechanics"],
    "computer_science": ["computer science", "cs", "coding", "code", "programming",
                         "computing", "software", "computers"],
    "english": ["english", "language arts", "literature", "writing", "reading",
                "composition"],
    "history": ["history", "social studies", "government", "civics", "politics"],
    "geography": ["geography", "geo", "maps", "earth science"],
    "art": ["art", "drawing", "painting", "ceramics", "sculpture", "studio art"],
    "music": ["music", "band", "orchestra", "choir", "guitar", "piano"],
    "foreign_language": ["foreign language", "spanish", "french", "german", "chinese",
                         "languages", "latin", "japanese"],
    "shop_tech": ["shop", "tech ed", "woodshop", "metal shop", "auto shop", "welding",
                  "industrial arts", "engineering"],
    "business_econ": ["business", "economics", "econ", "accounting", "marketing",
                      "entrepreneurship"],
    "psychology": ["psychology", "psych", "sociology", "human behavior", "behavior"],
    "phys_ed": ["physical education", "phys ed", "gym", "pe class", "health class",
                "sports medicine"],
    # -------------------------------------------------------- work style
    "team": ["team", "teams", "together", "group", "collaborate", "collaboration",
             "coworkers", "colleagues"],
    "independent": ["own", "alone", "independent", "independently", "solo", "myself",
                    "by myself"],
    "hands_on": ["hands on", "hands-on", "physical", "moving", "active", "building",
                 "manual", "labor", "practical"],
    "desk_work": ["desk", "office", "computer", "sitting", "sit", "screen"],
    "outdoors_env": ["outdoors", "outdoor", "outside", "job site", "site", "field",
                     "construction site"],
    "travel_frequent": ["travel", "traveling", "travelling", "moving around", "road",
                        "different places", "on the go"],
    "structured": ["routine", "structured", "procedures", "clear", "organized",
                   "predictable", "steps"],
    "flexible_hours": ["flexible", "flexibility", "own hours", "schedule", "part time"],
    "fast_paced": ["fast paced", "fast-paced", "fast", "busy", "pressure", "high pressure",
                   "adrenaline", "emergency", "exciting"],
    "quiet_focus": ["quiet", "focused", "focus", "calm", "concentration", "peaceful"],
    "leadership": ["leading", "lead", "leader", "leadership", "manage", "managing",
                   "in charge", "boss", "supervise"],
    "customer_facing": ["talking", "talk", "people", "customers", "clients", "social",
                        "communicating", "conversation"],
    "remote_possible": ["remote", "remotely", "from home", "work from home", "online",
                        "anywhere"],
    "shift_work": ["nights", "night", "weekends", "shifts", "shift", "overnight",
                   "late"],
    # ------------------------------------------------------------ values
    "high_pay": ["high pay", "pay", "money", "salary", "rich", "well paid", "wealthy",
                 "income", "lucrative"],
    "job_security": ["security", "secure", "stable", "stability", "steady", "reliable",
                     "always needed", "safe job"],
    "work_life_balance": ["work life balance", "balance", "free time", "time off",
                          "family time", "not overworked", "hours"],
    "helping_others": ["helping others", "helping", "help", "making a difference",
                       "give back", "impact", "care for", "serve"],
    "creativity": ["creative", "creativity", "express", "expression", "imagination",
                   "original", "design"],
    "autonomy": ["own boss", "autonomy", "independence", "independent", "freedom",
                 "control", "decide"],
    "prestige": ["respect", "prestige", "respected", "status", "admired", "proud",
                 "reputation"],
    "short_training": ["quickly", "quick", "fast", "start earning", "soon", "short",
                       "no college", "less school", "right away"],
    "entrepreneurship": ["own business", "business", "entrepreneur", "startup",
                         "self employed", "my own company"],
    "variety": ["variety", "different", "not the same", "changes", "varied", "new things",
                "never boring"],
    "stay_local": ["near home", "local", "stay", "close to home", "hometown", "family",
                   "nearby"],
    "making_things": ["making something", "make things", "build", "create", "tangible",
                      "real", "with my hands", "produce"],
    "public_service": ["community", "public service", "serving", "serve", "civic",
                       "give back", "society"],
    "teamwork_culture": ["close knit", "close-knit", "team culture", "friends",
                         "friendly", "belonging", "supportive team"],
}


# The concrete nouns students actually type. The lists above are mostly category
# words ("music", "sports"); these are the specifics someone writes when asked what
# they enjoy -- instruments, school clubs, job titles, brand-name hobbies.
EXTRA: Dict[str, List[str]] = {
    # ---------------------------------------------------------- interests
    "technology": ["robotics", "robots", "robot", "app", "apps", "website", "websites",
                   "web", "hacking", "video games", "minecraft", "roblox", "discord",
                   "pc", "laptop", "phones", "electronics", "circuits", "arduino",
                   "python", "java", "javascript", "html", "3d printing"],
    "building": ["legos", "lego", "woodwork", "furniture", "houses", "renovating",
                 "renovation", "diy", "crafts", "models", "framing", "drywall",
                 "handy", "put things together", "take things apart"],
    "machines": ["motorcycle", "motorcycles", "truck", "trucks", "tractor", "airplane",
                 "planes", "hvac", "plumbing", "electrician", "electrical", "wiring",
                 "machining", "forklift", "diesel", "small engines"],
    "science": ["astronomy", "space", "stars", "planets", "geology", "microscope",
                "dna", "genetics", "molecules", "rocks", "weather", "marine biology"],
    "health": ["pharmacy", "therapy", "physical therapy", "surgeon", "surgery", "emt",
               "paramedic", "xray", "x ray", "radiology", "mental health", "ultrasound",
               "vaccines", "first aid", "cna", "hospice", "midwife", "optometry"],
    "helping_people": ["volunteer", "volunteering", "community service", "counselor",
                       "nonprofit", "charity", "elderly", "disabled", "shelter",
                       "listening", "advice", "therapist"],
    "teaching": ["teacher", "professor", "daycare", "preschool", "instructor",
                 "training people", "babysitting", "camp counselor", "tutoring"],
    "animals": ["zoo", "farm", "farming", "marine", "birds", "reptiles", "shelter",
                "ranch", "grooming", "training dogs", "aquarium", "livestock"],
    "outdoors": ["camping", "fishing", "hunting", "gardening", "hiking", "beach",
                 "mountains", "park", "trails", "kayaking", "surfing", "skiing"],
    "environment": ["recycling", "renewable", "solar", "wind power", "pollution",
                    "ocean", "forestry", "sustainable", "global warming"],
    "art_design": ["photography", "photos", "photo", "animation", "animating",
                   "digital art", "interior design", "architecture", "tattoo",
                   "makeup", "ceramics", "sculpting", "video editing", "film",
                   "editing videos", "procreate", "photoshop", "sketching"],
    "performing": ["piano", "guitar", "violin", "drums", "bass", "cello", "flute",
                   "trumpet", "saxophone", "ukulele", "choir", "orchestra", "concerts",
                   "stage", "musicals", "movies", "tiktok", "youtube", "dj",
                   "rapping", "producing", "songwriting", "instrument", "instruments"],
    "writing": ["poetry", "poems", "blog", "blogging", "novels", "screenwriting",
                "fanfiction", "essays", "editing", "debate"],
    "business": ["retail", "store", "real estate", "hr", "consulting", "logistics",
                 "supply chain", "operations", "franchise", "reselling"],
    "money_markets": ["crypto", "trading", "budgeting", "taxes", "wall street",
                      "bookkeeping", "insurance", "loans", "mortgage"],
    "data_numbers": ["excel", "spreadsheets", "patterns", "chess", "sudoku",
                     "rubiks cube", "coding puzzles", "statistics", "graphs"],
    "law_order": ["paralegal", "detective", "fbi", "corrections", "firefighting",
                  "army", "navy", "marines", "air force", "dispatcher", "attorney",
                  "cop", "sheriff", "border patrol"],
    "food": ["barista", "coffee", "pastry", "grill", "catering", "nutrition",
             "baking bread", "line cook", "food truck", "bartending"],
    "travel": ["airline", "flight attendant", "cruise", "trucking", "delivery",
               "rideshare", "tourism", "hotels", "different countries"],
    "sports": ["soccer", "basketball", "football", "baseball", "softball", "swimming",
               "track", "wrestling", "volleyball", "tennis", "hockey", "lacrosse",
               "weightlifting", "personal trainer", "athlete", "lifting", "running"],
    # ----------------------------------------------------------- subjects
    "music": ["piano", "guitar", "violin", "drums", "choir", "orchestra", "jazz band",
              "marching band", "music theory"],
    "art": ["photography", "ceramics", "digital art", "animation", "graphic design",
            "ap art", "studio"],
    "computer_science": ["robotics", "ap csa", "ap csp", "java", "python",
                         "javascript", "html", "web design", "game design"],
    "math": ["precalc", "pre calc", "ap calc", "algebra 2", "discrete", "stats class"],
    "biology": ["ap bio", "environmental science", "anatomy and physiology",
                "human biology"],
    "chemistry": ["ap chem", "organic chemistry", "biochem"],
    "physics": ["ap physics", "engineering class", "mechanics"],
    "english": ["lit", "ap lang", "ap lit", "creative writing", "literature class"],
    "history": ["ap world", "ap us", "government", "civics class", "world history"],
    "shop_tech": ["drafting", "cad", "autocad", "automotive class", "metals",
                  "construction class", "engineering", "robotics", "welding class"],
    "phys_ed": ["weight training", "health class", "sports med"],
    "psychology": ["ap psych", "child development", "sociology class"],
    "business_econ": ["ap econ", "personal finance", "deca", "marketing class"],
    "foreign_language": ["asl", "sign language", "italian", "korean", "arabic",
                         "portuguese", "russian"],
    # -------------------------------------------------------- work style
    "team": ["partners", "crew", "squad", "with others", "group projects",
             "coworkers", "people around me"],
    "independent": ["by myself", "on my own", "solo", "left alone", "no one bothering"],
    "hands_on": ["with my hands", "on my feet", "moving around", "tools", "physical",
                 "not sitting", "active"],
    "desk_work": ["cubicle", "laptop", "screens", "sitting down", "office job"],
    "outdoors_env": ["job site", "field work", "construction site", "outside all day"],
    "travel_frequent": ["different places", "on the road", "new cities", "not stuck"],
    "structured": ["same schedule", "checklist", "know what to expect", "consistent"],
    "flexible_hours": ["own schedule", "freelance", "part time", "my own hours",
                       "set my own"],
    "fast_paced": ["high energy", "never boring", "on my toes", "intense", "rush"],
    "quiet_focus": ["low stress", "peaceful", "calm", "concentrate", "not loud"],
    "leadership": ["run a team", "supervisor", "be in charge", "manage people",
                   "own crew"],
    "customer_facing": ["people person", "customers", "clients", "communication",
                        "meeting new people", "chatting"],
    "remote_possible": ["from home", "hybrid", "work anywhere", "wfh"],
    "shift_work": ["overnight", "early mornings", "graveyard", "on call",
                   "night shift"],
    # ------------------------------------------------------------ values
    "high_pay": ["good money", "well paying", "six figures", "make bank", "paid well",
                 "financially stable", "afford"],
    "job_security": ["always hiring", "in demand", "recession proof", "wont be replaced",
                     "reliable job", "never out of work"],
    "work_life_balance": ["weekends off", "not stressed", "9 to 5", "time for family",
                          "not working all the time", "vacation"],
    "helping_others": ["make a difference", "impact", "give back", "help people",
                       "take care of", "change lives"],
    "creativity": ["express myself", "original ideas", "imagination", "artistic",
                   "come up with"],
    "autonomy": ["my own boss", "freedom", "my own decisions", "nobody over me",
                 "independence"],
    "prestige": ["respected", "look up to", "proud", "title", "status", "impressive"],
    "short_training": ["no college", "start working", "right away", "short program",
                       "cheap", "get out fast", "two year"],
    "entrepreneurship": ["own business", "start a company", "self employed",
                         "be my own boss", "own shop"],
    "variety": ["different every day", "not boring", "new things", "mix it up"],
    "stay_local": ["close to family", "hometown", "stay here", "near my family"],
    "making_things": ["make things", "see the result", "tangible", "something real",
                      "finished product", "with my hands"],
    "public_service": ["serve", "give back", "my city", "my country", "public"],
    "teamwork_culture": ["good team", "friends at work", "culture", "supportive",
                         "people i like"],
}

for _tag, _words in EXTRA.items():
    KEYWORDS.setdefault(_tag, [])
    KEYWORDS[_tag] = KEYWORDS[_tag] + _words

# Words that carry no signal -- excluded from the always-match fallback so a
# sentence of pure filler doesn't drag in a random tag.
STOPWORDS = frozenset("""
a an and are as at be been being but by can could do does doing dont for from
get got had has have having he her him his how i id if ill im in into is it its
ive just like ll me might must my no not of on or our out re should so some
such than that the their them then there these they thing things this those to
up us very want wanna was we well were what when where which while who why will
with would you your youre
""".split())

_SUFFIXES = ("ing", "ed", "es", "s")


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", text.lower())


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if len(word) > 4 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _ngrams(tokens: List[str], n: int) -> List[str]:
    return [" ".join(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def _keyword_score(keyword: str, text: str, tokens: List[str],
                   stems: List[str]) -> float:
    """How strongly one keyword is present, 0..1."""
    kw = _normalize(keyword).strip()
    if not kw:
        return 0.0
    if " " in kw:
        if kw in text:
            return 1.0
        parts = kw.split()
        # every word of the phrase present somewhere still counts, loosely
        if all(p in tokens for p in parts):
            return 0.93
        candidates = _ngrams(tokens, len(parts))
        return max([_ratio(kw, c) for c in candidates], default=0.0)
    if kw in tokens:
        return 1.0
    kw_stem = _stem(kw)
    if kw_stem in stems:
        return 0.94
    if len(kw) >= 5:
        # typos and inflections the stemmer misses ("enginering", "buisness")
        return max([_ratio(kw, t) for t in tokens if len(t) >= 4], default=0.0)
    return 0.0


def score_tags(dimension: str, text: str) -> List[Tuple[str, float]]:
    """Every tag in the dimension, scored against the text, best first."""
    haystack = _normalize(text)
    tokens = [t for t in haystack.split() if t]
    stems = [_stem(t) for t in tokens]
    content = [t for t in tokens if t not in STOPWORDS]

    scored: List[Tuple[str, float]] = []
    for tag, display in VOCABULARIES[dimension].items():
        words = KEYWORDS.get(tag, []) + [display]
        best = max(
            (_keyword_score(w, haystack, tokens, stems) for w in words),
            default=0.0,
        )
        scored.append((tag, best))
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    # nothing to work with at all -- an empty box or pure filler
    if not content:
        return []
    return scored


STRONG = 0.88   # confident match
LOOSE = 0.62    # best-effort fallback so something is always picked up


def extract(dimension: str, text: str) -> List[str]:
    """Tags the student's text is about.

    Always returns something when the text has any real content: confident
    matches if there are any, otherwise the closest tag it can find.
    """
    if not text or not text.strip():
        return []
    scored = score_tags(dimension, text)
    if not scored:
        return []
    strong = [tag for tag, score in scored if score >= STRONG]
    if strong:
        return strong
    loose = [tag for tag, score in scored if score >= LOOSE]
    return loose[:2]


def suggestions(dimension: str, limit: int = 6) -> List[str]:
    """A few example answers to show under the box, so the student isn't stuck."""
    labels = list(VOCABULARIES[dimension].values())
    return labels[:limit]
