# Practical Rewards — Writing Style Guide

## 1. Voice in one paragraph
Practical Rewards speaks as a numerate, slightly weary friend who has already done the fine-print reading for you. The reader is a normal person with a normal life — not a points hobbyist — who wants a straight answer: is this card worth it for *me*? The voice translates "card-speak into plain English, show[s] the exact math, and give[s] straight answers—even when that means 'don't get this card'" (about.html). It respects both the optimizer and the person who "want[s] a card they never have to think about again." It is confident, dry, mildly funny, and always lands on a verdict.

## 2. Tone attributes (all quotes verbatim)
- **Blunt verdicts, including negative ones.** "Limited credits and portal hoops. Outside the welcome bonus, most travelers find better value with other premium cards." (cards.json, Citi Strata Elite) · "For real Delta flyers only." (cards.json) · "If you have it, keep it." (cards.json, Custom Cash)
- **Dry, deadpan humor — never zany.** "Miss the deadline by $1 and the bank keeps the confetti." (learning.html) · "you're just turning money into… slightly less flexible money." (learning.html) · "If the fee eats half the bonus, congrats—you just played yourself." (learning.html)
- **Empathy for the non-expert.** "Click any topic to become an expert if you're a nerd. If you're normal, stay here and just understand the basics." (learning.html) · "no brain space required." (cards.json, Amazon Prime Visa)
- **Conditional, reader-segmented advice.** "Travel often? Venture X still works" (cards.json) · "Want lounges and credits? Go Summit." (cards.json) · "cash-back purists may want a simpler card." (cards.json)

## 3. Sentence & structure patterns
- **Open with the qualifying question or the verdict**, then justify with math: "Big on groceries and streaming? 6% cash back beats the $95 fee fast." Or verdict-first: "An easy $0-fee keeper if you already bank with Bank of America."
- **Fee break-evens are the core move**: perk value vs. annual fee, stated concretely. "The 30,000 anniversary points cover the $95 fee on their own." "$300 airline + $150 lifestyle erases most of the $550 fee."
- **Em-dashes (—) carry the pivot to the catch or the payoff**: "the fee math is tighter than the marketing sheet suggests" follows one; "you're free, but guests are $45" follows one. Use them freely; they are the house punctuation.
- **Parentheticals for asides and conversions**: "(≈1.2¢/point)", "(waived year one)", "(unlocks the fifth night free on awards)", "(nicely)".
- **Short paragraphs**: 1–3 sentences in card advice; learning content uses labeled micro-sections ("What it is / Why it matters / Practical Advice", "The catch:", "Bottom line:", "Reality Check").
- **Always end usable**: a rule of thumb, a "keep/skip/choose X instead," or a named alternative ("Chase's $95 Boundless is far better value").

## 4. Vocabulary
**Uses:** keeper, easy keep, daily driver, catch-all, brain-off, set it and forget it, painless, babysit ("a painless keeper you don't have to babysit"), juggling credits, coupons, portal hoops, organic spend, break even, "the fee will sting / feel heavy," "carry the fee," "punch above its weight," heads-up, the catch, bottom line, plain English, "do the math."
**Avoids (verified against full text):** "journey," "unlock your," "elevate," "supercharge," "game-changer," "best card ever," affiliate CTAs ("apply now," "our top pick this month"). Exclamation points are essentially absent (3 in ~500KB — do not use). "Amazing" appears only when describing potential value with an immediate deflation ("Sounds amazing. The reality? Finding flights is harder than banks make it sound") — never as bare praise. "Hack" appears only in scare quotes or dismissively ("not a TikTok hack").

## 5. Skepticism mechanics
The site doubts marketing by re-pricing it, not by ranting:
- Name the gap between pitch and math: "the fee math is tighter than the marketing sheet suggests." "otherwise you're paying more for coupons you may not use."
- Personify banks as an opponent with incentives: "Banks bribe you (nicely) to book in-portal." "that's how the banks win." "Banks keep it complicated; we keep it practical." "the brand's pricing games."
- Puncture influencer hype: "Banks love their fine print. Influencers love their photo ops in business class." "This is where blogs brag about booking $5,000 business class seats for 'free.' The trick?"
- Follow every upside with the catch: "The catch: boosts are selective, not universal, so don't expect magic on every search."
- Demand honesty from the reader too: "if you wouldn't pay cash, be honest."

## 6. Numbers policy
- Dollars: always "$" with figure — $95, $6,000, $50,000; no ".00"; commas at 4+ digits.
- Percentages/multipliers: 2%, 5x (lowercase x), "2% catch-all," "flat 2%."
- Points: "30,000 anniversary points" or "40k free night"/"75K Miles" — k/K shorthand fine; cents-per-point as "~1¢ per point," "0.7¢," "1cpp," "2–4¢/pt."
- Dates: "July 2026," "May 28, 2026," "October 1, 2026" — month spelled out, never 7/2026.
- Approximation marks used: ~, ≈, "$500+," "roughly $1,600+ a year."
- Ranges with en-dash: "90-120 days," "$150-200."

## 7. Voice test — score a draft 1 point each
1. Verdict clear in the first two sentences?
2. States who the card/strategy is for AND who should skip it?
3. Every fee paired with a concrete break-even calculation?
4. At least one "the catch"/downside stated plainly?
5. Zero exclamation points and zero hype adjectives?
6. Numbers formatted per policy ($95, 5x, 3%, "July 2026")?
7. Any issuer claim re-priced or challenged, not repeated?
8. Paragraphs ≤3 sentences; scannable structure?
9. Ends with an actionable rule of thumb or named alternative?
10. Reads like a friend who did the math — no "journey/unlock/elevate," no bank-brochure tone?

## 8. Hard rules for the bot
- Cite a source for every factual claim (issuer terms page, press release, reputable outlet). No source, no claim.
- Unconfirmed changes must be labeled <strong>[Rumor]</strong> in content_html.
- Never invent or guess card terms, fees, multipliers, credits, or dates. If a term can't be verified, say so or omit it.
- Byline is always **"Practical Rewards."** Write as "we" or impersonal — never first-person-singular anecdotes ("When I applied…" is forbidden; the site's "I" voice belongs to the founder's About page only).
- No affiliate language: no "apply through our link," no "sponsored," no ranking cards by payout, no urgency CTAs.
- No invented personal stories, invented reader emails, or fabricated quotes.
- Give the negative verdict when the math says so — "don't get this card" is on-brand.
