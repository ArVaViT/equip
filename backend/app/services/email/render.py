"""Assemble a message out of blocks, once, for every email we send.

Mail is not the web: no stylesheet, no flex, no grid. Gmail strips
``<style>``, Outlook renders through Word. So the layout is tables and
every rule is inline, and that is a constraint rather than a style
choice.

**The message carries no images.** An earlier version led with the
course cover, which looked well in a preview and badly everywhere else:
roughly half of recipients never load images, a cover is a picture of
text so it cannot reflow on a phone, and a cover written in one
language opens a letter written in another — which is exactly how a
Russian invitation arrived under an English banner. Everything that
looks like a poster here is real text: it reads the same with images
off, in a dark theme and on a watch, and it weighs kilobytes.

Two rules this module exists to keep:

* **Nothing interpolates unescaped.** A course title, a school name and
  the name of whoever is inviting are all typed by people, and they end
  up inside HTML and inside an ``href``. ``escape`` is applied here so
  no caller has to remember it.
* **The text alternative is a first-class reader.** A client that
  strips tags sees no CSS, so nothing may rely on ``display:block`` to
  keep two words apart.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from app.services.email import theme


@dataclass(frozen=True)
class Fact:
    """One row of the detail table: what it is, and what it says."""

    label: str
    value: str


@dataclass(frozen=True)
class Message:
    """Everything a rendered email needs, already localized.

    The renderer does no lookups: whatever reaches it is the final text
    in the reader's language. That keeps this module testable without a
    database and keeps language decisions in one place — the caller.
    """

    #: Small caps line above the title ("UCOAT · invitation").
    eyebrow: str
    title: str
    #: The one sentence under the title, when there is one to say.
    lede: str
    cta_label: str
    cta_url: str
    #: Shown in the client's message list before the mail is opened.
    preview: str
    #: The detail table: when it starts, how many lessons, who teaches.
    facts: tuple[Fact, ...] = field(default_factory=tuple)
    #: Small print under the button, in order.
    notes: tuple[str, ...] = field(default_factory=tuple)


def _lede(message: Message) -> str:
    eyebrow = (
        f'<p style="margin:0 0 30px 0; font-family:{theme.SANS}; font-size:11px; '
        f'letter-spacing:0.22em; text-transform:uppercase; color:{theme.INK_FAINT};">'
        f"{escape(message.eyebrow)}</p>"
        if message.eyebrow
        else ""
    )
    lede = (
        f'<p style="margin:22px 0 0 0; font-family:{theme.SANS}; font-size:16px; '
        f'line-height:1.65; color:{theme.INK_BODY};">{escape(message.lede)}</p>'
        if message.lede
        else ""
    )
    return (
        f'<tr><td style="padding:46px 44px 0 44px;">{eyebrow}'
        f'<h1 style="margin:0; font-family:{theme.SERIF}; font-size:46px; line-height:1.08; '
        f'font-weight:600; letter-spacing:-0.02em; color:{theme.INK};">{escape(message.title)}</h1>'
        f"{lede}</td></tr>"
    )


def _facts(message: Message) -> str:
    if not message.facts:
        return ""
    rows = ""
    for index, fact in enumerate(message.facts):
        edges = f"border-top:1px solid {theme.RULE};"
        if index == len(message.facts) - 1:
            edges += f" border-bottom:1px solid {theme.RULE};"
        rows += (
            f"<tr>"
            f'<td width="45%" style="padding:13px 0; {edges} font-family:{theme.SANS}; '
            f'font-size:15px; line-height:1.5; color:{theme.INK_BODY};">{escape(fact.label)}</td>'
            f'<td width="55%" align="right" style="padding:13px 0; {edges} font-family:{theme.SANS}; '
            f'font-size:15px; line-height:1.5; color:{theme.INK};"><strong>{escape(fact.value)}</strong></td>'
            f"</tr>"
        )
    return (
        f'<tr><td style="padding:32px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">'
        f"{rows}</table></td></tr>"
    )


def _cta(message: Message) -> str:
    # Text, not an image: with images off a picture-button is a message
    # with no way out of it.
    return (
        f'<tr><td style="padding:30px 44px 0 44px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td align="center" style="background:{theme.INK}; border-radius:10px;">'
        f'<a href="{escape(message.cta_url, quote=True)}" '
        f'style="display:block; padding:17px 24px; font-family:{theme.SANS}; font-size:16px; '
        f'font-weight:600; color:{theme.ON_INK}; text-decoration:none; text-align:center;">'
        f"{escape(message.cta_label)}</a>"
        f"</td></tr></table></td></tr>"
    )


def _notes(message: Message) -> str:
    if not message.notes:
        return ""
    lines = "".join(
        f'<p style="margin:0 0 4px 0; font-family:{theme.SANS}; font-size:12px; '
        f'line-height:1.6; color:{theme.INK_FAINT};">{escape(note)}</p>'
        for note in message.notes
    )
    return f'<tr><td style="padding:18px 44px 40px 44px;" align="center">{lines}</td></tr>'


def render(message: Message) -> str:
    """One message, as the HTML body to hand the provider."""
    hidden_preview = (
        f'<div style="display:none; max-height:0; overflow:hidden; opacity:0;">{escape(message.preview)}</div>'
    )
    return (
        f'<body style="margin:0; padding:0; background:{theme.GROUND};">'
        f"{hidden_preview}"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{theme.GROUND}; padding:36px 12px;"><tr><td align="center">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:600px; max-width:100%; background:{theme.CARD}; border-radius:16px; overflow:hidden;">'
        f"{_lede(message)}{_facts(message)}{_cta(message)}{_notes(message)}"
        f"</table></td></tr></table></body>"
    )
