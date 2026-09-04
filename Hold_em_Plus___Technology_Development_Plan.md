# **Hold'em Plus — Technology Development Plan**

### **From play-money demo to online rooms, live casinos, and the GameTech Dealer Assist pathway**

---

## **1\. Objective & Strategic Logic**

The goal is to prove out **Hold'em Plus** — Texas Hold'em with a third hole card dealt after the flop — as a faster, higher-action tournament variant, using a low-cost, low-risk **fake-money web demo** as the wedge. A working, playable demo does three things at once:

1. **Validates the gameplay hypothesis** (bigger hands, faster action, more excitement) with real usage data instead of opinion.  
2. **Creates a reference implementation** that any poker room, home-game host, or casino can point to when evaluating whether to spread the game.  
3. **Builds the narrative bridge to GameTech Systems' Dealer Assist Technology** — a screen-based hand-tracking system for live tables. A screen system is far easier to pitch once there's a *specific new game* (Hold'em Plus) that benefits from screen-tracked hand status, since the extra hole card adds a dealing sequence that's easier to manage with on-screen prompts than with memory alone.

Because this is a **fake-money, no-rake demo**, it sidesteps gambling licensing entirely in phase 1\. Real-money and live-casino paths are deliberately sequenced later, after the rules and code are proven, and they carry very different legal requirements addressed in Section 6\.

---

## **2\. Game Specification (must be locked before any code is written)**

A precise, unambiguous rules document is the actual deliverable of phase 0 — everything else is an implementation of it. Below is a first draft to formalize; treat it as the spec the engineering team codes against.

**Hold'em Plus — Core Rules**

* Deal: 2 hole cards to each player, as in standard Texas Hold'em.  
* Pre-flop betting round, as normal.  
* Flop (3 community cards) is dealt.  
* **New step:** each active (non-folded) player is dealt a **3rd hole card**, face down.  
* Betting round on the flop \+ 3rd hole card (this replaces the standard "flop betting round" — it now happens with 3 hole cards \+ 3 community cards known).  
* Turn (4th street) dealt, betting round.  
* River (5th street) dealt, betting round.  
* Showdown: best 5-card hand from 3 hole cards \+ 5 community cards (standard "best 5 of 7" becomes "best 5 of 8").

**Dealer procedure (as specified), for both live and digital implementations:**

1. Deal hole cards, pre-flop betting.  
2. Burn one card.  
3. Deal the flop (3 community cards face up on the table.)  
4. Burn.  
5. Deal 3rd hole cards to each active player (face down, one at a time).  
6. Burn.  
7. Deal 4th street card face down (not yet turned up).  
8. Burn.  
9. Deal 5th street card face down (not yet turned up).  
10. Deck is now fully "set" and put down — dealer's remaining job is running betting rounds and turning 4th/5th street face up in sequence when action reaches that point.

This front-loaded dealing sequence is the detail that most directly motivates the Dealer Assist screen: it decouples "dealing" from "revealing," so the screen needs to track *what's already been dealt face-down vs. what's been turned* per hand, which is exactly the kind of state a human dealer can lose track of under pressure but a screen can't.

**Open rules questions to resolve before coding (flag these back to the game designer):**

* Does the 3rd hole card change starting hand equity enough to require different opening-range guidance, and should the demo educate players on this (tooltips, trainer mode)? I don’t believe the 3rd hole card changes starting hand equity. For v1 let’s assume little to no guidance, and a trainer mode can be in a v2.   
* Any max-hand-cap or hand-reveal rule differences from standard Hold'em (e.g., does anything change for stud-like exposure)? Answer: no, hole cards stay hidden until showdown — confirm this stays true. Confirmed, no caps or hand rule differences.  
* Rabbit Runner add-on (Section 2a below) — is it in-scope for the v1 demo or a v2 feature? Let’s add it to v1 demo, as it’s a feature worth showcasing from the start.

**2a. Rabbit Runner Option (secondary feature, likely v2)** If the hand ends by folding after 4th street, any player who folded may pay one small blind (routed to a dealer-tip pool in live play) to see the would-have-been river. This is a monetizable, dealer-incentive feature for live casino play; in the fake-money demo it can be simulated for free or with play-chips to gather player-interest data, but the *tip-pool economics* are a live-casino-only concept and shouldn't be modeled as revenue in the demo phase.

---

## **3\. Phase 1 — Fake-Money Web Demo**

### **3.1 Scope**

A browser-playable, multiplayer (and single-player-vs-bots) Hold'em Plus table using play chips only, no real-money paths, no rake, open registration, with anonymous/guest play so players don’t have to log-in to test the game. Primary purposes: prove the rules feel good, gather hand-speed/session data, and produce something shareable to online rooms, casinos, and the poker press.

### **3.2 Recommended approach: fork, don't build from scratch**

Building a poker engine, hand evaluator, table UI, and multiplayer networking layer from zero is the single biggest way this project could stall. Several mature open-source projects already solve 80% of the generic-Hold'em problem; the actual differentiator (the 3rd-hole-card street) is a comparatively small, well-isolated change to the betting/dealing state machine.

**Candidate open-source bases (as of Sept 2026):**

| Project | Stack | Fit for this project |
| ----- | ----- | ----- |
| **PokerTH** (github.com/pokerth/pokerth) \+ **PokerTH Web Client** (github.com/narmod/pokerth-web-client) | C++/Qt core, browser PWA client | Most mature, actively maintained (2026 release), explicitly play-money-only already, 10-player tables, AGPLv3/GPLv2. Best long-term base if the team is comfortable in C++; the web client gives a ready-made responsive UI to fork for player-side screens. |
| **bocaletto-luca/Texas-Holdem** | HTML5/CSS3/JS, Bootstrap 5, custom engine | Lightweight, pure front-end \+ simple engine, GPLv3. Good pick if the team wants a fast JS-only prototype and plans to write a custom backend anyway. |
| **jarczano/Texas-Holdem-Poker-Web-App** | Python/Flask \+ Flask-SocketIO backend, HTML/CSS/JS client | Good reference for real-time multiplayer architecture (Socket.IO) if the team is Python-first; currently heads-up only, would need extension to multi-seat tables. |
| **pokerscript-style HTML5 source packages** | Various, license terms vary | Useful for UI/table-graphics reference; audit license terms individually — quality and provenance vary widely. |

Recommendation: use **PokerTH's web client** for the player-facing table UI (cards, seats, betting controls, chat) since it's explicitly a "screen supplement to real play-money-free poker" product already — philosophically identical to what's needed here — and pair it with a **custom game-state service** for the Hold'em Plus rules engine, so the variant logic lives in code the team fully controls rather than deep inside a forked engine.

### **3.3 Technical architecture**

┌─────────────────────┐        WebSocket/REST        ┌──────────────────────────┐  
│  Player Client (Web) │ ◄───────────────────────────►│   Table/Game Server      │  
│  \- Forked PokerTH    │                                │  \- Hold'em Plus engine   │  
│    web UI components │                                │  \- Betting state machine│  
│  \- Seat/action UI    │                                │  \- Hand evaluator (8-card│  
│  \- Hand history view │                                │    best-5) service      │  
└─────────────────────┘                                │  \- RNG (shuffle) service │  
                                                          │  \- Play-chip ledger     │  
                                                          └───────────┬──────────────┘  
                                                                      │  
                                                          ┌───────────▼──────────────┐  
                                                          │  Persistence / Analytics │  
                                                          │  \- Hand histories        │  
                                                          │  \- Session/speed metrics │  
                                                          │  \- Player accounts (demo)│  
                                                          └───────────────────────────┘

**Core components to build (net-new):**

1. **Hold'em Plus rules/state engine** — extends a standard Hold'em betting-round state machine with the extra "deal 3rd hole card" step and the front-loaded burn/deal sequence described in Section 2\.  
2. **8-card hand evaluator** — standard Hold'em evaluators find the best 5 of 7; this needs best-5-of-8. Fast, well-tested 7-card evaluators (e.g., 2+2 evaluator, Cactus Kev-style lookup tables) can be extended by evaluating all C(8,5)=56 combinations per player at showdown — trivial computationally, just needs the extra combinatorics wired in and unit-tested hard against known hand rankings.  
3. **RNG/shuffle service** — cryptographically secure shuffle (e.g., Fisher–Yates seeded from a CSPRNG) even in the fake-money demo, both for good practice and because this code path gets reused later for real-money certification.  
4. **Play-chip ledger** — simple per-account balance, buy-in/re-buy/rebalance logic for tournament and cash-game demo modes. No real payment processing at all in phase 1\.  
5. **Analytics/instrumentation layer** — this is the part that actually tests the hypothesis. Track, per table/session: hands per hour, average pot size relative to blinds, showdown frequency, hand-strength distribution at showdown (pairs/two-pair/trips/straights/flushes/etc. rate vs. standard Hold'em baseline), and simple player-reported excitement (a lightweight post-session survey or thumbs-up prompt).

### **3.4 Suggested build sequence / milestones**

| Milestone | Deliverable | Rough effort |
| ----- | ----- | ----- |
| M0 — Rules lock | Finalized written rules spec \+ dealer procedure, reviewed by a few real poker players | 1–2 weeks |
| M1 — Engine prototype | Headless (no UI) Hold'em Plus engine: deal, bet, evaluate, showdown, playable via CLI or bot-vs-bot simulation | 3–5 weeks |
| M2 — UI integration | Fork PokerTH web client (or chosen alternative), wire to engine over WebSocket, single table, human \+ bots | 4–6 weeks |
| M3 — Multiplayer \+ accounts | Multi-table, lobby, play-money accounts, basic tournament (sit-and-go) structure per the "Simple Format Option" (40 chips, escalating blinds) | 4–6 weeks |
| M4 — Analytics \+ hypothesis testing | Instrumentation live, run structured A/B sessions (standard Hold'em vs. Hold'em Plus) with real players, publish results | ongoing after launch |
| M5 — Public demo launch | Hosted, shareable URL; outreach to online rooms, poker press, casino contacts | after M3/M4 stabilize |

### **3.5 Team & stack recommendation**

* 1 backend engineer (game logic, state machine, hand evaluator) — Go, Node/TypeScript, or Python are all reasonable; pick based on team familiarity, not novelty.  
* 1 frontend engineer (fork/adapt the chosen open-source client, real-time UI)  
* 1 person owning rules/UX/playtesting (can be the founder — needs to actually run structured playtests, not just intuit that it "feels faster")  
* Fractional/contract: data analyst for the hypothesis-testing analytics once M4 starts producing volume

This is a scoped, few-months project for a small team using the fork-first approach — materially smaller than the "hire a freelance engineer off Craigslist and build a full back end from scratch" path referenced in the GameTech Systems history, which is worth noting as a lesson: reusing a maintained open-source poker engine avoids re-solving already-solved problems (shuffling, hand evaluation, table UI) and lets the team's limited engineering time go entirely toward the actual differentiator.

---

## **4\. Phase 2 — Path to Online Poker Rooms (real-money, where legal)**

This phase only starts once Phase 1 produces real usage data supporting the hypothesis. Two separate work streams:

**4a. Technical**

* Package the Hold'em Plus rules engine as a **licensable module/spec** (open API or open-source reference implementation) that an existing licensed online poker room's platform team can integrate, rather than trying to become an operator. This is a much smaller lift than building a licensed real-money site from scratch, and mirrors how new variants (e.g., Short Deck/6+ Hold'em) actually got adopted by incumbent rooms.  
* RNG and hand-evaluator code need independent certification (e.g., by an approved testing lab such as GLI or iTech Labs) before any real-money deployment — budget for this explicitly; it's a hard requirement, not optional QA.

**4b. Business/legal**

* Real-money online poker legality is jurisdiction-specific (varies by U.S. state and by country) and changes over time — this plan does not constitute legal advice, and any real-money rollout needs jurisdiction-by-jurisdiction review from qualified gaming counsel before launch.  
* Target rooms that already operate legally in a given jurisdiction and pitch Hold'em Plus as an added tournament/cash-game variant on their existing licensed platform, using the Phase-1 demo and its data as the pitch asset.

---

## **5\. Phase 3 — Live Casinos & the Dealer Assist Bridge**

The live-casino path is where Hold'em Plus and the **GameTech Systems Dealer Assist concept** connect directly:

* The front-loaded dealing procedure (Section 2\) is specifically designed to reduce a live dealer's in-hand cognitive load — cards are pre-set, so the dealer's remaining job is running the betting rounds and flipping cards at the right moments. That's precisely the kind of state (whose turn it is, what's been revealed, what's still to come) a table-mounted **status screen** is good at tracking and displaying, per the Dealer Assist concept description.  
* Pitch sequencing: lead with the **variant** (a concrete, playtested, "here's the demo, here's the data" product) rather than leading with the **hardware/screen system** in isolation. A casino's felt-and-floor decision makers are far more likely to evaluate a specific new tournament format with proven data than an abstract technology-supplement pitch on its own — the game gives the screen system a concrete reason to exist at a given table.  
* Technical note specific to this project: the Dealer Assist system as described only displays and records dealer-entered action (check/bet/call/raise/fold) — it does not decide outcomes. That keeps the *hardware* project's scope (and its licensing classification argument) separate from the Hold'em Plus *software* project; they can be pitched together but built and evaluated independently, and a casino could adopt one without the other.  
* Realistic first foothold: independent card rooms, home-game-adjacent "poker leagues," or a single friendly casino property willing to run a promotional Hold'em Plus tournament series — not a strip-wide rollout — using the same "Billion Dollar Challenge"-style escalating sit-and-go structure already outlined in the source concept as a marketing hook, scaled down to a realistic pilot size initially.

---

## **6\. Risk & Legal Considerations (read before committing resources)**

* **This document is a technology and product plan, not legal advice.** Gambling law (online real-money gaming, live casino table-game approval, gaming licenses) is heavily jurisdiction-specific and changes over time; involve qualified gaming counsel before any step past the fake-money demo.  
* **IP status:** per the source material, the original 2005 patent application referenced does not appear to have issued as a granted patent, and the concept has been publicly described for marketing/investor-outreach purposes. Treat Hold'em Plus and the Dealer Assist concept as **not currently protected IP** — don't assume exclusivity is available, and if IP protection matters to the business plan, get a current freedom-to-operate and patentability opinion from a patent attorney before investing heavily, rather than assuming the earlier filing provides coverage.  
* **New table-game approval:** most gaming jurisdictions require a live casino table game (including a Hold'em variant with altered rules) to go through a formal game-approval process with the relevant gaming control board before it can be spread live for real money — this is a real timeline/cost item to plan for in Phase 3, separate from the software work.  
* **Open-source licensing:** PokerTH and PokerTH Web Client are AGPLv3/GPLv2; bocaletto-luca/Texas-Holdem is GPLv3. These are copyleft licenses — any derivative product built on them, especially a hosted web service, likely needs to keep the combined work's source open (AGPL in particular affects network-hosted use). Confirm license obligations with counsel before any commercial (non-demo) deployment; this may push a real-money product toward either fully complying with the copyleft terms or replacing the forked components with independently-written or permissively-licensed code before that stage.

---

## **7\. Immediate Next Steps**

1. Lock the written rules spec (Section 2\) and circulate it to a handful of real poker players for a sanity check before any code is written.  
2. Stand up the headless rules engine (M1) and unit-test it hard against known hand rankings and edge cases (split pots, all-ins with the extra street, etc.).  
3. Fork the PokerTH web client (or chosen alternative) and get one playable table running end-to-end with bots, even before multiplayer/accounts exist.  
4. Design the analytics instrumentation *before* public playtesting starts, so the hands-per-hour/hand-strength/excitement hypothesis has clean data from session one, not retrofitted later.  
5. In parallel, get a short consult with gaming counsel on (a) current patent/IP status and (b) the real-money and live-table regulatory landscape, so Phase 2/3 timing assumptions are grounded rather than aspirational.

