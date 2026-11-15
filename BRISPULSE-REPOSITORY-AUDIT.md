# BrisPulse — Repository Audit (M0)

**Phase:** M0 — Technical Discovery
**Author:** Sonnet 5.5
**Date:** 2026-11-16
**Scope agreed with the product owner:** the BrisPulse page in the portfolio repository (`stevensu04/stevensu-resume`) is treated as the "existing implementation". The DECO7380 reports and mock-ups were **not** audited (see §7).

Legend: **[V]** verified by inspecting a file or running a command in this session · **[A]** assumption or inference, not verified.

---

## 1. Headline finding

**[V] There is no BrisPulse application code in any location that was searched.** The "existing implementation" is a portfolio case-study page, a static screenshot of a prototype UI, and prose describing a proposed stack. Nothing runs, nothing fetches data, and there is no backend, database, test suite or deployment.

This matters because Master Plan §6.1 says "inspect the existing implementation before choosing or replacing technologies" and §8 M0 says "retain useful existing components". There is no technology to retain. M1 is effectively a greenfield architecture decision, and the project's own portfolio documents say so.

## 2. What was searched

| Location | Method | Result |
| --- | --- | --- |
| Portfolio repo `stevensu-resume` (working tree) | `grep -rIn -i brispulse` excluding `node_modules`, `.git`, `.next`, `.claude` | Only content/docs/3D-scene references listed in §3. No application code. |
| GitHub account `stevensu04` | `gh repo list stevensu04 --limit 100` | 12 repositories (public and private). None named BrisPulse or similar. The repository contents of the others were **not** inspected. |
| Local machine | `find ~ -maxdepth 4 -iname "*brispulse*"` (excluding `node_modules`, `Library`) | Only files inside `UQ NOTES/DECO7380/` (reports and images) and the new empty working folder created for this plan. |

**[V] Confirmed by the product owner (2026-11-16):** BrisPulse was only a concept and no code was ever written. The "simple responsive prototype" mentioned in `PLAN.md:48` and `PLAN.md:152` therefore refers to a design artefact, not source code, and cannot be reused as a frontend. Q1 is closed.

## 3. Inventory of BrisPulse references in the portfolio repo

| Artefact | Evidence | What it is |
| --- | --- | --- |
| `content/projects/brispulse.md` | frontmatter lines 1–30 | Case-study card. `status.label: "Capstone · Concept & Design"`. `tech` lists only *Systems Design, UX Research, Responsive Prototype*. `meta` lists "Proposed Stack (not yet built): Django · Python · GTFS-Realtime". `TODO(steven): add repo and demo once the walking skeleton is public`. |
| `public/projects/BrisPulse.jpeg` | image, 85,569 bytes | Screenshot of a dark-theme mobile UI (see §4). |
| `PLAN.md` §2, §3, §5 | lines 48, 63, 142–165 | States the project is "Concept + simple responsive prototype", that the card tags were corrected for honesty, and proposes a Django + GTFS-R "walking skeleton" (pressure score over 5–10 hard-coded corridors, deployed on Railway/Fly.io, with tests). |
| `CONTENT.md` | lines 225–240 | Uses BrisPulse as the worked example of labelling planned tech as "not yet built". |
| `WORLD.md` | lines 101, 121, 138, 325, 659, 1020 | Describes the 3D `/world` scene: a "blueprint table with a translucent wireframe and no walls", a traffic signal and an Olympic podium. States "The Django and GTFS-Realtime stack is proposed, not built." Line 138: BrisPulse moves "from the blueprint table to a building" if a walking skeleton ships. |
| `src/app/world/objects.ts:41`, `placements.ts:135`, `scene/Props.tsx:44`, `scene/Landmarks.tsx:113` | scene geometry | 3D props for the /world scene. Presentation only. |
| `src/app/projects/page.tsx:10`, `src/components/ProjectsView.tsx:26` | strings/comments | Page metadata and a layout comment. |

**[V]** Git history for the page: `git log --follow content/projects/brispulse.md` shows six commits, all portfolio-content changes (latest `3a11525`). No commit adds product code.

## 4. The prototype screenshot (`public/projects/BrisPulse.jpeg`)

**[V] Observed in the image:** a dark-theme mobile layout with a "BrisPulse" wordmark, a "Local" badge, a theme toggle, an alert card ("South Bank — pressure building · Athletics ends 9:30 PM · crowd surge in 42 min · your route is protected"), a "Where are you going?" search box, a stylised map with red/amber/green pressure blobs and a dashed protected route, a High/Mid/Calm legend, and a "Hotspot status" list (South Bank — Exit gates — *Surge*; Roma Street — Station concourse — *Building*; Woolloongabba — … — *Busy*).

**[A] Interpretation:** the content (a named athletics session ending at 9:30 PM, a "42 min" surge forecast, hotspot states) is illustrative of the *original* event-day crowd-pressure concept. There is no way to confirm from an image whether any of it was computed. It should be treated as **mock data and a design reference, not a working feature**. `TransLink GTFS-Realtime` cannot produce crowd-pressure values (see the metrics document).

## 5. Existing functionality (what actually works today)

| Capability | Status | Evidence |
| --- | --- | --- |
| Retrieve any transport data | **None** | No fetch code or dependency exists in any BrisPulse artefact found. |
| Backend / API | **None** | Stack is only "proposed" in `brispulse.md`. |
| Database / storage | **None** | — |
| Frontend | **Screenshot only** | `BrisPulse.jpeg`; source not found. |
| Tests | **None** | — |
| Deployment | **None** | `brispulse.md` has no `repo`/`demo` field. |
| Documentation | Concept docs and portfolio copy | §3. |

## 6. Technology stack

**BrisPulse itself: none implemented.** The only stack statement is the *proposal* "Django · Python · GTFS-Realtime" (`brispulse.md`, `PLAN.md:150`).

For context only (**not** BrisPulse's stack): the portfolio site is Next.js 16.2.4 / React 19.2.4 / TypeScript 5 / Tailwind 4 / three.js 0.187.0 (`package.json`). Its `AGENTS.md` warns that this Next.js version has breaking changes relative to common training data, so anyone reusing Next.js for BrisPulse must read `node_modules/next/dist/docs/` first. The owner's public `EventNow` repo is described as "Django + HTMX on Vercel" (`gh repo view`), with Python as a main language — relevant evidence of existing Django experience, not a decision.

## 7. Components worth preserving

| Item | Keep? | Reason |
| --- | --- | --- |
| Product name and the dark, status-coloured visual language (Calm/Mid/High → green/amber/red) | **Yes, as design reference** | It is the only built UI artefact. Master Plan §11 asks for accessible contrast and clear status indicators; the colour semantics need re-checking against real states (they currently mean *crowd pressure*, not *delay*). |
| Concept: "spatial-equity guardrails" (calmer routes must not push crowds onto residential streets) | **Preserve as documented future idea only** | Master Plan §3.2 excludes route recommendations and personalisation from the MVP, and the data it needs (BCC Wi-Fi probe density, venue gate egress) is unverified. |
| Original data proposals: BCC Wi-Fi probe density, venue gate egress, anonymised user signals | **Do not carry into MVP** | No evidence these are available. Not investigated in M0. |
| Portfolio card, `/world` blueprint-table scene | **Update later, not now** | They will become inaccurate once direction changes (see §8). Out of M0 scope; no files were modified. |
| DECO7380 reports and mock-ups | **Not audited** | Outside the scope the owner selected. File names exist in `UQ NOTES/DECO7380/` (three iteration/progress reports, a final report v4, a spatial-equity map PNG, a user-insights dashboard mock-up, a raw-data PNG). They may hold user-research findings worth citing in the case study. |

## 8. Divergence between the existing concept and the Master Plan

| Dimension | Existing concept (portfolio docs) | Master Plan v1.0 |
| --- | --- | --- |
| Problem | Event-day *spatial pressure* at stations and corridors during big events (2032 Olympics framing) | General *mobility intelligence* from public transport data |
| Core output | Pressure score; Fastest / Balanced / Calmer routes | Monitoring, descriptive analytics, data freshness and reliability |
| Primary data | GTFS-R plus Wi-Fi probe density, gate egress, user signals | TransLink GTFS static and GTFS-Realtime only |
| Routing | Included, with equity guardrails | Explicitly out of MVP (§3.2) |
| Status in portfolio | "Concept & Design" | "Functional MVP" |

**This is a change of product direction, not a refinement.** Master Plan §15 says major direction changes need explicit approval; the plan itself states the direction (§1.2), so this document records the gap rather than objecting to it. The practical consequences are:

1. The `/projects/brispulse` page, the `/world` blueprint-table copy and the CV text currently describe the old concept and must be updated when the repo goes public, keeping completed work and plans clearly separated (Master Plan §13). Not done in M0.
2. The spatial-pressure idea cannot be shown from GTFS data, so it should not appear in MVP screens or copy.

## 9. Mock data and placeholders

**[V]** No data files, seed files, fixtures or API stubs exist for BrisPulse in the places searched. The screenshot content is the only mock-looking material (§4).

## 10. Risks found in this audit

| ID | Risk | Severity |
| --- | --- | --- |
| A-R1 | The Master Plan presumes an implementation that does not exist; scheduling assumptions that rely on reuse ("Existing responsive prototype as the frontend", `PLAN.md:152`) may not hold. | High |
| A-R2 | ~~Prototype source may live elsewhere.~~ Closed: owner confirmed no code exists. | Closed |
| A-R3 | Portfolio copy will conflict with the new direction until updated. | Medium (reputation) |
| A-R4 | Colour semantics in the old UI mean crowd pressure; reusing them for delay data without redefinition would mislead. | Low |

## 11. Unresolved questions for the product owner

| ID | Question |
| --- | --- |
| Q1 | ~~Where is the prototype's source?~~ **Answered:** no code exists; concept only. |
| Q2 | Should the DECO7380 reports be audited in a later pass so that user-research evidence can be cited in the case study? |
| Q3 | Do you want the portfolio page and `/world` copy updated as soon as the repo is public, or after the MVP ships? |

## 12. Evidence trail

Commands run in this session (read-only against the portfolio repo): `git remote -v`, `gh repo list stevensu04 --limit 100`, `grep -rIn -i brispulse …`, `find ~ -maxdepth 4 -iname "*brispulse*"`, `git log --follow content/projects/brispulse.md`, `sed -n` on `PLAN.md`, `CONTENT.md`, `WORLD.md`, `Landmarks.tsx`; image view of `public/projects/BrisPulse.jpeg`; `gh repo view stevensu04/EventNow`. **No portfolio file was modified.** The portfolio working tree already had unrelated uncommitted changes before this session (`/world` work); they were left untouched.
