# Datenschutzerklärung

**Fassung 2.0 · in Kraft ab 17. September 2026**

Equip ist eine Plattform für Bibelschulen. Dieses Dokument legt dar, was die
Plattform speichert, warum, wer es sehen kann, wie lange es aufbewahrt wird und
wie man es mitnimmt oder löschen lässt. Es ist für Menschen geschrieben, nicht
für Juristen.

Es ist länger als die Fassung davor, und das mit Absicht: Die vorige Fassung
beschrieb weniger, als die Plattform tatsächlich tut. Alles, was hier genannt
ist, tut die Software heute, geprüft am Code und am laufenden System.

## Wer wir sind

Equip ist ein nicht-kommerzielles Projekt, kein Unternehmen. Hinter der
Plattform stehen Menschen und keine juristische Person, und Fragen gehen an
**supportequip@gmail.com**. Wir sagen das offen, weil es vor der Anmeldung zu
wissen lohnt: In einem Streit gibt es niemanden außer uns, an den man sich
wenden kann.

**Wer entscheidet, was mit Ihren Daten geschieht.** Für Ihr Konto und für den
Betrieb der Plattform sind das wir — in der Sprache des Datenschutzes sind wir
der Verantwortliche, und supportequip@gmail.com ist die Adresse für jede Frage,
jeden Antrag und jede Beschwerde dazu. Für Ihre Kursarbeiten, Ihre Noten und
Ihren Fortschritt entscheidet die Schule, die Sie unterrichtet: Die Schule ist
der Verantwortliche, und wir handeln auf ihre Weisung, was die
[Schulvereinbarung](/school-agreement) darlegt. In der Praxis schreiben Sie in
beiden Fällen uns, und wir klären, wer von uns antwortet.

**Wenn wir es falsch machen.** Sagen Sie es zuerst uns — uns ist lieber, wir
bringen es in Ordnung, als dass es uns jemand anderes sagt. Aber wenn Sie im
Europäischen Wirtschaftsraum oder im Vereinigten Königreich sind, haben Sie
auch das Recht, sich bei der Datenschutzaufsichtsbehörde des Landes zu
beschweren, in dem Sie leben, und Sie brauchen dafür weder unsere Erlaubnis
noch unser Einverständnis.

## Was wir speichern

**Was Sie selbst eingeben.** Name, E-Mail-Adresse, Profilfoto, bevorzugte
Sprache. Ihr Name wird auf Zertifikate und Notenblätter gedruckt, es sollte
also der Name sein, unter dem Sie verzeichnet werden wollen.

**Was Sie in einem Kurs tun.** Gelesene Lektionen, Quizantworten, eingereichte
Arbeiten, Noten und Rückmeldungen der Lehrenden, erworbene Zertifikate und die
Erklärungen, die Sie über Ihre eigene Arbeit abgeben.

**Was Lehrende hochladen.** Dateien, Texte und Bilder, die Lehrende oder
Direktoren einem Kurs hinzufügen, und die maschinellen Übersetzungen davon.

**Nachweise, dass etwas geschehen ist.** Ein Aktivitätsprotokoll der
Handlungen auf der Plattform — wer einen Kurs angelegt, wer eine Note geändert,
wer wen eingeschrieben hat. Seit September 2026 enthält dieses Protokoll
**keine IP-Adresse und keine Browserkennung**; es enthält wer, was und wann.

**IP-Adressen, in zwei Momenten.** Wenn Sie ein Dokument wie dieses annehmen
und wenn Sie eine Arbeit mit einer beigefügten Erklärung abgeben. Die IP wird
genau deshalb gespeichert, damit sich zeigen lässt, dass eine Annahme und eine
Erklärung tatsächlich abgegeben wurden. Sie wird für nichts anderes genutzt,
und nichts sonst, was Sie auf der Plattform tun, schreibt Ihre IP in unsere
Datenbank.

**Ihre Anmeldesitzungen.** Unser Authentifizierungsanbieter (Supabase) hält für
jede aktive Sitzung die **IP-Adresse und den Browser-User-Agent** fest, von dem
aus sie begonnen wurde. Das gehört dazu, wie die Anmeldung funktioniert, und
ist nichts, was wir einschalten. Ein Sitzungseintrag lebt so lange wie die
Sitzung; das Abmelden beendet ihn.

## Was die Plattform über Ihre Nutzung aufzeichnet

Dieser Abschnitt beschreibt die Messung, und das ist der Teil, den die meisten
Erklärungen vage lassen. Unsere tut das nicht, denn beides ist hier voll
aufgedreht.

**Sitzungsaufzeichnung im Frontend (Datadog Real User Monitoring).** Jede
Sitzung wird aufgezeichnet — **100 % der Sitzungen, und 100 % davon mit Session
Replay**, das nachbildet, was im Browser geschehen ist, als abspielbares Bild
der Seite. Konkret:

- **Text, der auf Ihrem Bildschirm sichtbar war, ist in der Aufzeichnung.**
  Überschriften, Schaltflächen, Menüs, die geöffnete Lektion, eine auf einer
  Seite gezeigte Note — alles davon.
- **Text, den Sie in ein Feld getippt haben, nicht.** Jedes Eingabefeld, jedes
  Textfeld und jeder bearbeitbare Bereich wird maskiert, bevor irgendetwas den
  Browser verlässt (`mask-user-input`), sodass Quizantworten, Aufsatztexte,
  Suchfelder und Passwörter in der Aufzeichnung durch Platzhalter ersetzt sind.
  Sobald Ihre Antwort Ihnen aber auf einer Ergebnisseite *zurückgezeigt* wird,
  ist sie angezeigter Text, und angezeigter Text wird aufgezeichnet.
- **Ebenfalls aufgezeichnet:** die besuchten Seiten und in welcher Reihenfolge,
  Klicks, Scrollen und Tipp-*Ereignisse* (dass eine Taste gedrückt wurde, nicht
  welche), wie lange Dinge zum Laden brauchten, JavaScript-Fehler und die
  Netzwerkanfragen der Seite.
- **Sie sind darin identifiziert.** Wenn Sie angemeldet sind, trägt die Sitzung
  Ihre Nutzerkennung, Ihre E-Mail-Adresse und Ihren Namen, damit ein
  Fehlerbericht der Person zugeordnet werden kann, die darauf gestoßen ist.
- Sie dient dazu, Ausfälle zu finden und zu beheben. Sie wird nicht verkauft,
  nicht mit Werbetreibenden geteilt und nicht dazu genutzt, ein Profil von
  Ihnen zu bauen.

**Server- und Anfrageprotokolle.** Anfragen an die Website und an die API laufen
über unseren Hosting-Anbieter (Vercel) und werden zu Datadog gestreamt. Diese
Anfrageprotokolle **enthalten die IP-Adresse**, von der die Anfrage kam, dazu
den Pfad, den Antwortcode und die Zeiten. Das ist Infrastrukturprotokollierung
und nichts, was wir uns über Sie aufzuzeichnen ausgesucht hätten, aber es ist
Ihre IP, und Sie sollten wissen, dass sie dort steht. Sie werden **15 Tage**
aufbewahrt und laufen dann ab.

**Keine Werbung, keine Zählpixel, keine Analyse durch Dritte.** Es gibt kein
Werbenetzwerk, kein Marketing-Tag, kein seitenübergreifendes Tracking und kein
Zählpixel in den E-Mails, die die Plattform sendet. Die oben beschriebene
Messung ist alles.

**Cookies und lokaler Speicher.** Die Plattform setzt, was sie braucht, um Sie
angemeldet zu halten und sich Ihre Sprache und ein paar
Anzeigeeinstellungen zu merken. Es gibt keine Werbe- oder
seitenübergreifenden Cookies.

## Wohin Ihre Daten außerhalb der Plattform gehen

Die Plattform läuft auf Infrastruktur, die wir mieten. Jeder Anbieter
verarbeitet Daten auf unsere Weisung und in unserem Auftrag; keiner besitzt
sie, und keiner darf sie für eigene Zwecke nutzen. **Wer sie in einem gegebenen
Moment sind, ist die Liste unter
[/privacy/providers](/privacy/providers), und sie ist Teil dieser Erklärung** —
eine Anlage dazu, kein Faltblatt daneben. Was sie tun, steht hier, weil das der
Teil ist, der ein Versprechen ist:

- **Supabase** — die Datenbank, die Anmeldung und hochgeladene Dateien. Alles,
  was die Plattform speichert, liegt dort, einschließlich des oben
  beschriebenen Sitzungseintrags mit Ihrer IP und Ihrem User-Agent.
- **Vercel** — liefert die Website und die API aus; sieht jede Anfrage,
  einschließlich ihrer IP-Adresse.
- **Datadog** — technische Protokolle, Fehlerberichte und die oben
  beschriebenen Sitzungsaufzeichnungen.
- **Google (Gemini)** — **Kursinhalte werden an Googles Gemini-Modelle gesendet,
  um maschinell übersetzt zu werden**, in die vier Sprachen, die die Plattform
  bedient. Gesendet wird von Lehrenden verfasstes Kursmaterial: Titel,
  Lektionstexte, Quizfragen, Ankündigungen. **Von Studierenden eingereichte
  Arbeiten werden niemals gesendet** — weder zur Übersetzung noch für sonst
  etwas. Wir nutzen bewusst den **kostenpflichtigen** Tarif, und genau darauf
  kommt es hier an: Auf dem kostenpflichtigen Tarif sagen Googles eigene
  Bedingungen, dass es **Eingaben und Antworten nicht zur Verbesserung seiner
  Produkte verwendet**, sie nur für eine begrenzte Zeit und nur zur Erkennung
  von Verstößen gegen seine Nutzungsrichtlinie protokolliert und sie nicht von
  Menschen lesen lässt, um seine Modelle zu verbessern. Auf dem kostenlosen
  Tarif ist alles drei umgekehrt. Sollten wir je vom kostenpflichtigen Tarif
  weggehen, wäre dieser Absatz nicht mehr wahr — und das haben wir uns in der
  Anbieter-Anlage als Selbstverpflichtung aufgeschrieben.
- **Google (Anmeldung)** — nur wenn Sie „Weiter mit Google“ nutzen, und nur, um
  Sie zu authentifizieren.
- **YouVersion** — die Plattform fragt die YouVersion-Bibel-API nach dem Text
  eines Verses, damit eine in einer Lektion zitierte Stelle die echte Stelle
  ist. Sie wird nach einer Stelle gefragt; wer fragt, erfährt sie nicht.
- **Resend** — versendet die E-Mails der Plattform. Resend hält die Adresse, an
  die die Nachricht ging, ihren Betreff und ihren Text sowie ob sie angenommen
  wurde.

**Wenn sich diese Liste ändert, sagen wir es Ihnen.** Einen Anbieter
hinzuzunehmen oder einen gegen einen anderen mit derselben Aufgabe zu tauschen,
wird in der Anlage mit dem Datum der Änderung veröffentlicht und Ihnen
innerhalb der Plattform angekündigt, 60 Tage bevor es in Kraft tritt. Sie
müssen dem nicht zustimmen — die Versprechen dieser Erklärung haben sich nicht
bewegt —, aber Sie erfahren es rechtzeitig, um zu widersprechen, uns danach zu
fragen oder Ihr Konto zu schließen, wenn die Antwort Sie nicht
zufriedenstellt. Schreiben Sie an supportequip@gmail.com; wir antworten. *Kein*
bloßer Lieferantenwechsel ist ein Anbieter, der eine Kategorie von Daten halten
würde, die bisher kein Anbieter hielt, oder sie zu einem neuen Zweck hält. Das
ist eine Änderung dieser Erklärung selbst, und sie kommt mit einer neuen
Fassung und einer erneuten Bitte um Zustimmung.

**Wo das alles liegt, und was den Weg absichert.** Jeder Anbieter oben sitzt in
den Vereinigten Staaten, und die Plattform wird von dort betrieben, die Nutzung
bedeutet also, dass Ihre Daten in den Vereinigten Staaten verarbeitet werden.
Wenn Sie im Europäischen Wirtschaftsraum oder im Vereinigten Königreich sind,
ist das eine Übermittlung aus Ihrem Land heraus, und der Vertrag zur
Auftragsverarbeitung des jeweiligen Anbieters sagt, was sie schützt:

- **Supabase** — die EU-Standardvertragsklauseln, die sein Vertrag durch unsere
  Annahme als unterzeichnet behandelt, dazu ein UK-Zusatz.
- **Vercel** — die Standardvertragsklauseln, in dem Modul, das zu den jeweiligen
  Rollen passt. Sie gelten für Pro- und Enterprise-Tarife; unserer ist Pro.
- **Datadog** — die Standardvertragsklauseln und der UK-Zusatz zur
  internationalen Datenübermittlung, beide ohne gesonderte Unterschrift im
  Vertrag enthalten.
- **Resend** — Zertifizierung nach dem EU–U.S. Data Privacy Framework samt
  UK-Erweiterung **und** zusätzlich die Standardvertragsklauseln.
- **Google** — Empfänger ist **Google LLC**, zertifiziert nach dem **EU–U.S.
  Data Privacy Framework** und dessen UK-Erweiterung. Diese Zertifizierung ist
  für sich genommen eine Rechtsgrundlage für die Übermittlung — sie stützt sich
  auf den Angemessenheitsbeschluss der Europäischen Kommission —, unabhängig
  davon, welchen Vertrag wir mit ihnen haben. Getrennt davon und ehrlich: Ob
  Googles Cloud Data Processing Addendum gerade Google AI Studio abdeckt, konnten
  wir nicht bestätigen, weil sich die vollständigen Anlagen über das Web nicht
  öffnen lassen. Das ist eine Frage unseres Vertrags, nicht der Rechtsgrundlage,
  und es berührt die Rechtmäßigkeit der Übermittlung nicht.

**Warum wir halten, was wir halten.** Für das Recht, das diese Frage direkt
stellt: Wir verarbeiten Ihr Konto und Ihre Kursarbeiten, um die Plattform
bereitzustellen, um die Sie gebeten haben, und um zu erfüllen, was in diesen
Dokumenten vereinbart ist; wir verarbeiten technische Protokolle,
Fehlerberichte und Sitzungsaufzeichnungen auf der Grundlage unseres
berechtigten Interesses an einer Plattform, die funktioniert und die sich
reparieren lässt, abgewogen gegen die ehrliche Beschreibung oben; wir
verarbeiten, was eine Schule uns gibt, auf Weisung dieser Schule; und wo wir Sie
je um eine Einwilligung bitten, bitten wir gesondert darum, und Sie können sie
zurücknehmen. Wir verkaufen nichts, und es gibt hier keine Verarbeitung für
Werbung.

**Woher Ihre Daten kommen, wenn sie nicht von Ihnen kommen.** Meist tippen Sie
sie ein. Aber ein Schul-Administrator kann Studierende einschreiben, und das
heißt, dass die Schule uns Name und E-Mail-Adresse dieser Person gibt, bevor
diese Person uns irgendetwas gegeben hat. Wenn Ihr Konto so entstanden ist, ist
die Schule seine Herkunft, und Sie können uns genau wie alle anderen fragen,
was wir über Sie halten.

## Wer es innerhalb der Plattform sehen kann

- **Ihre Kurslehrenden** — Ihre Arbeiten, Antworten, Noten und Fortschritte.
- **Der Direktor oder Administrator Ihrer Schule** — dasselbe, dazu
  Studierendenlisten und Notenblätter.
- **Andere Studierende** — nur Ihren Namen und Ihr Foto, und nur dort, wo das
  Teil der Kursarbeit selbst ist (eine Bewertung etwa, die Sie zu einem Kurs
  hinterlassen haben).
- **Die Menschen, die die Plattform betreiben** — technisch kann jede Person,
  die die Datenbank verwaltet, sehen, was darin steht. Wir sehen hin, wenn
  etwas kaputt ist oder wenn jemand ein Problem meldet, sonst nicht.
- **Jede Person, die eine Ihrer Zertifikatsnummern hat.** Ein Zertifikat wird
  unter `equipbible.com/verify/<number>` geprüft, ohne Konto und ohne Anmeldung,
  und die Antwort zeigt **den Namen, auf den es ausgestellt wurde, den Kurstitel
  und das Datum**. Das ist es, was ein Zertifikat wertvoll macht; es heißt aber
  auch, dass diese drei Dinge für jede Person sichtbar sind, der Sie die Nummer
  geben, und für jede Person, der diese sie weitergibt. Sonst wird nichts über
  Sie gezeigt, und eine Nummer, die zu nichts passt, zeigt nichts.
- **Sonst niemand.** Wir verkaufen keine Daten, geben sie nicht an
  Werbetreibende und teilen sie mit niemandem über die obigen Anbieter hinaus.

Wir geben Daten heraus, wenn das Gesetz es verlangt — eine gerichtliche
Anordnung, ein rechtmäßiges Verlangen einer Behörde —, und wir sagen es Ihnen,
wenn wir es dürfen.

## Wie lange wir es aufbewahren

| Was | Wo es liegt | Wie lange |
|---|---|---|
| Konto und Profil — Name, E-Mail, Foto, Sprache | Supabase | Solange das Konto besteht |
| Kursarbeit — Fortschritt, Quizantworten, eingereichte Arbeiten, Noten, Rückmeldungen | Supabase | Solange das Konto besteht; wird mit ihm gelöscht |
| Ausgestellte Zertifikate und die Notenblätter, die sie festhalten | Supabase | **Bleibt nach der Löschung des Kontos** — siehe unten |
| Nachweis der Annahme eines Dokuments wie dieses (Fassung, Prüfsumme, Sprache, Zeit, IP) | Supabase | Solange das Konto besteht — dann **ohne Sie darin aufbewahrt**, unbefristet (siehe unten) |
| Erklärung zu einer eingereichten Arbeit (Aussage, KI-Nutzung, Zeit, IP) | Supabase | Solange die eingereichte Arbeit besteht |
| Aktivitätsprotokoll der Handlungen — wer wann was getan hat (ohne IP) | Supabase | Wird aufbewahrt; heute keine planmäßige Löschung |
| Benachrichtigungen, die Ihnen in der Plattform gezeigt werden | Supabase | Wird aufbewahrt; heute keine planmäßige Löschung |
| Hochgeladene Kursdateien | Supabase Storage | Bis Lehrende oder die Schule sie entfernen |
| Anmeldesitzungseintrag — IP und User-Agent | Supabase Auth | Solange die Sitzung lebt; endet mit dem Abmelden |
| Server- und Anfrageprotokolle, einschließlich IP | Datadog | **15 Tage** |
| Frontend-Sitzungseinträge und Replays | Datadog | **30 Tage** (Speicherdauer von Datadog für diese Daten) |
| Gesendete E-Mails — Adresse, Betreff, Text, Zustellergebnis | Resend | Bei Resend nach dessen eigener Speicherdauer; wir behalten keine Kopie in unserer Datenbank |
| Datenbank-Sicherungen | Supabase | Ein kurzes rollierendes Fenster nach unserem Tarif — eine Löschung wird endgültig, wenn die Sicherungen, die sie enthalten, ablaufen |

Wo eine Zeile sagt „heute keine planmäßige Löschung“, ist das der ehrliche
Stand: Die Plattform ist jung, und es läuft noch kein Aufräumauftrag. Wenn
einer läuft, ändert sich diese Tabelle, und die Änderung wird mitgeteilt statt
neu unterschrieben, weil eine kürzere Speicherdauer für Sie kein schlechteres
Geschäft ist.

**Was Ihr Konto überdauert.** Zwei Dinge, und nur zwei.

Ein ausgestelltes Zertifikat und das Notenblatt, das es festhält, bleiben. Eine
Schule kann nicht rückwirkend unbezeugt machen, was sie bereits bezeugt hat,
und genau deshalb sind diese Dokumente als Momentaufnahme zum Zeitpunkt ihrer
Ausstellung eingefroren.

Auch der Nachweis, dass Sie ein Dokument wie dieses angenommen haben, bleibt,
**ohne Sie darin**. In dem Moment, in dem Ihr Konto gelöscht wird, wird die
Kontokennung auf diesem Nachweis durch eine Einweg-Prüfsumme davon ersetzt, und
die IP-Adresse wird gelöscht. Übrig bleibt: welches Dokument, welche Fassung, in
welcher Sprache und wann — und eine Prüfsumme, die sich nicht in Ihren Namen,
Ihre E-Mail-Adresse oder Ihr Konto zurückrechnen lässt. Das wird unbefristet
aufbewahrt, weil ein Einwilligungsnachweis, der mit dem Konto verschwindet, die
eine Frage nicht beantworten kann, für die er aufbewahrt wird.

Alles andere geht.

## Was Sie tun können

- **Ihre Daten einsehen und ändern** — in Ihrem Profil, für das, was das Profil
  hält.
- **Eine Kopie von allem bekommen, was über Sie gehalten wird** — schreiben Sie
  an supportequip@gmail.com, und wir stellen es zusammen und senden es. Einen
  Export-Knopf zur Selbstbedienung gibt es noch nicht.
- **Ihr Konto und Ihre Kursarbeiten löschen** — schreiben Sie an
  supportequip@gmail.com mit der Betreffzeile **Delete my account**. Es gibt
  keinen Löschknopf im Profil und keinen Weg zur Selbstbedienung: Wir machen es
  von Hand, und **innerhalb von 30 Tagen** nach Ihrer Bitte. Wir bestätigen,
  wenn es getan ist, und sagen Ihnen, was geblieben ist. Geblieben sind die
  drei oben genannten Dinge und sonst nichts: bereits ausgestellte Zertifikate,
  die Notenblätter, die sie festhalten, und der Nachweis, dass Sie diese
  Dokumente angenommen haben, ohne Sie darin.
- **Etwas berichtigen, das falsch ist** — sagen Sie es uns, und wir bringen es
  in Ordnung.
- **Der Sitzungsaufzeichnung widersprechen** — wir können sie heute nicht für
  ein einzelnes Konto abschalten. Wenn das für Sie nicht hinnehmbar ist, ist
  das Löschen des Kontos das ehrliche Mittel, und wir machen es Ihnen nicht
  schwer.
- **Die Einwilligung zurücknehmen** — was heißt, das Konto zu löschen: Die
  Plattform ohne Zustimmung zu diesem Dokument zu nutzen ist technisch nicht
  möglich.

Wir beantworten das innerhalb von 30 Tagen.

## Alter

Selbst anmelden können Sie sich ab **16**. Zwischen **13 und 16** kann ein Konto
nur von einem Schul-Administrator eröffnet werden, und in diesem Fall liegt die
Einwilligung der für die studierende Person verantwortlichen Person in der
Verantwortung der Schule — sie kennt die Familie und wir nicht. Diese Pflicht
steht in der [Schulvereinbarung](/school-agreement) geschrieben, statt
vorausgesetzt zu werden.

**Unter 13 kein Konto, auf keinem Weg.** Nicht durch Anmeldung und nicht
dadurch, dass ein Schul-Administrator eines anlegt. Wenn wir feststellen, dass
ein Konto einem Kind unter 13 gehört, schließen wir es und löschen seine Daten,
und wir sagen es der Schule. Wenn Sie glauben, dass ein Kind unter 13 hier ein
Konto hat, schreiben Sie an supportequip@gmail.com, und wir kümmern uns darum.

## E-Mails, die die Plattform sendet

Drei Arten, und keine anderen:

- **Konto-E-Mails** — die Bestätigung Ihrer Adresse, das Zurücksetzen Ihres
  Passworts, eine Einladung, die Ihnen jemand geschickt hat. Sie lassen sich
  nicht abschalten; ohne sie lässt sich ein Konto nicht nutzen.
- **Kurs-E-Mails und Benachrichtigungen** — Dinge, bei denen Sie schlechter
  dran wären, wenn Sie sie nicht wüssten: eine Sitzung, die gleich beginnt, ein
  entschiedenes Zertifikat, eine zurückgegebene Arbeit, eine verschobene Frist,
  eine Ankündigung aus Ihrem Kurs. Jede Art lässt sich in Ihrem Profil
  abschalten, und jede solche Nachricht trägt einen Abmeldelink.
- **Sonst nichts.** Keine Newsletter, keine Produktankündigungen, kein
  Marketing und kein Verkauf oder Vermieten Ihrer Adresse an irgendwen.

## Dinge, die später kommen können

Hier genannt, damit ihr Hinzukommen eine Mitteilung ist und keine weitere
Unterschriftenrunde — und jedes davon wird, wenn es kommt, hier vollständig
beschrieben, bevor es irgendwessen Daten berührt:

- **Kostenpflichtige Kurse.** Wenn eine Schule je für einen Kurs Geld verlangt,
  wickelt ein Zahlungsanbieter die Zahlung ab. **Wir werden Ihre Kartennummer
  nie halten**; der Anbieter wird es, und er wird in der Anbieterliste genannt,
  mit dem, was er hält. Heute gibt es auf der Plattform keine Zahlungen, und
  wir speichern keine Zahlungsdaten.
- **Anderswo gehostetes Video.** Eine Lektion kann ein Video eines
  Drittanbieters einbetten (heute YouTube, per Link). Es abzuspielen ist ein
  Besuch bei diesem Dienst, unter dessen eigenen Bedingungen, und dieser Dienst
  sieht Ihre Anfrage.
- **Weniger Dinge, früher.** Speicherdauern können auf diesem Weg nur kürzer
  werden; eine längere ist eine wesentliche Änderung.

## Änderungen dieser Erklärung

**Eine wesentliche Änderung braucht Ihre Zustimmung.** Sie werden gebeten, die
neue Fassung anzunehmen, bevor Sie weitermachen können. Eine Änderung ist
wesentlich, wenn sie eines davon tut:

- eine Kategorie von Daten hinzufügt, die wir erheben, oder einen neuen Zweck
  für Daten, die wir bereits halten;
- erweitert, wer Ihre Daten sehen kann, innerhalb der Plattform oder außerhalb;
- einen Anbieter hinzufügt, der eine Kategorie von Daten hält, die bisher kein
  Anbieter hielt, oder sie zu einem neuen Zweck hält;
- verlängert, wie lange etwas aufbewahrt wird;
- eines der unter **Was Sie tun können** aufgeführten Rechte nimmt.

**Alles andere wird mitgeteilt, nicht neu unterschrieben.** Einen Anbieter
gegen einen anderen mit derselben Aufgabe zu tauschen, eine Speicherdauer zu
verkürzen, ein neues Recht hinzuzufügen, einen Fehler zu berichtigen oder
dasselbe klarer zu sagen — diese werden veröffentlicht, Ihnen innerhalb der
Plattform mitgeteilt und **treten 60 Tage später in Kraft**. Sie müssen sie
nicht annehmen; Sie dürfen sie früher annehmen, wenn die neue Fassung sofort
für Sie gelten soll, und wenn Sie an eine davon lieber nicht gebunden wären,
haben Sie diese 60 Tage, um uns danach zu fragen oder Ihr Konto zu schließen.
Die Anbieter-Anlage ändert sich zu denselben Bedingungen und aus demselben
Grund: Ein Lieferantenwechsel bewegt kein Versprechen, und ihn zu einer neuen
Unterschriftenrunde zu machen würde Menschen dazu erziehen, sich durch einen
Einwilligungsbildschirm zu klicken, ohne ihn zu lesen — das Gegenteil dessen,
wofür Einwilligung da ist.

Jede Fassung wird mit dem Datum ihres Inkrafttretens und einer Prüfsumme ihres
Textes gespeichert, und der Nachweis dessen, was Sie angenommen haben, nennt
diese Fassung und diese Prüfsumme. Alte Fassungen werden nie umgeschrieben.

## Sprachen

Dieses Dokument wird auf Englisch, Russisch, Deutsch und Ukrainisch
veröffentlicht. Die Übersetzungen gibt es, damit alle lesen können, wozu sie
zustimmen, und sie sollen dasselbe sagen. **Wenn sie voneinander abweichen,
gilt die englische Fassung** — außer wo das Recht des Landes, in dem Sie leben,
etwas anderes sagt.

## Recht

Die Plattform wird von den Vereinigten Staaten aus betrieben (Indiana), und das
Recht dieses Staates gilt für dieses Dokument. Wenn Sie dort leben, wo das
Datenschutzrecht Ihnen Rechte gibt, die sich nicht wegvereinbaren lassen, dann
vereinbart dieses Dokument sie nicht weg.

## Kontakt

**supportequip@gmail.com**
