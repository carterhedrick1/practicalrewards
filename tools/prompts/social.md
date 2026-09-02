Write the Instagram copy for one published Practical Rewards article. The slides are rendered by a fixed template; you supply only the words.

The post is a 4:5 carousel or a single image. Slide 1 is always the article's hero stat card (kicker, stat, label — already fixed). When the article contains a worked-math panel it is rendered automatically as its own slide, and the final slide is always the "Practical verdict". You write: the optional text slides in between, the short verdict, and the caption.

Hard rules:
- Follow the inlined house style: dry, numerate, blunt verdicts, no hype, no exclamation points, "we" or impersonal voice, never first-person singular.
- Every number, dollar figure, percentage, multiplier, points figure, or date you write must already appear in the article with the same value. Do not introduce any number that is not in the article. Do not round, convert, or extrapolate.
- Name only cards, issuers, and brands the article names.
- Dates read like a person talking today: write "October 1" or "starting October 1", never "October 1, 2026" or "in 2026". Include a year only when the article is contrasting two different years.
- No affiliate language, no "apply now", no urgency, no emoji, no hashtags or URLs inside slides, verdict, or caption (hashtags and the link line are appended automatically).
- Do not repeat the hero stat card's label verbatim, and do not restate the math panel's rows on a text slide.
- Plain text only. No Markdown, no HTML entities.

Format decision:
- "single" when the hero stat and label carry the whole point on their own and the article has no worked-math panel and no multi-step argument.
- "carousel" otherwise. Write 1 or 2 text slides, each one idea: heading under 40 characters, body under 170 characters and at most two sentences. Prefer the most concrete, surprising, or rule-of-thumb material.

Verdict (always required, even for single): the article's closing rule of thumb in one or two sentences, under 190 characters.

Caption: 350 to 900 characters of plain text. Open with a hook line that is not the article title. Then two or three short paragraphs separated by blank lines that explain the practical math and the catch. End with the rule of thumb. No hashtags, links, emoji, or calls to apply.

extra_hashtags: 0 to 3 tags specific to this article (a card, issuer, perk, or program), each in the form #CamelCase with letters and digits only.

Return STRICT JSON only with exactly this shape:
{"format":"carousel","slides":[{"heading":"...","body":"..."}],"verdict":"...","caption":"...","extra_hashtags":["#SapphireReserve"]}

HOUSE STYLE:
{{STYLE_GUIDE}}

ARTICLE TITLE: {{TITLE}}
ARTICLE URL: {{URL}}
META DESCRIPTION: {{META_DESCRIPTION}}
HERO STAT CARD (slide 1, fixed): {{HERO_JSON}}
WORKED-MATH PANEL (rendered automatically as its own slide when present, or null): {{MATH_JSON}}
ARTICLE VERDICT SECTION: {{VERDICT_TEXT}}

ARTICLE TEXT:
{{ARTICLE_TEXT}}
