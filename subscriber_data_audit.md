# Subscriber Data Audit
*Mid-Nineteenth Century Jewish Newspapers — April 2026*

---

## What's in the dataset

**17,689 subscription rows** spanning 1843–1868 across four newspapers:

| Newspaper | Rows | Share |
|---|---|---|
| The Israelite | 10,583 | 59.8% |
| The Occident, and American Jewish Advocate | 3,559 | 20.1% |
| The Jewish Messenger | 3,008 | 17.0% |
| The Weekly Gleaner | 539 | 3.0% |

The Israelite dominates the dataset, which will shape any cross-paper comparison — overlap rates will naturally be pulled toward that paper.

---

## What's reliably filled in

These columns are essentially complete and can anchor most analyses:

| Column | Fill rate |
|---|---|
| Subscriber name edited | 100% |
| Final_Classification (Individual / Business) | 97.8% |
| Place_edited | 96.3% |
| State | 95.1% |
| Country | 94.3% |
| Year | 98.1% |

**What this means:** Geographic and temporal analysis is very feasible. You can reliably answer where and when subscribers appear across newspapers.

---

## What's sparse and why it matters

| Column | Fill rate | Impact |
|---|---|---|
| People_UUID | 81.1% | The main gap — see below |
| Month | 78.0% | Limits within-year sequencing |
| Subscriber Type (Male/Female/Business/Clergy…) | 30.6% | Can't fully analyze demographic patterns |
| Subscriber Role | 16.6% | Very partial — mostly "Subscriber" where filled |
| Occupation | 4.9% | Only a few hundred rows enriched |
| Business Name | 1.6% | Barely populated |

The **Subscriber Type** and **Occupation** gaps are significant but not fatal — the `Final_Classification` field (97.8% complete) gives you Individual vs Business reliably, which covers the most important distinction for most questions.

---

## The UUID situation

- **14,349 rows have a People_UUID** (81.1%) → these represent **7,003 unique identified people**
- **3,340 rows have no UUID** (18.9%) → drawn from **1,912 distinct names**
- The unidentified rows skew heavily toward **The Jewish Messenger** (2,237 of 3,008 rows) and the **Weekly Gleaner** (456 of 539), meaning cross-paper analysis currently underrepresents those papers

Among identified people:
- **6,428** appear in only one paper
- **542** appear in exactly two papers
- **33** appear in all three major papers

---

## Cross-paper subscriber overlap (identified people only)

| Paper pair | Shared subscribers |
|---|---|
| The Israelite + The Occident | **353** |
| The Jewish Messenger + The Occident | **135** |
| The Israelite + The Jewish Messenger | **117** |
| The Israelite + The Weekly Gleaner | **29** |
| The Occident + The Weekly Gleaner | 6 |
| The Jewish Messenger + The Weekly Gleaner | 1 |

**Key finding:** The Occident is the connective tissue. It overlaps substantially with both major papers, suggesting its subscribers were a more "invested" reading community who also followed other papers. The Israelite–Messenger overlap (117) is lower than you might expect given their size, hinting at distinct readerships. *Note: these numbers are floors — the 3,340 unidentified rows could add more overlap once UUIDs are assigned.*

---

## Subscriber switching and loyalty

The timelines of multi-paper subscribers reveal several patterns already visible in the data:

**Loyalty with parallel subscriptions:** Some subscribers maintained The Israelite subscriptions year after year while adding other papers (e.g., Kiersky Brothers, Stockton — Israelite 1856, Gleaner 1857, Israelite again through 1863).

**Switching:** Others appear to drop one paper as they pick up another (e.g., Joseph P. Newmark: Weekly Gleaner 1858 → Jewish Messenger 1859–1861).

**Migration with continuity:** Amson B. Goldsmith (Yreka/Crescent City/San Francisco, 1857–1864) is a clear example of someone maintaining subscriptions while physically moving — he appears in multiple California gold country towns across years, subscribing to both The Israelite and The Weekly Gleaner concurrently.

**Business→personal transitions:** The Kling family is already flagged in the data: "Kling & Brother," "Joseph Kling," and "Moses Kling" all share a UUID (a02f2c7a), showing 14 Israelite subscriptions under different names across years.

---

## Geographic movement

**732 identified people appear in more than one location** across their subscription history. Examples:

- **A. Levy** — Dubuque, Houston, Louisville, Philadelphia, Richmond, Sparta
- **Meyer Strauss** — Charleston, Cincinnati, Milwaukee, Muskegon, St. Louis
- **Isaac Frank** — Cincinnati, Columbus, Savannah, St. Louis, Steubenville

These are people you can already trace moving across the country while maintaining newspaper subscriptions — a rich thread for analysis of mid-century Jewish migration patterns.

However, some "movers" like **A. Levy** or **S. Levy** may be UUID false positives (the same common name assigned to one person when they may be different individuals). These deserve scrutiny before using them as migration evidence.

---

## What you can analyze *right now*

1. **Cross-paper overlap geography** — which cities had subscribers to multiple papers? (Year and Place_edited are solid.)
2. **Institutional/community subscribers** — Synagogues, organizations, clergy are partially tagged in Subscriber Type; cross-paper analysis of these is possible.
3. **Timeline of subscriber acquisition** — when did The Israelite pull subscribers away from The Occident (or vice versa)? The year coverage is good.
4. **Migration trajectories** — the 732 movers with confirmed UUIDs are ready to map.
5. **Business vs. Individual patterns by paper** — Final_Classification is nearly complete.

## What needs more work first

1. **The Jewish Messenger UUID gap** — 74% of its rows have no UUID, making it hard to include fairly in overlap analysis. Prioritizing UUID assignment for the Messenger would unlock the most new insight.
2. **Common name ambiguity** — Names like "A. Levy," "S. Levy," "M. Cohen" appear across many cities. UUIDs assigned to these should be verified before use in migration analysis.
3. **Month field** — 22% missing; limits fine-grained sequencing within years.
4. **Subscriber Type** — Only 30.6% filled; demographic analysis of gender, clergy, organizations is currently incomplete.

---

## Recommended next steps

- **Prioritize UUID assignment for The Jewish Messenger** — it's the paper most underrepresented in the current identity layer
- **Flag high-ambiguity UUIDs** for review (common surnames + multiple cities = likely conflation)
- **Run a cross-paper overlap analysis by city and year** using only Place_edited + Year + Newspaper_Name (no UUID needed) — this gives a UUID-independent view of geographic overlap
- **Build subscriber timeline visualizations** for the 575 confirmed multi-paper people as a pilot

