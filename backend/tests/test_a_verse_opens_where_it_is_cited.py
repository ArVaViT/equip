"""A reference in a lesson opens its verse, in the reader's Bible.

The page sends a block's text; the server finds the references with the
pipeline's own parser and answers the ones it can show. These pin who may
ask, what comes back, and that nothing is linked that cannot be opened.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.api.v1 import scripture

if TYPE_CHECKING:
    import pytest
    from fastapi.testclient import TestClient

    from app.services.bible.references import BibleRef

LESSON = "Иисус обещает силу (Деян. 1:8), и в Пятидесятницу (Деян 2:1\u20134) она приходит. Ещё раз: Деян. 1:8. Встреча в 10:30."


def _from_api(texts: dict[str, str]):
    def fetch(ref: BibleRef, locale: str) -> str | None:
        return texts.get(f"{locale} {ref}")

    return fetch


def test_the_reader_gets_each_reference_once_in_their_language(
    student_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        scripture,
        "fetch_verse",
        _from_api({"ru acts 1:8": "но вы примете силу…", "ru acts 2:1-4": "При наступлении дня Пятидесятницы…"}),
    )
    r = student_client.post("/api/v1/scripture/passages", json={"text": LESSON}, headers={"Accept-Language": "ru"})
    assert r.status_code == 200, r.text
    assert r.json() == [
        {"written": "Деян. 1:8", "ref": "acts 1:8", "text": "но вы примете силу…", "edition": "nrt"},
        {
            "written": "Деян 2:1\u20134",
            "ref": "acts 2:1-4",
            "text": "При наступлении дня Пятидесятницы…",
            "edition": "nrt",
        },
    ]


def test_what_cannot_be_shown_is_not_linked(student_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # No key (local, preview): the API answers nothing, and Russian has no
    # bundle it may show — the misaligned file (#990) never reaches a reader.
    monkeypatch.setattr(scripture, "fetch_verse", _from_api({}))
    r = student_client.post("/api/v1/scripture/passages", json={"text": LESSON}, headers={"Accept-Language": "ru"})
    assert r.status_code == 200
    assert r.json() == []


def test_english_falls_back_to_the_king_james_file_and_says_so(
    student_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(scripture, "fetch_verse", _from_api({}))
    r = student_client.post(
        "/api/v1/scripture/passages", json={"text": "As John 3:16 says."}, headers={"Accept-Language": "en"}
    )
    assert r.status_code == 200
    [passage] = r.json()
    assert passage["edition"] == "kjv"
    assert passage["text"].startswith("For God so loved the world")


def test_a_stranger_cannot_use_it(anon_client: TestClient) -> None:
    r = anon_client.post("/api/v1/scripture/passages", json={"text": "John 3:16"})
    assert r.status_code == 401


def test_a_long_reference_list_is_cut_off(student_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fetch(ref: BibleRef, locale: str) -> str:
        calls.append(str(ref))
        return "text"

    monkeypatch.setattr(scripture, "fetch_verse", fetch)
    text = " ".join(f"Ps 119:{n}" for n in range(1, 101))
    r = student_client.post("/api/v1/scripture/passages", json={"text": text}, headers={"Accept-Language": "ru"})
    assert r.status_code == 200
    assert len(r.json()) == scripture.MAX_REFERENCES
    assert len(calls) == scripture.MAX_REFERENCES
