"""Assemble a message out of blocks, once, for every email we send.

Mail is not the web: no stylesheet, no flex, no grid. Gmail strips
``<style>``, Outlook renders through Word. So the layout is tables and
every rule is inline, and that is a constraint rather than a style
choice.

Two rules this module exists to keep:

* **Nothing interpolates unescaped.** A course title, a school name and
  the name of whoever is inviting are all typed by people, and they end
  up inside HTML and inside an ``href``. ``escape`` is applied here so
  no caller has to remember it.
* **The message reads with images off.** Roughly half of recipients see
  no images at all, so the banner carries an ``alt`` and — deliberately
  — no height attribute: a reserved height leaves a dark rectangle
  where a picture was supposed to be, and everything that matters is in
  the text below it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from app.services.email import theme


@dataclass(frozen=True)
class Fact:
    """One short label/value pair in the strip under the lede."""

    label: str
    value: str


@dataclass(frozen=True)
class Message:
    """Everything a rendered email needs, already localized.

    The renderer does no lookups: whatever reaches it is the final text
    in the reader's language. That keeps this module testable without a
    database and keeps language decisions in one place — the caller.
    """

    #: Small caps line above the title ("Course invitation").
    eyebrow: str
    title: str
    lede: str
    cta_label: str
    cta_url: str
    #: Shown in the client's message list before the mail is opened.
    preview: str
    #: Right of the wordmark in the header — the school, when there is one.
    org_name: str | None = None
    banner_url: str | None = None
    banner_alt: str | None = None
    facts: tuple[Fact, ...] = field(default_factory=tuple)
    #: Small print under the button, in order.
    notes: tuple[str, ...] = field(default_factory=tuple)
    footer: str = ""


def _header(message: Message) -> str:
    org = (
        f'<span style="font-family:{theme.SANS}; font-size:12px; color:{theme.ON_INK_MUTED}; '
        f'letter-spacing:0.18em; text-transform:uppercase; float:right; padding-top:6px;">'
        f"{escape(message.org_name)}</span>"
        if message.org_name
        else ""
    )
    return (
        f'<tr><td style="padding:22px 32px; background:{theme.INK};">'
        f'<span style="font-family:{theme.SERIF}; font-size:20px; font-weight:600; '
        f'color:{theme.ON_INK}; letter-spacing:0.01em;">Equip</span>{org}'
        f"</td></tr>"
    )


def _banner(message: Message) -> str:
    if not message.banner_url:
        return ""
    alt = escape(message.banner_alt or "")
    return (
        f'<tr><td style="padding:0; line-height:0; background:{theme.INK};">'
        f'<img src="{escape(message.banner_url, quote=True)}" width="600" alt="{alt}" '
        f'style="display:block; width:100%; max-width:600px; height:auto; border:0; '
        f'font-family:{theme.SERIF}; font-size:16px; color:{theme.ON_INK}; padding:14px 0;">'
        f"</td></tr>"
    )


def _lede(message: Message) -> str:
    return (
        f'<tr><td style="padding:36px 32px 8px 32px;">'
        f'<p style="margin:0 0 10px 0; font-family:{theme.SANS}; font-size:12px; '
        f'letter-spacing:0.18em; text-transform:uppercase; color:{theme.INK_FAINT};">'
        f"{escape(message.eyebrow)}</p>"
        f'<h1 style="margin:0 0 18px 0; font-family:{theme.SERIF}; font-size:30px; '
        f'line-height:1.25; font-weight:600; color:{theme.INK};">{escape(message.title)}</h1>'
        f'<p style="margin:0; font-family:{theme.SANS}; font-size:16px; line-height:1.65; '
        f'color:{theme.INK_BODY};">{escape(message.lede)}</p>'
        f"</td></tr>"
    )


def _facts(message: Message) -> str:
    if not message.facts:
        return ""
    width = 100 // len(message.facts)
    cells = "".join(
        f'<td width="{width}%" valign="top" style="padding:16px 12px 16px 0; '
        f'font-family:{theme.SANS}; font-size:14px; line-height:1.5; color:{theme.INK_BODY};">'
        f'<strong style="display:block; color:{theme.INK};">{escape(fact.label)}</strong>'
        f"{escape(fact.value)}</td>"
        for fact in message.facts
    )
    # A table rather than a list: Outlook renders list markers its own way.
    return (
        f'<tr><td style="padding:14px 32px 6px 32px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="border-top:1px solid {theme.RULE}; border-bottom:1px solid {theme.RULE};">'
        f"<tr>{cells}</tr></table></td></tr>"
    )


def _cta(message: Message) -> str:
    # Text, not an image: with images off a picture-button is a message
    # with no way out of it.
    return (
        f'<tr><td style="padding:28px 32px 8px 32px;">'
        f'<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>'
        f'<td align="center" style="background:{theme.INK}; border-radius:8px;">'
        f'<a href="{escape(message.cta_url, quote=True)}" '
        f'style="display:inline-block; padding:15px 38px; font-family:{theme.SANS}; '
        f'font-size:16px; font-weight:600; color:{theme.ON_INK}; text-decoration:none;">'
        f"{escape(message.cta_label)}</a>"
        f"</td></tr></table></td></tr>"
    )


def _notes(message: Message) -> str:
    if not message.notes:
        return ""
    first, *rest = message.notes
    lines = (
        f'<p style="margin:0 0 6px 0; font-family:{theme.SANS}; font-size:13px; '
        f'line-height:1.6; color:{theme.INK_MUTED};">{escape(first)}</p>'
    )
    lines += "".join(
        f'<p style="margin:0; font-family:{theme.SANS}; font-size:13px; line-height:1.6; '
        f'color:{theme.INK_FAINT};">{escape(note)}</p>'
        for note in rest
    )
    return f'<tr><td style="padding:10px 32px 34px 32px;">{lines}</td></tr>'


def _footer(message: Message) -> str:
    if not message.footer:
        return ""
    return (
        f'<tr><td style="padding:18px 32px; background:{theme.FOOTER_GROUND}; '
        f'border-top:1px solid {theme.RULE};">'
        f'<p style="margin:0; font-family:{theme.SANS}; font-size:12px; line-height:1.6; '
        f'color:{theme.INK_FAINT};">{escape(message.footer)} '
        f'<a href="https://equipbible.com" style="color:{theme.INK_MUTED}; '
        f'text-decoration:underline;">equipbible.com</a></p>'
        f"</td></tr>"
    )


def render(message: Message) -> str:
    """One message, as the HTML body to hand the provider."""
    hidden_preview = (
        f'<div style="display:none; max-height:0; overflow:hidden; opacity:0;">{escape(message.preview)}</div>'
    )
    return (
        f'<body style="margin:0; padding:0; background:{theme.GROUND};">'
        f"{hidden_preview}"
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
        f'style="background:{theme.GROUND}; padding:32px 12px;"><tr><td align="center">'
        f'<table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" '
        f'style="width:600px; max-width:100%; background:{theme.CARD}; border-radius:14px; '
        f'overflow:hidden; border:1px solid {theme.CARD_EDGE};">'
        f"{_header(message)}{_banner(message)}{_lede(message)}{_facts(message)}"
        f"{_cta(message)}{_notes(message)}{_footer(message)}"
        f"</table></td></tr></table></body>"
    )
