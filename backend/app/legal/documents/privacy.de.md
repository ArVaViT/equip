# Datenschutzerklärung

**Fassung 2.0 · in Kraft ab 17. September 2026**

Equip ist eine Plattform für Bibelschulen. Dieses Dokument legt dar, was die
Plattform speichert, warum, wer es sehen kann, wie lange es aufbewahrt wird und
wie man es mitnehmen oder löschen lassen kann. Es ist für Menschen geschrieben,
nicht für Juristen.

Es ist länger als die Fassung davor, und das mit Absicht: Die vorige Fassung
beschrieb weniger, als die Plattform tatsächlich tut. Alles, was hier genannt
wird, ist etwas, das die Software heute tut, geprüft am Code und am laufenden
System.

## Wer wir sind

Equip ist ein nicht-kommerzielles Projekt, keine Firma. Hinter der Plattform
stehen Menschen und keine juristische Person, und Fragen gehen an
**supportequip@gmail.com**. Wir sagen das offen, weil es sich zu wissen lohnt,
bevor Sie sich anmelden: In einem Streit gibt es niemanden, an den man sich über
uns hinaus wenden könnte.

## Was wir speichern

**Was Sie selbst eingeben.** Name, E-Mail-Adresse, Profilfoto, bevorzugte
Sprache. Ihr Name steht auf Zertifikaten und Notenblättern, also sollte es der
Name sein, unter dem Sie festgehalten werden wollen.

**Was Sie in einem Kurs tun.** Gelesene Lektionen, Quiz-Antworten, eingereichte
Arbeiten, Noten und Rückmeldungen der Lehrenden, erworbene Zertifikate und die
Erklärungen, die Sie zu Ihrer eigenen Arbeit abgeben.

**Was Lehrende hochladen.** Dateien, Texte und Bilder, die eine lehrende Person
oder ein Direktor einem Kurs hinzufügt, und deren maschinelle Übersetzungen.

**Aufzeichnungen darüber, dass etwas geschehen ist.** Ein Aktivitätsprotokoll der
Handlungen auf der Plattform — wer einen Kurs angelegt hat, wer eine Note
geändert hat, wer wen eingeschrieben hat. Seit September 2026 enthält dieses
Protokoll **keine IP-Adresse und keine Browser-Kennung**; es enthält wer, was und
wann.

**IP-Adressen, in zwei Momenten.** Wenn Sie ein Dokument wie dieses annehmen und
wenn Sie eine Arbeit mit einer beigefügten Erklärung abgeben. Die IP wird genau
deshalb gespeichert, damit sich zeigen lässt, dass eine Annahme und eine
Erklärung tatsächlich abgegeben wurden. Sie wird für nichts anderes verwendet,
und nichts anderes, was Sie auf der Plattform tun, schreibt Ihre IP in unsere
Datenbank.

**Ihre Anmeldesitzungen.** Unser Authentifizierungs-Anbieter (Supabase)
protokolliert für jede aktive Sitzung die **IP-Adresse und den
Browser-User-Agent**, von denen aus sie gestartet wurde. Das gehört dazu, wie die
Anmeldung funktioniert, und ist nichts, was wir einschalten. Ein Sitzungseintrag
lebt so lange wie die Sitzung; das Abmelden beendet ihn.

## Was die Plattform darüber aufzeichnet, wie Sie sie nutzen

Dieser Abschnitt beschreibt die Messung, und das ist der Teil, den die meisten
Erklärungen vage lassen. Unsere tut das nicht, denn beides ist hier ganz
aufgedreht.

**Sitzungsaufzeichnung im Frontend (Datadog Real User Monitoring).** Jede Sitzung
wird aufgezeichnet — **100 % der Sitzungen, und 100 % davon mit Session Replay
(Sitzungsaufzeichnung)**, das rekonstruiert, was im Browser geschah, als
abspielbares Bild der Seite. Konkret:

- **Text, der auf Ihrem Bildschirm sichtbar war, ist in der Aufzeichnung.**
  Überschriften, Schaltflächen, Menüs, die geöffnete Lektion, eine auf einer
  Seite angezeigte Note — all das.
- **Text, den Sie in ein Feld getippt haben, ist es nicht.** Jedes Eingabefeld,
  jedes Textfeld und jeder editierbare Bereich wird maskiert, bevor irgendetwas
  den Browser verlässt (`mask-user-input`), sodass Quiz-Antworten, Aufsatztexte,
  Suchfelder und Passwörter in der Aufzeichnung durch Platzhalter ersetzt sind.
  Sobald Ihre Antwort Ihnen aber auf einer Ergebnisseite *zurück angezeigt* wird,
  ist sie angezeigter Text, und angezeigter Text wird aufgezeichnet.
- **Ebenfalls aufgezeichnet:** die Seiten, die Sie besucht haben, und in welcher
  Reihenfolge, Klicks, Scrollen und Tipp-*Ereignisse* (dass eine Taste gedrückt
  wurde, nicht welche), wie lange das Laden gedauert hat, JavaScript-Fehler und
  die Netzwerkanfragen, die die Seite gestellt hat.
- **Sie sind darin identifiziert.** Wenn Sie angemeldet sind, trägt die Sitzung
  Ihre Nutzer-ID, Ihre E-Mail-Adresse und Ihren Namen, damit ein Fehlerbericht
  der Person zugeordnet werden kann, die darauf gestoßen ist.
- Sie dient dazu, Kaputtes zu finden und zu reparieren. Sie wird nicht verkauft,
  nicht an Werbetreibende weitergegeben und nicht dazu benutzt, ein Profil von
  Ihnen zu bauen.

**Server- und Anfrageprotokolle.** Anfragen an die Website und an die API laufen
über unseren Hosting-Anbieter (Vercel) und werden zu Datadog gestreamt. Diese
Anfrageprotokolle **enthalten die IP-Adresse**, von der die Anfrage kam, dazu den
Pfad, den Antwortcode und die Zeiten. Das ist Infrastruktur-Protokollierung und
nicht etwas, das wir über Sie aufzeichnen wollten, aber es ist Ihre IP, und Sie
sollten wissen, dass sie dort ist. Sie werden **15 Tage** aufbewahrt und dann
durch Ablauf gelöscht.

**Keine Werbung, keine Tracking-Pixel, keine Analyse durch Dritte.** Es gibt kein
Werbenetzwerk, kein Marketing-Tag, kein seitenübergreifendes Tracking und kein
Tracking-Pixel in der E-Mail, die die Plattform versendet. Die oben beschriebene
Messung ist alles.

**Cookies und lokaler Speicher.** Die Plattform setzt, was sie braucht, um Sie
angemeldet zu halten und sich Ihre Sprache und ein paar Anzeigeeinstellungen zu
merken. Es gibt keine Werbe- oder seitenübergreifenden Cookies.

## Wohin Ihre Daten außerhalb der Plattform gehen

Die Plattform läuft auf Infrastruktur, die wir mieten. Jeder Anbieter verarbeitet
Daten nach unseren Weisungen und in unserem Auftrag; keiner besitzt sie, und
keiner darf sie für eigene Zwecke nutzen. **Wer sie jeweils sind, steht unter
[/privacy/providers](/privacy/providers)**, mit dem Datum, an dem sich diese
Liste zuletzt geändert hat. Was sie tun, steht hier, denn das ist der Teil, der
ein Versprechen ist:

- **Supabase** — die Datenbank, die Anmeldung und die hochgeladenen Dateien.
  Alles, was die Plattform speichert, wird dort gespeichert, einschließlich des
  oben beschriebenen Sitzungseintrags mit Ihrer IP und Ihrem User-Agent.
- **Vercel** — liefert die Website und die API aus; sieht jede Anfrage,
  einschließlich ihrer IP-Adresse.
- **Datadog** — technische Protokolle, Fehlerberichte und die oben beschriebenen
  Sitzungsaufzeichnungen.
- **Google (Gemini)** — **Kursinhalte werden an Googles Gemini-Modelle gesendet,
  um maschinell übersetzt zu werden** in die vier Sprachen, die die Plattform
  bedient. Gesendet wird von Lehrenden verfasstes Kursmaterial: Titel,
  Lektionstexte, Quiz-Fragen, Ankündigungen. **Eingereichte Arbeiten von
  Studierenden werden niemals gesendet** — nicht zur Übersetzung und auch sonst
  für nichts.
- **Google (Anmeldung)** — nur wenn Sie „Weiter mit Google“ verwenden, und nur,
  um Sie zu authentifizieren.
- **YouVersion** — die Plattform fragt die YouVersion-Bibel-API nach dem Text
  einer Bibelstelle, damit eine in einer Lektion zitierte Stelle die echte Stelle
  ist. Sie wird nach einer Stellenangabe gefragt; ihr wird nicht gesagt, wer
  gefragt hat.
- **Resend** — versendet die E-Mail der Plattform. Resend hält die Adresse, an
  die die Nachricht ging, ihren Betreff und Text sowie die Information, ob sie
  angenommen wurde.

Wenn ein Anbieter jemals durch einen anderen ersetzt wird, der dieselbe Aufgabe
erfüllt, ändert sich die Liste und das Datum darauf rückt vor. Das ist keine
Änderung dieser Erklärung; siehe **Änderungen** unten.

## Wer es innerhalb der Plattform sehen kann

- **Die Lehrenden Ihres Kurses** — Ihre Arbeiten, Antworten, Noten und
  Fortschritte.
- **Der Direktor oder Administrator Ihrer Schule** — dasselbe, dazu
  Studierendenlisten und Notenblätter.
- **Andere Studierende** — nur Ihren Namen und Ihr Foto, und nur dort, wo das
  Teil der Kursarbeit selbst ist (etwa eine Bewertung, die Sie zu einem Kurs
  hinterlassen haben).
- **Die Menschen, die die Plattform betreiben** — technisch kann jeder, der die
  Datenbank verwaltet, sehen, was darin ist. Wir schauen hinein, wenn etwas
  kaputt ist oder wenn jemand ein Problem meldet, sonst nicht.
- **Sonst niemand.** Wir verkaufen keine Daten, geben sie nicht an
  Werbetreibende und teilen sie mit keinen Dritten über die oben genannten
  Anbieter hinaus.

Wir geben Daten heraus, wenn das Gesetz es verlangt — ein Gerichtsbeschluss, ein
rechtmäßiges Verlangen einer Behörde — und wir sagen es Ihnen, wenn wir das
dürfen.

## Wie lange wir es aufbewahren

| Was | Wo es liegt | Wie lange |
|---|---|---|
| Konto und Profil — Name, E-Mail, Foto, Sprache | Supabase | Solange das Konto besteht |
| Kursarbeit — Fortschritt, Quiz-Antworten, eingereichte Arbeiten, Noten, Rückmeldungen | Supabase | Solange das Konto besteht; wird mit ihm gelöscht |
| Ausgestellte Zertifikate und die Notenblätter, die sie festhalten | Supabase | **Bleibt nach Löschung des Kontos** — siehe unten |
| Nachweis der Annahme eines Dokuments wie diesem (Fassung, Prüfsumme, Sprache, Zeit, IP) | Supabase | Solange das Konto besteht |
| Erklärung zu einer eingereichten Arbeit (Aussage, KI-Nutzung, Zeit, IP) | Supabase | Solange die eingereichte Arbeit besteht |
| Aktivitätsprotokoll der Handlungen — wer wann was getan hat (keine IP) | Supabase | Bleibt; wird heute nicht planmäßig gelöscht |
| Benachrichtigungen, die Ihnen in der Plattform angezeigt werden | Supabase | Bleibt; wird heute nicht planmäßig gelöscht |
| Hochgeladene Kursdateien | Supabase Storage | Bis die lehrende Person oder die Schule sie entfernt |
| Eintrag zur Anmeldesitzung — IP und User-Agent | Supabase Auth | Solange die Sitzung lebt; endet beim Abmelden |
| Server- und Anfrageprotokolle, einschließlich IP | Datadog | **15 Tage** |
| Sitzungsaufzeichnungen und Replays im Frontend | Datadog | **30 Tage** (Datadogs Speicherdauer für diese Daten) |
| Gesendete E-Mail — Adresse, Betreff, Text, Zustellergebnis | Resend | Wird von Resend nach dessen eigener Speicherdauer gehalten; wir behalten keine Kopie in unserer Datenbank |
| Datenbank-Backups | Supabase | Ein kurzes rollierendes Fenster nach unserem Tarif — eine Löschung wird endgültig, wenn die Backups, die sie noch enthalten, ablaufen |

Wo in einer Zeile steht „wird heute nicht planmäßig gelöscht“, ist das der
ehrliche Stand: Die Plattform ist jung, und es läuft noch kein Aufräum-Job. Wenn
einer läuft, ändert sich diese Tabelle, und die Änderung wird mitgeteilt statt
neu unterschrieben, denn eine kürzere Speicherdauer ist für Sie kein schlechteres
Geschäft.

**Das eine, was Ihr Konto überdauert.** Ein ausgestelltes Zertifikat und das
Notenblatt, das es festhält, bleiben. Eine Schule kann nicht rückwirkend
unbezeugt machen, was sie bereits bezeugt hat, und genau deshalb sind diese
Dokumente als Momentaufnahme zum Zeitpunkt ihrer Ausstellung eingefroren. Alles
andere geht.

## Was Sie tun können

- **Ihre Daten sehen und ändern** — in Ihrem Profil, für das, was das Profil
  enthält.
- **Eine Kopie von allem bekommen, was über Sie gespeichert ist** — schreiben Sie
  an supportequip@gmail.com, und wir stellen es zusammen und senden es. Einen
  Export-Knopf zur Selbstbedienung gibt es noch nicht.
- **Ihr Konto und Ihre Kursarbeit löschen** — schreiben Sie an
  supportequip@gmail.com. Wir tun es heute von Hand; einen Löschen-Knopf im
  Profil gibt es noch nicht. Ausgestellte Zertifikate bleiben, wie oben vermerkt.
- **Etwas berichtigen, das falsch ist** — sagen Sie es uns, und wir bringen es in
  Ordnung.
- **Der Sitzungsaufzeichnung widersprechen** — wir können sie heute nicht für ein
  einzelnes Konto abschalten. Wenn das für Sie nicht hinnehmbar ist, ist das
  Löschen des Kontos das ehrliche Mittel, und wir machen es Ihnen nicht schwer.
- **Die Einwilligung widerrufen** — was bedeutet, das Konto zu löschen: Die
  Plattform zu nutzen, ohne diesem Dokument zuzustimmen, ist technisch nicht
  möglich.

Wir beantworten das innerhalb von 30 Tagen.

## Alter

Selbst anmelden können Sie sich ab **16**. Jüngere Studierende werden von einem
Administrator der Schule eingeschrieben, und in diesem Fall ist die Einwilligung
der Eltern Sache der Schule — sie kennt die Familie und wir nicht.

## E-Mail, die die Plattform versendet

Drei Arten, und keine anderen:

- **Konto-E-Mail** — Bestätigung Ihrer Adresse, Zurücksetzen Ihres Passworts,
  eine Einladung, die Ihnen jemand geschickt hat. Sie lässt sich nicht
  abschalten; ohne sie kann ein Konto nicht genutzt werden.
- **Kurs-E-Mail und Benachrichtigungen** — Dinge, bei denen es Ihnen schlechter
  ginge, sie nicht zu wissen: eine Sitzung, die gleich beginnt, ein entschiedenes
  Zertifikat, eine zurückgegebene Arbeit, eine verschobene Frist, eine
  Ankündigung aus Ihrem Kurs. Jede Art lässt sich in Ihrem Profil abschalten, und
  jede solche Nachricht enthält einen Abmeldelink.
- **Sonst nichts.** Keine Newsletter, keine Produktankündigungen, kein Marketing
  und kein Verkauf oder Vermieten Ihrer Adresse an irgendwen.

## Dinge, die später kommen könnten

Hier genannt, damit ihr Hinzufügen eine Mitteilung ist und nicht eine weitere
Unterschriftsrunde — und jedes davon wird, wenn es kommt, hier vollständig
beschrieben, bevor es die Daten von irgendjemandem berührt:

- **Kostenpflichtige Kurse.** Wenn eine Schule jemals für einen Kurs Geld
  verlangt, wird ein Zahlungsanbieter die Zahlung abwickeln. **Wir werden Ihre
  Kartennummer niemals halten**; der Anbieter wird es, und er wird in der
  Anbieterliste genannt, mit dem, was er hält. Heute gibt es auf der Plattform
  keine Zahlungen, und wir speichern keine Zahlungsdaten.
- **Anderswo gehostete Videos.** Eine Lektion kann ein Video von einem
  Drittanbieter einbetten (heute YouTube, per Link). Es abzuspielen ist ein
  Besuch bei diesem Dienst, nach dessen eigenen Bedingungen, und er sieht Ihre
  Anfrage.
- **Weniger Dinge, früher.** Speicherdauern können auf diesem Weg nur kürzer
  werden; eine längere ist eine wesentliche Änderung.

## Änderungen dieser Erklärung

**Eine wesentliche Änderung erfordert Ihre Zustimmung.** Sie werden gebeten, die
neue Fassung anzunehmen, bevor Sie weitermachen können. Eine Änderung ist
wesentlich, wenn sie eines von diesen tut:

- fügt eine Kategorie von Daten hinzu, die wir erheben, oder einen neuen Zweck
  für Daten, die wir bereits haben;
- erweitert, wer Ihre Daten sehen kann, innerhalb der Plattform oder außerhalb;
- fügt einen Anbieter hinzu, der eine Kategorie von Daten hält, die vorher kein
  Anbieter hielt, oder sie zu einem neuen Zweck hält;
- verlängert, wie lange etwas aufbewahrt wird;
- nimmt eines der unter **Was Sie tun können** aufgeführten Rechte weg.

**Alles andere wird mitgeteilt, nicht neu unterschrieben.** Einen Anbieter gegen
einen anderen zu tauschen, der dieselbe Aufgabe erfüllt, eine Speicherdauer zu
verkürzen, ein neues Recht hinzuzufügen, einen Fehler zu berichtigen oder
dasselbe klarer zu sagen — das tritt in Kraft, wenn die neue Fassung
veröffentlicht wird, und Sie erfahren davon innerhalb der Plattform. Die
Anbieterliste steht genau aus diesem Grund auf einer eigenen Seite: Ein Wechsel
des Lieferanten verschiebt kein Versprechen, und daraus eine neue
Unterschriftsrunde zu machen, würde Menschen darauf trainieren, sich durch einen
Einwilligungsbildschirm zu klicken, ohne zu lesen — das Gegenteil dessen, wofür
Einwilligung da ist.

Jede Fassung wird mit dem Datum ihres Inkrafttretens und einer Prüfsumme ihres
Textes gespeichert, und der Nachweis dessen, was Sie angenommen haben, nennt
diese Fassung und diese Prüfsumme. Alte Fassungen werden nie umgeschrieben.

## Sprachen

Dieses Dokument wird auf Englisch, Russisch, Deutsch und Ukrainisch
veröffentlicht. Die Übersetzungen gibt es, damit alle lesen können, wozu sie
zustimmen, und sie sollen dasselbe sagen. **Wenn sie voneinander abweichen, gilt
die englische Fassung** — außer wo das Recht des Landes, in dem Sie leben, etwas
anderes sagt.

## Recht

Die Plattform wird aus den Vereinigten Staaten (Indiana) betrieben, und das Recht
dieses Bundesstaates gilt für dieses Dokument. Wenn Sie an einem Ort leben,
dessen Datenschutzrecht Ihnen Rechte gibt, auf die nicht verzichtet werden kann,
verzichtet dieses Dokument nicht darauf.

## Kontakt

**supportequip@gmail.com**
