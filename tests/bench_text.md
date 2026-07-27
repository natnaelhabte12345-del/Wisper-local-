# Benchmark-Text (ca. 60 Sekunden)

Diesen Text einmal vorlesen. Er ist die Referenz für `tools/stt_bench.py` —
alle Anbieter werden dagegen gemessen. Normal sprechen, nicht übertrieben
deutlich, sonst misst man einen Fall, den es im Alltag nicht gibt.

Alles unterhalb der ===-Zeile wird als Referenz gewertet, sonst nichts.

===

Ich habe gestern den ganzen Abend am Deployment gesessen und irgendwann gemerkt, dass die Environment Variables auf Vercel gar nicht gesetzt waren. Die Supabase Datenbank war über Prisma angebunden, aber der JWT wurde beim Refresh nicht validiert. Vermutlich liegt es am Middleware Setup in Next.js. Der Build dauert inzwischen ungefähr 4 Minuten und 30 Sekunden, das sind etwa 20 Prozent langsamer als letzte Woche. Am Ende habe ich einfach den kompletten Cache geleert, danach lief es sofort. Was ich als Nächstes angehen möchte, ist die Frage, wie wir die Genauigkeit überhaupt messbar machen. Im Moment ist das reines Bauchgefühl. Besser wäre eine feste Sammlung von Testtexten, die wir immer wieder verwenden, damit wir tatsächlich sehen, ob eine Änderung etwas verbessert oder verschlechtert hat. Wir treffen uns morgen um 14 Uhr 45, um das gemeinsam durchzugehen.
