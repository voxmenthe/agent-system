# Supplementary lists for /macro

**Role:** Optional **second-look** only. Core synthesis stays allowlist-hard;
participant-native equity runs keep any eligible sentiment-panel or context
hits in a separate evidence role.
These lists are broad markets feeds with real noise. Use them to catch themes
or allowlisted voices the `from:` batches missed - not to replace credibility
filtering.

Operator form: `list:{id}` (no spaces). Prefer **Latest** mode.

## Registry

| Name | List id | URL | Character (from sampling) |
|------|---------|-----|---------------------------|
| **NBTQ** | `209841180` | https://x.com/i/lists/209841180 | Mixed desk/analyst + chart brands + retail. High volume. Usable with topic + engagement filters. |
| **InvQ** | `960008892343246848` | https://x.com/i/lists/960008892343246848 | Reply-heavy (one chatty member can dominate Latest). Some quality macro/FX/global when replies are cut. |

## Hard constraints when using lists

1. **Budget:** At most **1–2** list keyword calls per `/macro` run (one per list, or one focused list if topic is narrow). Stay inside the overall X call budget.
2. **Never core evidence alone.** Non-allowlist authors from a list do **not**
   define facts, company conclusions, professional consensus, or breadth and do
   not enter core receipts as equal-weight voices. A registered
   sentiment-panel author may enter the separately labeled sentiment sample
   after its current-post gate; other off-list hits remain isolated context or
   discovery leads.
3. **Allowlist overlap is gold.** If a list hit is already on `credible-sources.md` / equity allowlist, treat it as normal allowlist evidence.
4. **Same post-level filters** as the main path: hashtag/quality gate for
   allowlisted hits (count alone is not a drop); 2+ hashtags remain a spam
   tell for non-allowlist list noise; on-topic-only rules; equity post-level
   rules in equity mode; no official institutional feeds as synthesis core
   (Fed/BLS/FRED promo, etc.).
5. **Latest preferred for root discovery.** Bare `list:` + Top often empty or
   weird; use a filtered Latest overview, then inspect only exact selected
   conversations.

## Noise you will see (filter accordingly)

| Noise type | Typical source | Drop when |
|------------|----------------|-----------|
| Reply-chain domination | InvQ especially | Use `-filter:replies` for the root overview; recover replies only for selected exact conversations |
| Chart-brand spam | Barchart-style one-liners + emoji | No new analytical claim; pure "look at chart" promo |
| Retail tip spam | "take it to bank", "follow for tips", leverage/SBLOC ads | Always |
| Personal / off-domain | Weather, food, babysitting, sitcom analogies | Always |
| Paywall bait / inbox promo | "link in bio", "subscribe for the note" | Always |
| Wire firehose | Automated alerts with no desk read | Keep only if it names a concrete print/decision you then re-check on allowlist |
| Geopolitics venting | Emotion-only war posts | Keep only if it clearly ties to oil/risk/FX levels with substance |

## Query filters (narrow the feed)

For **root discovery**, combine `list:{id}` with **window** +
`-filter:replies`. Add **topic tokens** in topic mode (or a fixed macro token
pack in discovery). Optionally raise the engagement floor when Latest is still
chatty. This is not a blanket rule against replies: after selecting an
allowlisted root, use `x_thread_fetch` plus a floor-free exact
`conversation_id:{root_id}` search and optional self-thread/time-box lanes.

### Macro token pack (discovery or broad scan)

```text
(yields OR FOMC OR CPI OR Fed OR rates OR inflation OR "10y" OR dollar OR DXY OR credit OR recession OR "soft landing" OR payrolls OR PCE OR ECB OR RBA OR "jobless" OR Treasury OR curve)
```

Tune the pack to the live sleeve (FX, oil, credit, etc.) rather than pasting every token every time.

### Equity mode token pack (when equity mode is on)

```text
(NVDA OR META OR AAPL OR MSFT OR GOOGL OR TSLA OR ORCL OR earnings OR guidance OR "Mag 7" OR semis OR "AI capex")
```

Or the user-named tickers / thesis terms. Still hard-filter core equity claims
to the equity allowlist; route sentiment-panel texture separately.

### Lane recipes

**NBTQ - root overview / supplementary (Latest):**

```text
list:209841180 since:{bound} -filter:replies ({topic_or_macro_tokens}) min_faves:3
```

If too thin, drop `min_faves` once (keep `-filter:replies` + tokens). If still chart spam, try `min_faves:5`.

**InvQ - root overview / supplementary (Latest; replies first):**

```text
list:960008892343246848 since:{bound} -filter:replies ({topic_or_macro_tokens})
```

Optional: `min_faves:2` if still chatty after `-filter:replies`. Do **not** use
bare `list:960008892343246848` for root discovery - Latest floods with short
replies. Once a root is selected, leave the list query and inspect that exact
conversation.

**Topic mode example (CPI day):**

```text
list:209841180 since:{bound} -filter:replies (CPI OR "consumer price" OR inflation OR core) min_faves:3
```

```text
list:960008892343246848 since:{bound} -filter:replies (CPI OR "consumer price" OR inflation OR core)
```

## What to do with list hits

| Hit type | Action |
|----------|--------|
| Author on active allowlist | Keep; normal ranking / receipts |
| Author registered in `equity-sentiment-panel.md` | Apply its current-post and concentration gates; keep only in the labeled sentiment sample or its narrower review/discovery role |
| High-substance non-allowlist (levels, print read, clear policy claim) | **Do not** let it define the primary read. Optionally (1) re-query allowlist on that theme, and/or (2) one bullet under **List check** labeled lower-weight / not allowlist |
| Theme only (many list posts on oil/RBA/etc. allowlist never hit) | Re-run one allowlist batch with those tokens; do not invent allowlist consensus from list noise |
| Low substance / retail / personal | Drop silently |

If a selected root has a substantive conversation, an off-allowlist reply may
be shown only as a labeled sentiment-sample node when it is registered and
eligible, or otherwise as lower-weight context/counterevidence. It does not
become list membership, an allowlisted receipt, or a core voice. Preserve both
root and reply IDs/URLs and state whether the node is an author continuation or
an independent voice.

## When to skip list check

- User fixed a very short window and allowlist already rich (Breaking, high confidence).
- Call budget exhausted after allowlist lattice - prefer allowlist threads over list noise.
- Equity mode with dense EQ-A already covering the tape - optional one equity-token list pass max.
