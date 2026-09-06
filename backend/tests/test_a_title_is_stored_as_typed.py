"""A course called "Faith & Works" is called that in the database too.

Until 2026-09-05 the title of a course, module or chapter went through
``sanitize_string`` — bleach — which escapes the text it lets through.
``Faith & Works`` was stored as ``Faith &amp; Works``; the teacher saw the
entity in the title box and the students saw it on the card, and there was
no way to write it out, because every save escaped it again. Titles are
one line of text rendered as text: tags come off, nothing is escaped, and
saving what came back changes nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

PREFIX = "/api/v1/courses"


def _course(client: TestClient, title: str) -> dict:
    response = client.post(PREFIX, json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


class TestAnAmpersandInATitle:
    def test_a_course_keeps_its_ampersand(self, client: TestClient) -> None:
        course = _course(client, "Faith & Works")
        assert course["title"] == "Faith & Works"
        assert client.get(f"{PREFIX}/{course['id']}").json()["title"] == "Faith & Works"

    def test_saving_the_title_back_changes_nothing(self, client: TestClient) -> None:
        # The round trip the teacher's form makes: read, edit nothing, save.
        course = _course(client, "Вопросы & ответы")
        again = client.put(f"{PREFIX}/{course['id']}", json={"title": course["title"]})
        assert again.status_code == 200, again.text
        assert again.json()["title"] == "Вопросы & ответы"

    def test_a_module_keeps_its_ampersand(self, client: TestClient) -> None:
        course = _course(client, "Course")
        module = client.post(f"{PREFIX}/{course['id']}/modules", json={"title": "Law & Grace"})
        assert module.status_code == 201, module.text
        assert module.json()["title"] == "Law & Grace"
        renamed = client.put(f"{PREFIX}/{course['id']}/modules/{module.json()['id']}", json={"title": "Law & Grace"})
        assert renamed.status_code == 200, renamed.text
        assert renamed.json()["title"] == "Law & Grace"

    def test_a_chapter_keeps_its_ampersand(self, client: TestClient) -> None:
        course = _course(client, "Course")
        module = client.post(f"{PREFIX}/{course['id']}/modules", json={"title": "Module"}).json()
        chapter = client.post(
            f"{PREFIX}/{course['id']}/modules/{module['id']}/chapters",
            json={"title": "Q & A <session 1>", "chapter_type": "reading", "order_index": 1},
        )
        assert chapter.status_code == 201, chapter.text
        assert chapter.json()["title"] == "Q & A"


class TestMarkupInATitle:
    def test_tags_come_off_and_nothing_is_escaped(self, client: TestClient) -> None:
        course = _course(client, '<b>Intro</b> to <a href="https://x.test">Acts</a>')
        assert course["title"] == "Intro to Acts"

    def test_a_script_is_neither_stored_nor_escaped(self, client: TestClient) -> None:
        course = _course(client, "Acts<script>alert(1)</script>")
        title = course["title"]
        assert "<" not in title
        assert "&lt;" not in title
        assert "script" not in title

    def test_a_module_title_is_no_longer_stored_raw(self, client: TestClient) -> None:
        # Module titles had no sanitiser at all before this.
        course = _course(client, "Course")
        module = client.post(f"{PREFIX}/{course['id']}/modules", json={"title": "<img src=x onerror=alert(1)>Week 1"})
        assert module.status_code == 201, module.text
        assert module.json()["title"] == "Week 1"
