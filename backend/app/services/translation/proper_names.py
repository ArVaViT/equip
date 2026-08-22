# ruff: noqa: RUF001, RUF002, RUF003
# The table below is Cyrillic and Latin side by side by definition — the
# whole point is that «Матфий» and "Matthias" are one row and «Матфей»
# and "Matthäus" are another.
"""One name swapped for another name.

The defect
----------

Three native editors read the live catalogue and found the translator
putting a *different* biblical person or place where the source named
one:

===============================  ==========================  ===========
source                           translation                 what it is
===============================  ==========================  ===========
«Крисп» (Acts 18:8)              German *Sosthenes*          another man
«Матфий»                         German *Matthäus*           another
                                                             apostle
«Филипп» the evangelist          German *Philippi*           the city
«Тавифа (по-гречески Серна)»     Ukrainian «Дорка»           the Greek
                                                             name, so the
                                                             sentence
                                                             contradicts
                                                             itself
«Господь»                        English *the Gospel*        not a person
===============================  ==========================  ===========

Every one of those passes ``validation.py`` without a murmur. The markup
matches, the markers came back, the length is right, the language is the
language asked for, the numbers survived. A name is a word, and a word
swapped for another word is exactly the shape that module says it is
blind to.

Why a table, and not a better prompt
------------------------------------

``prompt.py`` already carries rule 5 — "Keep proper nouns transliterated
to their established form in {tgt}" — and it did not prevent a single
one of the rows above. It is also measured that a German terminology
error entered at pipeline generation 7 and survived four complete
re-translations unchanged. Instruction is not the lever here. What works
in this codebase is a table the pipeline consults and a check that reads
the answer back, which is what ``glossary.py`` is and what this is.

What the check asks, and what it deliberately does not
------------------------------------------------------

    *The source names a known biblical person or place, and the
    translation names a different known one.*

Both halves are load-bearing, and the narrowness is the whole safety
argument:

**A transliteration is not a substitution.** «Пётр» → *Petrus* →
«Петро» is three spellings of one man and must never be flagged. So a
name counts as *present* in the translation on the flimsiest evidence —
an exact form, an inflection of one, or merely a word that sounds like
the source name under ``term_memory``'s skeleton comparison, which is
the same measured machinery that already tells «Филиппы»/"Philippi"
apart from «Марк»/«Мария».

**Both halves of the accusation are made on exact evidence.** The
source is credited with naming somebody, and the translation with
naming somebody else, only where a whole word *is* a form this table
spells out. Read loosely, the source side invents names out of ordinary
words: measured on the live catalogue it read «Деяния» as Derbe,
«Первая» as Rome and «Правила» as Job, and every one became a flag on
correct prose. Read loosely, the target side is worse — every noun is
capitalised in German.

So the four questions are asked in two directions on purpose. The two
that accuse are strict; the two that exonerate — *did the translation
keep this name*, *had the source already named this one* — are as loose
as ``term_memory`` will go. It is easy to be believed to have kept a
name and hard to be believed to have introduced one, and nothing is
reported unless both happened in the same row.

What this cannot see, stated plainly
------------------------------------

* **«Вавилон» → *Babylon*.** Russian spells Babel and Babylon the same
  way, so the source word names both rows at once and the translation
  names one of them — nothing new appeared. Telling Genesis 11 from
  Revelation 17 needs the surrounding chapter, which is not something a
  name table holds.
* **«Клавдий Лисий» → «Лій», «Лісій», «Лисий».** The name was mangled,
  not replaced. None of those is another person; they are three
  spellings, one of which happens to read as the adjective *bald*. This
  check is about substitution and is silent here by construction — and
  since 08.2026 it does not have to be the last word: two of those
  three are spellings Ukrainian does not print, which is
  ``person_names.foreign_person_names``'s question and not this one's.
  The same is true of «Стефан» → «Степан», the defect that made that
  sibling necessary: «Степан» is not a different person, it is this one
  misspelt as the ordinary Ukrainian given name, so everything below
  goes on reading it as Stephen and staying quiet.
* **«Красные ворота» → «Червоні ворота».** Ὡραία rendered as the
  colour. The wrong half is an adjective, and no different name
  appeared.
* **«Синай» → «Син».** The Ukrainian for "the Son" — a divine title,
  not a person or a place. Putting titles in the table was tried and
  measured: it takes the catalogue from 9 flags to 28, and the 19 extra
  are things like «Ной» → «Господь» and *Lord* → *David*. English
  writes the title as "Son", three letters, below the length at which a
  skeleton identifies anything — so it would read as missing from every
  English row that renders it perfectly.
* **«Господь» → *the Gospel*.** Same reason: neither word is a name.

Each of those wants a different check. Widening this one to reach them
means flagging "the name changed", and a name legitimately changes in
every row of a translated catalogue.

Coverage, and what it found
---------------------------

Built from the live catalogue rather than from a concordance: the
Russian and English sources behind all 6 077 live machine-translated
rows were read for capitalised words, and this table carries the
biblical persons and places among them, plus the rows that collide with
them («Матфей» is here because «Матфий» is, "Philippi" because «Филипп»
is) and the pairs that actually produced the failures above. It is not
a map of Scripture and must not become one: every row added widens the
surface on which a correct translation can be refused, and the rows
that earn their place are the ones that *collide*.

Run over those 6 077 rows on 2026-08-22 it flags nine, and all nine
were read. Every one is a real substitution — four of the five reported
failures it is built to see, the Ukrainian half of the Matthias defect
that nobody had reported, and two broken quiz options nobody had
reported either: «Книгу Иова» answered in English with *the book of
Isaiah*, which is the subject of the same question's *correct* answer,
and «К жителям Троады» answered with *To the inhabitants of Miletus*,
which is where the question already says the speech was given. No false
positives.

Inflection is written out where a collision depends on it. Russian and
Ukrainian decline, and the fallbacks that absorb declension elsewhere
cannot be trusted here — «Филиппах» (the city, locative) and «Филиппа»
(the man, genitive) are one edit apart, so both are spelled out and the
exact match settles it before any fuzzy tier is consulted. Two rules
follow from the measurement and are worth stating because a future
edit can break them silently: a form whose skeleton is shorter than
four characters is invisible (which is why Rome, *Rom*, «Рим», has no
row at all), and a form that shares a skeleton with an ordinary word of
its own language does not belong here (which is why «Иудеи» does not,
being "Jews" far more often than it is Judea).
"""

from __future__ import annotations

import re
from html import unescape
from typing import TYPE_CHECKING, Final

from app.core.sanitize import strip_tags
from app.schemas.locale import LOCALE_CODES, LanguageNotInTable
from app.services.bible.books import find_book
from app.services.bible.references import parse_references
from app.services.translation.term_memory import (
    _MIN_SIMILARITY,
    _MIN_SKELETON,
    _first_consonant,
    _similarity,
    _skeleton,
    _stem,
)

if TYPE_CHECKING:
    from app.schemas.locale import LocaleCode

# Each row is a name, not a person: «Тавифа» and «Дорка» are two rows
# because they are two names, and a translation that answers one with
# the other has said something the source did not — which is the defect,
# whoever the woman was.
#
# Columns are ``(key, ru, en, de, uk)`` — the key first, then one cell
# per language in the order of ``LOCALE_CODES``. A cell holds every form
# the check should recognise as *exactly* this name, separated by ``/``:
# the dictionary form always, and the inflections wherever another row
# is close enough that guessing at the ending would confuse the two.
_NAMES: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    # ---- The Twelve, and the two the model confused --------------------
    # «Матфий» and «Матфей» differ by one letter in Russian and by two in
    # German, and the model answered the first with the second. Every
    # oblique case of both is written out so the exact tier decides.
    ("matthias", "Матфий/Матфия/Матфию/Матфием/Матфие", "Matthias", "Matthias", "Матій/Матія/Матієм/Матфій"),
    ("matthew", "Матфей/Матфея/Матфею/Матфеем/Матфее", "Matthew", "Matthäus", "Матвій/Матвія/Матвієм"),
    ("peter", "Пётр/Петр/Петра/Петру/Петром/Петре", "Peter", "Petrus", "Петро/Петра/Петру/Петром"),
    ("andrew", "Андрей/Андрея/Андрею", "Andrew", "Andreas", "Андрій/Андрія"),
    ("james", "Иаков/Иакова/Иакову/Иаковом", "James", "Jakobus", "Яків/Якова/Якову"),
    ("john", "Иоанн/Иоанна/Иоанну/Иоанном/Иоанне", "John", "Johannes", "Іван/Івана/Івану/Іоан/Іоана"),
    ("philip", "Филипп/Филиппа/Филиппу/Филиппом", "Philip", "Philippus", "Филип/Филипа/Пилип/Пилипа"),
    ("bartholomew", "Варфоломей/Варфоломея", "Bartholomew", "Bartholomäus", "Варфоломій/Варфоломія"),
    ("thomas", "Фома/Фомы/Фоме/Фому", "Thomas", "Thomas", "Хома/Хоми/Фома"),
    ("thaddaeus", "Фаддей/Фаддея", "Thaddaeus", "Thaddäus", "Тадей/Тадея"),
    ("judas", "Иуда/Иуды/Иуде/Иуду/Иудой", "Judas", "Judas", "Юда/Юди/Іуда"),
    ("iscariot", "Искариот/Искариота", "Iscariot", "Iskariot", "Іскаріот/Іскаріота"),
    ("nathanael", "Нафанаил/Нафанаила", "Nathanael", "Nathanael", "Нафанаїл/Нафанаїла"),
    # ---- Acts: the people ----------------------------------------------
    ("paul", "Павел/Павла/Павлу/Павлом/Павле", "Paul", "Paulus", "Павло/Павла/Павлу/Павлом"),
    ("saul_of_tarsus", "Савл/Савла/Савлу/Савлом/Савле", "Saul", "Saulus/Saul", "Савл/Савла/Савлу/Савлом"),
    # The king, whom Russian spells differently from the apostle. Both
    # are "Saul" in English, so the English cell is shared and the two
    # rows go ambiguous there — which is the safe direction.
    ("king_saul", "Саул/Саула/Саулу", "Saul", "Saul", "Саул/Саула"),
    # The Ukrainian cell holds what Ukrainian prints. «Степан» used to
    # stand here as a third accepted form and does not: it is the
    # ordinary Ukrainian given name Stepan, and no Ukrainian Bible calls
    # the first martyr by it. It now lives in ``_NOT_PRINTED_HERE``,
    # which still resolves it to this row — see the note there.
    ("stephen", "Стефан/Стефана/Стефану/Стефаном", "Stephen", "Stephanus", "Стефан/Стефана/Стефану/Стефаном"),
    ("barnabas", "Варнава/Варнавы/Варнаве/Варнаву/Варнавой", "Barnabas", "Barnabas", "Варнава/Варнави/Варнаву"),
    ("silas", "Сила/Силы/Силе/Силу/Силой", "Silas", "Silas", "Сила/Сили/Силу"),
    ("timothy", "Тимофей/Тимофея/Тимофею", "Timothy", "Timotheus", "Тимофій/Тимофія"),
    ("titus", "Тит/Тита/Титу", "Titus", "Titus", "Тит/Тита"),
    ("luke", "Лука/Луки/Луке/Луку/Лукой", "Luke", "Lukas", "Лука/Луки/Луку"),
    ("mark", "Марк/Марка/Марку/Марком", "Mark", "Markus", "Марко/Марка/Марку"),
    ("mary", "Мария/Марии/Марию/Марией", "Mary", "Maria", "Марія/Марії/Марію"),
    ("ananias", "Анания/Анании/Ананию/Ананией", "Ananias", "Hananias", "Ананія/Ананії"),
    ("sapphira", "Сапфира/Сапфиры/Сапфире/Сапфиру", "Sapphira", "Saphira", "Сапфіра/Сапфіри"),
    ("cornelius", "Корнилий/Корнилия/Корнилию/Корнилием", "Cornelius", "Kornelius", "Корнилій/Корнилія/Корнилій"),
    ("gamaliel", "Гамалиил/Гамалиила/Гамалиилу", "Gamaliel", "Gamaliel", "Гамаліїл/Гамаліїла"),
    ("aquila", "Акила/Акилы/Акиле/Акилу", "Aquila", "Aquila", "Акила/Акили"),
    ("priscilla", "Прискилла/Прискиллы/Прискилле", "Priscilla", "Priszilla", "Прискилла/Прискилли"),
    ("apollos", "Аполлос/Аполлоса/Аполлосу", "Apollos", "Apollos", "Аполлос/Аполлоса"),
    # The reason this module exists. Crispus and Sosthenes are both
    # rulers of the same synagogue in the same chapter of Acts, which is
    # exactly why one can be written for the other and nothing downstream
    # notices.
    ("crispus", "Крисп/Криспа/Криспу/Криспом", "Crispus", "Krispus", "Крисп/Криспа"),
    ("sosthenes", "Сосфен/Сосфена/Сосфену", "Sosthenes", "Sosthenes", "Состен/Состена/Сосфен"),
    ("gallio", "Галлион/Галлиона/Галлиону", "Gallio", "Gallio", "Галліон/Галліона"),
    ("felix", "Феликс/Феликса/Феликсу", "Felix", "Felix", "Фелікс/Фелікса"),
    ("festus", "Фест/Феста/Фесту", "Festus", "Festus", "Фест/Феста"),
    ("agrippa", "Агриппа/Агриппы/Агриппе/Агриппу", "Agrippa", "Agrippa", "Агриппа/Агриппи"),
    ("lysias", "Лисий/Лисия/Лисию/Лисием", "Lysias", "Lysias", "Лісій/Лісія"),
    ("claudius", "Клавдий/Клавдия/Клавдию", "Claudius", "Klaudius", "Клавдій/Клавдія"),
    # Two names for one woman, and two rows, because answering the
    # Aramaic name with the Greek one leaves «Дорка (по-грецьки Серна)»
    # — a sentence that contradicts itself.
    ("tabitha", "Тавифа/Тавифы/Тавифе/Тавифу/Тавифой", "Tabitha", "Tabita", "Тавіта/Тавіти/Тавіту"),
    ("dorcas", "Доркас/Доркаса", "Dorcas", "Dorkas", "Дорка/Дорки/Дорку/Доркас"),
    ("aeneas", "Эней/Энея/Энею", "Aeneas", "Äneas", "Еней/Енея"),
    ("eutychus", "Евтих/Евтиха/Евтиху", "Eutychus", "Eutychus", "Євтих/Євтиха"),
    ("lydia", "Лидия/Лидии/Лидию/Лидией", "Lydia", "Lydia", "Лідія/Лідії/Лідію"),
    ("demetrius", "Димитрий/Димитрия/Димитрию", "Demetrius", "Demetrius", "Димитрій/Димитрія"),
    ("publius", "Публий/Публия/Публию", "Publius", "Publius", "Публій/Публія"),
    ("herod", "Ирод/Ирода/Ироду/Иродом", "Herod", "Herodes", "Ірод/Ірода/Іроду"),
    ("simon", "Симон/Симона/Симону/Симоном", "Simon", "Simon", "Симон/Симона/Симону"),
    ("simeon", "Симеон/Симеона/Симеону", "Simeon", "Simeon", "Симеон/Симеона"),
    ("tyrannus", "Тиранн/Тиранна/Тиранну", "Tyrannus", "Tyrannus", "Тиран/Тирана"),
    # ---- Acts: the places ----------------------------------------------
    # «Филипп» the man and «Филиппы» the city, the pair the model got
    # wrong in both directions: a lesson called «Филипп» came back
    # *Philippi*, and «в Филиппах» came back "in Philip".
    (
        "philippi",
        "Филиппы/Филиппах/Филиппам/Филиппами/Филиппийской/Филиппийская",
        "Philippi",
        "Philippi",
        "Филипи/Филипах/Филипам/Филиппи/Филиппах",
    ),
    ("jerusalem", "Иерусалим/Иерусалима/Иерусалиме/Иерусалиму", "Jerusalem", "Jerusalem", "Єрусалим/Єрусалима"),
    # «Иудеи» and «Иудеей» are deliberately absent. Both reduce to
    # the skeleton ``iudei``, and «Иудеи» is "Jews" far more often than
    # it is a case of Judea — which is how a correct English sentence
    # about Jews from Asia became a flag. «Иудее» stays, and shares its
    # skeleton with «Иуде» (Judas): a word that fits two rows is one
    # ambiguous statement, and ambiguity is the safe answer here.
    ("judea", "Иудея/Иудее/Иудею/Иудейской", "Judea/Judaea", "Judäa/Judäas", "Юдея/Юдеї/Юдейському/Юдейська/Іудея"),
    ("samaria", "Самария/Самарии/Самарию/Самарией", "Samaria", "Samaria", "Самарія/Самарії/Самарію"),
    ("galilee", "Галилея/Галилеи/Галилее/Галилею", "Galilee", "Galiläa", "Галілея/Галілеї"),
    ("damascus", "Дамаск/Дамаска/Дамаске/Дамаску", "Damascus", "Damaskus", "Дамаск/Дамаска/Дамаску"),
    ("antioch", "Антиохия/Антиохии/Антиохию/Антиохийской", "Antioch", "Antiochia/Antiochien", "Антіохія/Антіохії"),
    ("cyprus", "Кипр/Кипра/Кипре", "Cyprus", "Zypern", "Кіпр/Кіпру"),
    ("iconium", "Икония/Иконии", "Iconium", "Ikonion", "Іконія/Іконії"),
    ("lystra", "Листра/Листры/Листре", "Lystra", "Lystra", "Лістра/Лістри"),
    ("derbe", "Дервия/Дервии", "Derbe", "Derbe", "Дервія/Дервії"),
    ("troas", "Троада/Троады/Троаде", "Troas", "Troas", "Троада/Троади"),
    ("thessalonica", "Фессалоника/Фессалоники/Фессалонике", "Thessalonica", "Thessalonich", "Солунь/Солуні"),
    ("berea", "Верия/Верии", "Berea/Beroea", "Beröa", "Верія/Верії"),
    ("athens", "Афины/Афинах/Афин/Афинам", "Athens", "Athen", "Афіни/Афінах/Афін"),
    ("corinth", "Коринф/Коринфа/Коринфе/Коринфом", "Corinth", "Korinth", "Коринф/Коринфі/Коринт/Коринті"),
    ("ephesus", "Ефес/Ефеса/Ефесе/Ефесу", "Ephesus", "Ephesus", "Ефес/Ефесі/Ефеса"),
    ("miletus", "Милит/Милита/Милите", "Miletus", "Milet", "Мілет/Мілеті"),
    ("caesarea", "Кесария/Кесарии/Кесарию", "Caesarea", "Cäsarea", "Кесарія/Кесарії"),
    ("malta", "Мелит/Мелита/Мальта/Мальте", "Malta/Melita", "Malta", "Мальта/Мальті"),
    ("joppa", "Иоппия/Иоппии/Иоппию", "Joppa", "Joppe", "Йопія/Йопії/Йоппія"),
    ("lydda", "Лидда/Лидды/Лидде", "Lydda", "Lydda", "Лідда/Лідді"),
    ("tarsus", "Тарс/Тарса/Тарсе", "Tarsus", "Tarsus", "Тарс/Тарсі"),
    ("macedonia", "Македония/Македонии/Македонию", "Macedonia", "Mazedonien", "Македонія/Македонії"),
    ("achaia", "Ахаия/Ахаии", "Achaia", "Achaja", "Ахая/Ахаї"),
    ("syria", "Сирия/Сирии/Сирию", "Syria", "Syrien", "Сирія/Сирії"),
    ("cilicia", "Киликия/Киликии", "Cilicia", "Zilizien", "Кілікія/Кілікії"),
    ("galatia", "Галатия/Галатии", "Galatia", "Galatien", "Галатія/Галатії"),
    ("egypt", "Египет/Египта/Египте/Египту", "Egypt", "Ägypten", "Єгипет/Єгипту/Єгипті"),
    ("sinai", "Синай/Синае/Синаю/Синаем", "Sinai", "Sinai", "Синай/Синаю/Синаєм"),
    ("horeb", "Хорив/Хорива/Хориве", "Horeb", "Horeb", "Хорив/Хориві"),
    ("canaan", "Ханаан/Ханаана/Ханаане", "Canaan", "Kanaan", "Ханаан/Ханаану"),
    ("jericho", "Иерихон/Иерихона/Иерихоне", "Jericho", "Jericho", "Єрихон/Єрихона"),
    ("bethlehem", "Вифлеем/Вифлеема/Вифлееме", "Bethlehem", "Bethlehem", "Вифлеєм/Вифлеєма"),
    ("nazareth", "Назарет/Назарета/Назарете", "Nazareth", "Nazareth", "Назарет/Назарета"),
    ("babylon", "Вавилон/Вавилона/Вавилоне", "Babylon", "Babylon", "Вавилон/Вавилона"),
    # Genesis 11. Russian spells it exactly as Babylon, so this row and
    # the one above are one word in Russian and the check goes quiet —
    # see the module docstring. It is here so the *other* directions
    # (English or German source) still have a name to compare.
    ("babel", "Вавилон/Вавилона/Вавилоне", "Babel", "Babel", "Вавилон/Вавилона"),
    ("midian", "Мадиам/Мадиама", "Midian", "Midian", "Мадіам/Мадіама"),
    ("moab", "Моав/Моава", "Moab", "Moab", "Моав/Моава"),
    (
        "israel",
        "Израиль/Израиля/Израилю/Израилем/Израилевыми/Израильские/Израильских",
        "Israel",
        "Israel/Israels",
        "Ізраїль/Ізраїля/Ізраїлю/Ізраїлевих/Ізраїльські",
    ),
    # ---- Old Testament names the live catalogue actually uses -----------
    ("moses", "Моисей/Моисея/Моисею/Моисеем", "Moses", "Mose", "Мойсей/Мойсея/Мойсею"),
    ("aaron", "Аарон/Аарона/Аарону", "Aaron", "Aaron", "Аарон/Аарона"),
    ("abraham", "Авраам/Авраама/Аврааму/Авраамом", "Abraham", "Abraham", "Авраам/Авраама"),
    ("abram", "Аврам/Аврама/Авраму", "Abram", "Abram", "Аврам/Аврама"),
    ("isaac", "Исаак/Исаака/Исааку", "Isaac", "Isaak", "Ісаак/Ісаака"),
    ("jacob", "Иаков/Иакова/Иакову/Иаковом", "Jacob", "Jakob", "Яків/Якова/Якову"),
    ("joseph", "Иосиф/Иосифа/Иосифу/Иосифом", "Joseph", "Josef", "Йосип/Йосипа/Йосиф"),
    # Filed under the surname. «Иисус Навин» is Joshua and «Иисус» on
    # its own is not, and a two-word row would have to decide which of
    # two five-letter words carries the name — which it got wrong,
    # reading every «Иисуса» in the catalogue as Joshua.
    ("joshua", "Навин/Навина/Навину", "Joshua", "Josua", "Навин/Навина"),
    ("david", "Давид/Давида/Давиду/Давидом", "David", "David", "Давид/Давида"),
    ("solomon", "Соломон/Соломона/Соломону", "Solomon", "Salomo", "Соломон/Соломона"),
    ("samuel", "Самуил/Самуила/Самуилу", "Samuel", "Samuel", "Самуїл/Самуїла"),
    ("elijah", "Илия/Илии/Илию", "Elijah", "Elia", "Ілля/Іллі"),
    ("elisha", "Елисей/Елисея/Елисею", "Elisha", "Elisa", "Єлисей/Єлисея"),
    ("isaiah", "Исаия/Исаии/Исаию", "Isaiah", "Jesaja", "Ісая/Ісаї"),
    ("jeremiah", "Иеремия/Иеремии/Иеремию", "Jeremiah", "Jeremia", "Єремія/Єремії"),
    ("ezekiel", "Иезекииль/Иезекииля", "Ezekiel", "Hesekiel", "Єзекіїль/Єзекіїля"),
    ("daniel", "Даниил/Даниила/Даниилу", "Daniel", "Daniel", "Даниїл/Даниїла"),
    ("noah", "Ной/Ноя/Ною/Ноем", "Noah", "Noah", "Ной/Ноя/Ноєм"),
    ("adam", "Адам/Адама/Адаму", "Adam", "Adam", "Адам/Адама"),
    ("ruth", "Руфь/Руфи", "Ruth", "Rut", "Рут/Рути/Руф"),
    ("boaz", "Вооз/Вооза", "Boaz", "Boas", "Вооз/Вооза"),
    ("esther", "Есфирь/Есфири", "Esther", "Ester", "Естер/Естери"),
    ("job", "Иов/Иова/Иову", "Job", "Hiob", "Йов/Йова"),
    ("jonah", "Иона/Ионы/Ионе/Иону", "Jonah", "Jona", "Йона/Йони"),
    ("joel", "Иоиль/Иоиля", "Joel", "Joel", "Йоіл/Йоіля"),
    ("samson", "Самсон/Самсона", "Samson", "Simson", "Самсон/Самсона"),
    ("gideon", "Гедеон/Гедеона", "Gideon", "Gideon", "Гедеон/Гедеона"),
    ("pharaoh", "Фараон/Фараона/Фараону", "Pharaoh", "Pharao", "Фараон/Фараона"),
    ("jethro", "Иофор/Иофора", "Jethro", "Jitro", "Йотор/Йотора"),
    ("nebuchadnezzar", "Навуходоносор/Навуходоносора", "Nebuchadnezzar", "Nebukadnezar", "Навуходоносор"),
    ("cyrus", "Кир/Кира/Киру", "Cyrus", "Kyrus", "Кир/Кира"),
    ("darius", "Дарий/Дария", "Darius", "Darius", "Дарій/Дарія"),
    ("pilate", "Пилат/Пилата/Пилату", "Pilate", "Pilatus", "Пилат/Пилата"),
)

# Spellings a language does **not** print for a person, kept so that
# everything above still recognises them *as* that person.
#
# The same shape, and the same reason, as ``bible.books.
# _NOT_PRINTED_HERE``. A language has spellings it prints and spellings
# it does not: Ukrainian prints «Стефан» — Куліш 1905, the edition this
# platform serves, has «Стефана» at Acts 6:5, 7:59, 8:2, 11:19 and
# 22:20 — and «Степан» is the ordinary Ukrainian given name Stepan,
# which is a different name and not another spelling of this one.
#
# Registered into ``_EXACT`` and ``_STEMS`` exactly like the printed
# forms, and deliberately absent from ``_PRINTED``. That split is what
# makes the two checks say different things about the same word:
# ``substituted_names`` reads «Степана» as *Stephen, spelt oddly* and
# stays silent, which is the right answer to "did the translation put a
# different person here"; ``person_names.foreign_person_names`` reads
# the literal spelling and says Ukrainian does not print it. Take these
# out of the index instead of moving them here and «Стефан» → «Степан»
# reads as a name arriving out of nowhere — the wrong diagnosis, and an
# accusation of substituting somebody who was never named.
#
# Literal, not phonetic, because spelling is the whole subject. The
# skeletons these rows are indexed under cannot tell «Лисий» from
# «Лісій» — ``и`` and ``і`` are one letter to ``_skeleton``, by design,
# so that «Галилея» can meet «Галілея» — and one of those two is what
# Ukrainian prints.
#
# Every form below was read off the live catalogue by a native editor
# before it was written down, and each row is a claim that costs
# something: a language that does print a form and is listed here flags
# correct prose in every row that uses it. German ``Stephan`` was
# measured (14 rows) and is *not* here — German really does print it,
# which is why the feast is der Stephanstag and the cathedral is der
# Stephansdom.
_NOT_PRINTED_HERE: Final[dict[str, dict[str, str]]] = {
    "uk": {
        # Read on production in eight rows, every one an assessment
        # item: «промова Степана в Діян. 7», «при смерті Степана»,
        # «хто схвалив страту Степана?». The lessons those questions
        # examine print «Стефан».
        "stephen": "Степан/Степана/Степану/Степанові/Степаном/Степане",
        # «Лисий» is the Russian spelling standing in Ukrainian prose,
        # where it is read as the adjective *bald*; «Лій» is not a name
        # in any language and is the Ukrainian noun for tallow. Куліш
        # prints «Лизия» (Acts 23:26, 24:7, 24:22) and the modern
        # editions print «Лісій», which is what the same course prints
        # two paragraphs earlier and in the quiz option.
        "lysias": "Лисий/Лій",
    },
}


def _verify_every_name_is_written_in_every_language(locales: tuple[str, ...]) -> None:
    """Refuse to load a table that is narrower than the roster.

    The same reasoning as ``glossary._verify_every_term_is_written_in_
    every_language``, and the same failure mode it prevents: the columns
    are positional, so a table one language short does not check that
    language badly — it stops having an opinion about it, silently, and
    every row of it reads as a pass.
    """
    widths = {len(row) for row in _NAMES}
    expected = len(locales) + 1
    if widths == {expected}:
        return
    raise LanguageNotInTable(
        f"The proper-name table has rows {sorted(widths)} cells wide, and this "
        f"platform serves {len(locales)} languages ({', '.join(locales)}) — so "
        f"every row needs a key and {len(locales)} cells, {expected} in all, in "
        "the order of ``LOCALE_CODES``. A language left out of this table is a "
        "language in which one biblical name may be answered with another and "
        "nothing will say so."
    )


_verify_every_name_is_written_in_every_language(LOCALE_CODES)


def _forms(cell: str) -> tuple[str, ...]:
    return tuple(form.strip() for form in cell.split("/") if form.strip())


_Table = dict[str, dict[str, frozenset[str]]]


def _index() -> tuple[_Table, _Table]:
    """Two lookups per language, built once at import.

    The exact skeleton, and the skeleton with its ending off. Built
    eagerly rather than lazily because this is read from provider
    threads, and a dictionary filled from several threads at once is a
    race nobody would ever see fail — the same call ``term_memory``
    makes about ``_GLOSSARY_KEYS``.

    The not-printed forms go in beside the printed ones. They are
    spellings of the person they are filed under — a bad one — and
    every question these two tables answer is "who is this word about",
    which has the same answer either way.
    """
    exact: dict[str, dict[str, set[str]]] = {locale: {} for locale in LOCALE_CODES}
    stems: dict[str, dict[str, set[str]]] = {locale: {} for locale in LOCALE_CODES}
    rows: list[tuple[str, str, str]] = [
        (row[0], locale, cell) for row in _NAMES for locale, cell in zip(LOCALE_CODES, row[1:], strict=True)
    ]
    rows += [(key, locale, cell) for locale, table in _NOT_PRINTED_HERE.items() for key, cell in table.items()]
    for key, locale, cell in rows:
        for form in _forms(cell):
            skeleton = _skeleton(form)
            if len(skeleton) < _MIN_SKELETON:
                # Too little to identify anything — ``iov`` would
                # match half the Old Testament. ``term_memory``
                # measured this floor; a shorter name is simply not
                # checkable and saying so is better than guessing.
                # «Лій» falls here, which is why the check that reads
                # spelling reads it literally and not through this.
                continue
            exact[locale].setdefault(skeleton, set()).add(key)
            stems[locale].setdefault(_stem(skeleton), set()).add(key)
    frozen = tuple(
        {locale: {k: frozenset(v) for k, v in table.items()} for locale, table in built.items()}
        for built in (exact, stems)
    )
    return frozen[0], frozen[1]


_EXACT, _STEMS = _index()


def _printed() -> dict[str, dict[str, str]]:
    """locale → the form that language prints, per name.

    The first entry of the cell, which is the dictionary form
    everywhere in the table — what a reviewer should have seen.
    """
    printed: dict[str, dict[str, str]] = {locale: {} for locale in LOCALE_CODES}
    for row in _NAMES:
        for locale, cell in zip(LOCALE_CODES, row[1:], strict=True):
            forms = _forms(cell)
            if forms:
                printed[locale][row[0]] = forms[0]
    return printed


_PRINTED: Final[dict[str, dict[str, str]]] = _printed()

#: Every form of every name, filed by the consonant it starts with. Not
#: an optimisation detail: ``term_memory._similarity`` returns zero
#: outright for two skeletons that begin with different consonants, so
#: grouping this way compares exactly the pairs that could ever score,
#: and a long lesson does not pay a thousand ``SequenceMatcher`` calls
#: to be told no a thousand times.
_BY_CONSONANT: Final[dict[str, dict[str, tuple[tuple[str, frozenset[str]], ...]]]] = {
    locale: {
        consonant: tuple(
            (skeleton, keys) for skeleton, keys in table.items() if _first_consonant(skeleton) == consonant
        )
        for consonant in {_first_consonant(skeleton) for skeleton in table}
    }
    for locale, table in _EXACT.items()
}

# A word, apostrophes kept, the same shape ``term_memory`` tokenises
# with — «Мар'ям» is one token and not two.
_WORD_RE: Final[re.Pattern[str]] = re.compile(r"[^\W\d_]+(?:['’ʼ][^\W\d_]+)*", re.UNICODE)

#: Pairs named in one issue. Past a handful the sentence stops being
#: something a reviewer can act on.
_MAX_REPORTED: Final[int] = 4


#: A book cited by number and name, the way German prints the
#: Pentateuch: ``1. Mose``, ``3. Mose``, and in Russian ``1 Царств``.
#: ``parse_references`` will not see these — it insists on a chapter and
#: a verse, and a bare ``(1. Mose 11)`` has no verse — so they are found
#: here and confirmed against ``bible.books`` rather than guessed at.
_NUMBERED_BOOK_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)(\d{1,3}\s*\.?\s*([^\W\d_]+))", re.UNICODE)

#: …and a book cited by name and chapter with no verse: ``Isaiah 49``,
#: ``Левит 11``.
_BOOK_AND_CHAPTER_RE: Final[re.Pattern[str]] = re.compile(r"(?<!\w)([^\W\d_]+)\s*\d{1,3}(?!\s*[:.,]\s*\d)", re.UNICODE)


def _blank_citations(text: str, locale: str) -> str:
    """Erase what is a book being cited rather than a person being named.

    German prints Genesis as *1. Mose* and Leviticus as *3. Mose*, and
    the Russian these lessons are written from prints them «Бытие» and
    «Левит». So a correct German translation of a reading list contains
    the word *Mose* where its source contained no Moses at all — and
    without this, that is a new name appearing out of nowhere, which is
    exactly what this check reports. It did: two of the eighteen rows
    the first measurement flagged were a citation and nothing else.

    Blanked in place, keeping the length, because the caller still holds
    offsets into this string — the same contract
    ``glossary._blank_scripture_references`` keeps, and it is called
    first, for the citations that do carry a verse.

    Only where a number says it is a citation. "The book of Isaiah" as a
    quiz answer keeps its name and is still compared, which matters: one
    of the substitutions this check found in production is a Russian
    «Книгу Иова» answered in English with *the book of Isaiah*.
    """
    chars = list(text)
    for reference in parse_references(text, locale):
        start, end = reference.span
        chars[start:end] = " " * (end - start)
    blanked = "".join(chars)
    for pattern, group in ((_NUMBERED_BOOK_RE, 1), (_BOOK_AND_CHAPTER_RE, 1)):
        for match in pattern.finditer(blanked):
            if find_book(match.group(group)) is None:
                continue
            start, end = match.span(group)
            blanked = blanked[:start] + " " * (end - start) + blanked[end:]
    return blanked


def capitalised_words(text: str, locale: str) -> list[tuple[str, int]]:
    """Capitalised words of ``text``, with where each one sits.

    Capitalisation, and not ``term_memory.name_candidates``: that helper
    also drops a word that opens a clause, which is right when it is
    guessing whether a word is a name and wrong here, where a table
    already knows. The row this check exists for is the lesson title
    ``Урок 5. Филипп: …`` — where the name *is* the word after the full
    stop, and dropping it would drop the defect.

    An all-caps word is a heading or an acronym and says nothing about
    its own shape, which is the one exclusion worth keeping.

    Public because ``person_names`` reads the same words with the same
    citations blanked, and asks a different question about them.
    """
    # Entities decoded before anything reads a word. The catalogue
    # writes a reference as ``1&nbsp;Тимофею 1:3``, and ``strip_tags``
    # leaves the entity standing — so the citation blanker saw a digit
    # followed by an ampersand, declined to call it a book, and this
    # module read the name of a letter as the naming of a man.
    prose = _blank_citations(unescape(strip_tags(text) if "<" in text else text), locale)
    found: list[tuple[str, int]] = []
    for match in _WORD_RE.finditer(prose):
        word = match.group(0)
        if word[0].isupper() and not word.isupper():
            found.append((word, match.start()))
    return found


def _tokens(text: str, locale: str) -> list[tuple[str, str, int]]:
    """The same words, reduced to skeletons, minus the ones too short to
    identify anybody.

    The floor belongs here rather than in ``capitalised_words``: it is a
    fact about ``term_memory``'s comparison, not about the text, and the
    check that reads a spelling literally is not subject to it.
    """
    found: list[tuple[str, str, int]] = []
    for word, offset in capitalised_words(text, locale):
        skeleton = _skeleton(word)
        if len(skeleton) >= _MIN_SKELETON:
            found.append((word, skeleton, offset))
    return found


def _named(tokens: list[tuple[str, str, int]], locale: str, *, strict: bool) -> list[tuple[str, int, frozenset[str]]]:
    """Which names in the table these words use, word by word.

    Returned per word rather than per name because a word that fits two
    rows is one ambiguous statement and not two claims: "Saul" is the
    king and the man from Tarsus in English, and a translation that
    writes it has named whichever of them the source did.

    ``strict`` is the whole safety argument, and the two settings are
    used in opposite directions.

    Strict asks for an exact form: the word, reduced to a skeleton, *is*
    a spelling this table carries. Both halves of an accusation are made
    on strict evidence — that the source named somebody, and that the
    translation named somebody else — because a fuzzy reading invents
    names out of ordinary words. Measured on the live catalogue, a loose
    source side read «Деяния» as Derbe, «Первая» as Rome and «Правила»
    as Job, and every one of those became a flag on correct prose.

    Loose adds two fallbacks — the same word with its ending changed,
    then anything that sounds like it under ``term_memory``'s measured
    threshold. Both exonerating questions are asked loosely: *did the
    translation keep this name* and *had the source already named this
    one*. Being easy to clear is the point — a transliteration, an
    inflection, a spelling this table never thought of all count as the
    name surviving, and none of them is a substitution.
    """
    found: list[tuple[str, int, frozenset[str]]] = []
    for word, skeleton, offset in tokens:
        keys = _EXACT[locale].get(skeleton)
        if keys is None and not strict:
            keys = _STEMS[locale].get(_stem(skeleton))
        if keys is None and not strict:
            keys = _sounds_like(skeleton, locale)
        if keys:
            found.append((word, offset, keys))
    return found


def _sounds_like(skeleton: str, locale: str) -> frozenset[str]:
    """Names this word could be a spelling of, by sound.

    The last tier and the most generous one, and it only ever makes a
    name *harder* to report: it is consulted when deciding whether the
    translation kept a name and when deciding whether the source had
    already named one, never when deciding that a new name arrived.
    """
    candidates = _BY_CONSONANT[locale].get(_first_consonant(skeleton), ())
    return frozenset(
        key
        for form_skeleton, keys in candidates
        if _similarity(skeleton, form_skeleton) >= _MIN_SIMILARITY
        for key in keys
    )


def not_printed_in(locale: str) -> tuple[tuple[str, str], ...]:
    """Every spelling written down as one ``locale`` does not print, with
    the person each one was reaching for.

    A closed, hand-checked list, and the only thing in this module that
    accuses on the strength of a spelling alone. The parallel with
    ``bible.books.not_printed_in`` is exact, including why it has to be
    written by hand: nothing here can tell a spelling a language lacks
    from a spelling nobody happened to write down.
    """
    return tuple((form, key) for key, cell in _NOT_PRINTED_HERE.get(locale, {}).items() for form in _forms(cell))


def printed_in(key: str, locale: str) -> str | None:
    """What ``locale`` does print for this person, or ``None`` if this
    table has no column for the two of them."""
    return _PRINTED.get(locale, {}).get(key)


def named_in(text: str, locale: str) -> frozenset[str]:
    """Every person or place ``text`` names, on exact evidence.

    The strict reading, and only the strict one: this is the half of an
    accusation that says the source really did name somebody, and read
    loosely the source side invents names out of ordinary words — it
    read «Деяния» as Derbe and «Правила» as Job. A caller wanting the
    generous reading wants ``substituted_names``, which asks both.
    """
    keys: set[str] = set()
    for _word, _offset, found in _named(_tokens(text, locale), locale, strict=True):
        keys |= found
    return frozenset(keys)


def substituted_names(
    source: str,
    translation: str,
    *,
    source_locale: LocaleCode,
    target_locale: LocaleCode,
) -> list[tuple[str, str]]:
    """Names the source used that the translation answered with other names.

    Returns ``(the word the source used, the word the translation used
    instead)`` — the words themselves rather than the table's keys,
    because the reviewer's question is "does this sentence still say
    what the Russian said", and two quoted words answer it.

    Empty unless *both* halves are true in the same row: a name from the
    table left the translation, and a different name from the table
    arrived in it. One without the other is not evidence of anything —
    a translation drops a name into a pronoun all the time, and a
    translation that names somebody the source also named is doing its
    job.
    """
    if not source or not translation or source_locale == target_locale:
        return []
    if source_locale not in _EXACT or target_locale not in _EXACT:
        raise LanguageNotInTable(
            f"The proper-name table has no column for {source_locale!r} or "
            f"{target_locale!r}. It carries {', '.join(_EXACT)}. A pair it "
            "cannot read is a pair where one name may be answered with "
            "another silently, and an empty answer would look like a pass."
        )

    source_words = _tokens(source, source_locale)
    target_words = _tokens(translation, target_locale)

    # Everything the source can be read as naming, in any of the four
    # languages and on the loosest evidence. A Russian lesson that writes
    # "(Philippi)" in brackets has named the city, and the German
    # translation repeating it has introduced nothing; a Russian
    # «Савлу» has named Saul, so an English "Saul" is not a new man.
    already: set[str] = set()
    for _word, _offset, keys in _named(source_words, source_locale, strict=False):
        already |= keys
    for locale in _EXACT:
        # Strictly in the other three, and loosely in none of them. A
        # Russian lesson that writes "(Philippi)" in brackets has named
        # the city and the German repeating it introduces nothing — but
        # asked loosely, the German column reads «Филипп» as an ending
        # away from *Philippi* and quietly exonerates the one row this
        # module was written for.
        for _word, _offset, keys in _named(source_words, locale, strict=True):
            already |= keys
    kept: set[str] = set()
    for _word, _offset, keys in _named(target_words, target_locale, strict=False):
        kept |= keys

    missing = sorted(
        (offset, word) for word, offset, keys in _named(source_words, source_locale, strict=True) if not (keys & kept)
    )
    # A word is a new name only when *none* of the rows it could be was
    # already named. "Saul" is two rows in English, and a source that
    # named either of them is a source this word does not contradict.
    appeared = sorted(
        (offset, word)
        for word, offset, keys in _named(target_words, target_locale, strict=True)
        if not (keys & already)
    )
    if not missing or not appeared:
        return []
    return _pair_up(missing, len(source), appeared, len(translation))[:_MAX_REPORTED]


def _pair_up(
    missing: list[tuple[int, str]],
    source_length: int,
    appeared: list[tuple[int, str]],
    translation_length: int,
) -> list[tuple[str, str]]:
    """Which vanished name goes with which new one, for the sentence a
    person reads.

    By where they sit. A translation follows its source, so the name
    that arrived three fifths of the way through the German is standing
    where the name three fifths of the way through the Russian used to
    be — and that is the pair a reviewer needs quoted. Measured: the
    lesson that lost «Крисп» also stops mentioning «Рима» (German writes
    *Rom*, three letters, too short for this module to see), and pairing
    by order alone offered "«Рима» → *Sosthenes*", which sends the
    reviewer to the wrong sentence.

    Nothing depends on getting this right — the row is flagged either
    way, and the pairing is only the wording of the explanation.
    """
    unclaimed = list(missing)
    pairs: list[tuple[str, str]] = []
    for offset, gained in appeared:
        if not unclaimed:
            break
        here = offset / max(translation_length, 1)
        nearest = min(unclaimed, key=lambda item: abs(item[0] / max(source_length, 1) - here))
        unclaimed.remove(nearest)
        pairs.append((nearest[1], gained))
    return pairs


__all__ = ["capitalised_words", "named_in", "not_printed_in", "printed_in", "substituted_names"]
