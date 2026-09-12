"""The brand, in the only form email understands: hex and inline styles.

These values mirror ``frontend/src/index.css`` design tokens and the
edge function's ``supabase/functions/send-email/copy.ts``. They are
written as hex because mail clients do not read CSS custom properties,
and they are duplicated across the two runtimes because one is Python
and the other is Deno — a fact neither can fix.

What keeps the two copies honest is a test on each side that forbids
the retired palette. The edge function has had one since the August
palette fix (``copy.test.ts``); the absence of its twin here is how the
invitation email stayed blue for a month after everything else stopped
being blue.

Literata is not loaded — mail clients do not fetch webfonts — so Georgia
leads the serif fallback. Its x-height/em (.481) is the closest of the
ubiquitous serifs to Literata's (.503), which is the same reason it
leads the stack on the web.
"""

from typing import Final

#: Paper the message sits on, and the card it sits in.
GROUND: Final = "#EFEDE8"
CARD: Final = "#FBFAF8"
CARD_EDGE: Final = "#E2DED6"
FOOTER_GROUND: Final = "#F3F1EC"
RULE: Final = "#E7E3DB"

#: Ink, in three weights of attention.
INK: Final = "#1E1C1A"
INK_BODY: Final = "#45413B"
INK_MUTED: Final = "#6D675F"
INK_FAINT: Final = "#8A8377"
#: On the dark header, where the ground is INK.
ON_INK: Final = "#F8F8F6"
ON_INK_MUTED: Final = "#A9A296"

SERIF: Final = "Literata,Georgia,Cambria,'Times New Roman',serif"
SANS: Final = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

#: Colours this product stopped using in August 2026. Any of them in a
#: rendered message is a regression, and ``test_the_email_wears_the_
#: current_palette`` fails on it.
RETIRED_COLOURS: Final = ("#2563eb", "#1a1a2e", "#4a4a6a", "#8888a8", "#422277", "#67A982")
