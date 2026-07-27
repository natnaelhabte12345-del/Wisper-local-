# WisprWin Genauigkeits-Tests

So gehst du vor:
1. Text laut vorlesen (Right Ctrl halten), in einen leeren Editor diktieren lassen.
2. Ergebnis unter "Ergebnis:" einfügen.
3. Mir die Datei zurückgeben — ich vergleiche Wort für Wort und leite daraus ab, was am Prompt/Formatter geändert werden muss.

Wichtig: **nicht** absichtlich übertrieben deutlich sprechen. Sprich so, wie du normalerweise diktierst — sonst testen wir einen Fall, der im Alltag nie vorkommt.

---

## T1 — Kurz, reines Deutsch, Satzzeichen (ca. 8 Sek.)
**Prüft:** Grundgenauigkeit, Kommasetzung, Groß-/Kleinschreibung.

> Ich schreibe dir später nochmal, wenn ich weiß, wann der Termin ist. Falls es nicht klappt, sag einfach Bescheid.

Ergebnis:
```

```

---

## T2 — Kurz, Tech-Vokabular (ca. 10 Sek.)
**Prüft:** ob der Whisper-Prompt die Fachbegriffe abdeckt und der Formatter sie nicht "verbessert".

> Ich habe die Supabase Datenbank mit Prisma angebunden, aber der JWT wird beim Refresh nicht validiert. Vielleicht liegt es am Middleware Setup in Next.js.

Ergebnis:
```

```

---

## T3 — Kurz, Zahlen und Einheiten (ca. 10 Sek.)
**Prüft:** Zahlen, Uhrzeiten, Prozente — klassische Whisper-Schwachstelle.

> Der Build dauert ungefähr 4 Minuten und 30 Sekunden, das sind etwa 20 Prozent langsamer als letzte Woche. Wir treffen uns um 14 Uhr 45.

Ergebnis:
```

```

---

## T4 — Mittel, Deutsch-Englisch gemischt (ca. 25 Sek.)
**Prüft:** Code-Switching. Hier verschluckt Whisper gern englische Wörter oder eindeutscht sie.

> Ich habe gestern den ganzen Abend am Deployment gesessen und irgendwann gemerkt, dass die Environment Variables auf Vercel gar nicht gesetzt waren. Das war schon ziemlich frustrierend, weil die Logs überhaupt nichts angezeigt haben. Am Ende habe ich einfach den kompletten Cache gecleared und dann ging es sofort. Manchmal ist die Lösung wirklich einfacher als man denkt.

Ergebnis:
```

```

---

## T5 — Mittel, natürliches Sprechen mit Füllwörtern (ca. 25 Sek.)
**Prüft:** ob der Formatter Füllwörter, Selbstkorrekturen und Wiederholungen richtig behandelt — oder ob er anfängt, den Inhalt umzuschreiben. Lies das bewusst so holprig vor, wie es dasteht.

> Also ich wollte eigentlich, ähm, ich wollte eigentlich fragen, ob du morgen, ne warte, übermorgen Zeit hast. Weil ich glaube, also ich bin mir nicht ganz sicher, aber ich glaube das Meeting wurde verschoben. Und dann müssten wir das halt nochmal neu planen irgendwie.

Ergebnis:
```

```

---

## T6 — Lang, zusammenhängend (ca. 90 Sek.)
**Prüft:** das eigentliche Problemfeld — Drift über die Länge, abgeschnittene Enden, Formatter der bei langen Texten anfängt zusammenzufassen statt nur zu formatieren.

> Ich möchte kurz zusammenfassen, wo wir mit dem Projekt gerade stehen und was die nächsten Schritte sind. Der erste Teil, also die Aufnahme und die Transkription, funktioniert inzwischen stabil. Wir schicken das Audio direkt an die API und bekommen den Text normalerweise in unter zwei Sekunden zurück. Was noch nicht optimal läuft, ist die Nachbearbeitung. Manchmal werden Wörter ersetzt, die eigentlich völlig korrekt waren, und das ist natürlich schlimmer als gar keine Korrektur, weil man es beim schnellen Drüberlesen überhaupt nicht merkt.
>
> Der zweite Punkt betrifft die Einfügung in andere Programme. Das war lange Zeit unser größtes Problem, weil der Text manchmal in der Adressleiste vom Browser gelandet ist statt im eigentlichen Textfeld. Das haben wir jetzt gelöst, indem wir die Zeichen einzeln als Unicode schicken, sodass sie gar nicht erst als Tastenkombination interpretiert werden können.
>
> Was ich als Nächstes angehen möchte, ist die Frage, wie wir die Genauigkeit messbar machen. Im Moment ist das reines Bauchgefühl. Ich lese etwas vor, schaue mir das Ergebnis an und finde es entweder gut oder schlecht. Besser wäre es, wenn wir eine feste Sammlung von Testtexten hätten, die wir immer wieder verwenden, damit wir tatsächlich sehen können, ob eine Änderung etwas verbessert oder verschlechtert hat.

Ergebnis:
```

```

---

## Notizen
Alles, was dir beim Diktieren auffällt und nicht im Text sichtbar wird (Overlay hängt, Abbruch, spürbare Verzögerung), hier rein:

```

```
