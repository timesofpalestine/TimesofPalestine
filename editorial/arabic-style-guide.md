# Times of Palestine Arabic edition standard

The Arabic edition is a first-class newsroom edition. It must preserve the
same verified facts, evidence, caveats and corrections as the English edition,
but it must not preserve English syntax, paragraph order or idiom when those
choices make the Arabic sound translated.

## Editorial workflow

1. Lock the reporting record: names, titles, dates, figures, attribution,
   uncertainty, hyperlinks and right-of-reply language.
2. Build a clean Arabic outline from that record. Choose the lead, section
   order and transitions for an Arabic reader.
3. Draft directly in Modern Standard Arabic. Prefer concrete verbs and clear
   subjects over chains of abstract nouns.
4. Compare the completed editions for factual parity, not sentence parity.
   Subheads, graphics, tables and material disclosures must still correspond.
5. Perform a separate Arabic-only line edit without looking at the English
   sentence order.
6. Read the full edition aloud. Rewrite any sentence that is difficult to say
   naturally or that requires rereading.
7. Check RTL rendering, mixed Arabic and Latin text, numerals, links, names,
   dates, captions and alt text before publication.

## Headlines

- Write the headline fresh in Arabic after the reporting record is locked.
- Aim for 6–10 words and never exceed 12 unless an essential proper name
  makes that impossible.
- Use an active construction and name the responsible person, institution,
  authority or other actor whenever the evidence identifies one.
- Do not hide a known actor behind an agentless construction such as
  «تتغيّر الأراضي» or «تم اتخاذ القرار». Write who changed the land record or
  who made the decision.
- State one clear news fact. Remove throat-clearing, vague abstractions,
  duplicated context and explanatory clauses that belong in the dek or lead.
- Read the headline by itself. It must make complete sense on the first
  reading, without relying on the English edition or the article body.

## House style

- Lead with the event, finding or person and its significance. Avoid
  throat-clearing such as «في خطوة من شأنها أن» when a direct verb will do.
- Keep paragraphs purposeful and sentences of moderate length. Split a
  sentence when several subordinate clauses obscure the main point.
- Use active verbs where the record identifies the actor: «أقرّت الحكومات»،
  «قالت المنظمة»، «قدّر التقرير».
- Use natural Arabic transitions that describe the relationship between ideas:
  «في المقابل»، «وبحسب التقرير»، «أما المرحلة التالية»، «ولهذا».
- Prefer precise newsroom vocabulary to unnecessary foreign terms. For
  example, use «على جدول الأعمال» or «في صدارة الاهتمام» rather than
  «على الأجندة» when the meaning permits.
- Use Arabic punctuation: the comma «،»، semicolon «؛» and question mark «؟».
  Do not copy English comma placement.
- Keep names and institutional titles consistent across the article. Introduce
  an acronym only when it will be used again.
- Use month pairs such as «يوليو/تموز» where the established site style calls
  for them. Keep numerals and units legible in mixed-direction text.
- Attribute evidence in the prose. Do not add a sources or bibliography
  section to published articles.
- Preserve constructive, good-faith framing while stating clearly what is
  promised, funded, underway, completed or still to be decided.

## Verb precision — hard errors (validator-enforced, owner order 2026-08-03)

These are not stylistic preferences; each is a wrong word that marks the copy
as machine-made. The build's diction gate (`language_quality_issues` in
`build.py`) flags them, sends the draft back for one editor rewrite, and
scrubs any cached brief that carries them.

- **«أسلم» ≠ «سلّم».** «أسلم» means embraced Islam (or, with نفسه, gave
  oneself up in a specific idiom). The verb for handing something over is
  «سلّم/سلّمت»: «سلّمت قوات الاحتلال الجثامين»، never «أسلمت قوات الاحتلال».
- **«قام بـ» + مصدر.** Use the verb itself: «قصفت الطائرات» لا «قامت
  الطائرات بقصف»؛ «اعتقل الجيش» لا «قام الجيش باعتقال».
- **«تم/تمت» + مصدر.** Name the actor and use the active verb: «اعتقلت
  القوات» لا «تم اعتقال»؛ «وقّع الطرفان» لا «تمّ التوقيع».
- **Machine filler.** «يُذكر أن»، «تجدر الإشارة إلى»، «الجدير بالذكر» —
  delete the scaffolding and state the information.

## Translation-artifact watchlist

These are warnings, not automatic replacements; context decides the wording.

- «المرحلة التشغيلية التالية» often reads more naturally as «مرحلة التنفيذ».
- «خريطة للتمويل» may be «خطة تمويل واضحة» or «سجل للمساهمات».
- «مقر إداري خاضع للمساءلة» may be «جهة إدارية تخضع للمساءلة».
- «جعل الغاية ملموسة» may be «ترجمة الالتزام إلى برنامج» or «إظهار أثره».
- «أمثلة أولية مفيدة» may be «مبادرات قائمة يمكن البناء عليها».
- Repeated «وفقاً لـ» can often become a reporting verb: «أفاد»، «قدّر»،
  «أظهر»، «ذكر».
- Do not reproduce English headline punctuation, parallelism or explanatory
  labels when a shorter Arabic headline is clearer.

## Names arriving through English or Hebrew (owner order 2026-08-11)

A transliterated personal or place name is never spelled by ear. Before an
Arabic edition uses a name that reached the desk through English or Hebrew
(a wire story, a bulletin, an Israeli paper), VERIFY the Arabic spelling
against Arabic-language sources covering the same story — الجزيرة نت، وفا،
معا، عرب 48، العربي الجديد، CNN بالعربية — and prefer the form the person's
own community uses (a Palestinian family name has one correct form:
الهذالين، مصلط، دعدرة…; the order came after «الهدالين» ran for الهذالين).

- Record every verified name in `editorial/arabic-names.json` with its
  source, and add any wrong variant you corrected — `build.py` loads that
  lexicon and flags the wrong variants in briefs and originals like machine
  diction, so a mistake can never recur silently.
- When Arabic usage is genuinely split (Hebrew names often are), pick one
  form, record it as the house form, and keep it consistent across editions.
- A name you cannot verify in any Arabic source is transliterated by the
  rules of the Arabic press register, flagged in the lexicon with
  `"verified": "unverified — recheck"`, and rechecked on the next story.

## Final Arabic-only pass

Confirm that:

- the opening sounds written in Arabic rather than translated into it;
- each pronoun has an unmistakable antecedent;
- gender, number and agreement are correct;
- dual and plural forms are natural rather than mechanically literal;
- quotations, allegations and uncertainty retain their exact evidentiary
  weight;
- no sentence follows English word order merely to mirror the paired edition;
- the article remains smooth when the English edition is closed.
