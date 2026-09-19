# Case Statement — Alstom x Cognyx (FDE)

The brief as received on 2026-09-19. Source:
<https://cognyx.notion.site/Case-Statement-Alstom-x-Cognyx-FDE-397e4540ca4c8114900ddcdbec22bd78>

## Foreword

This case (inspired by real events…) was designed to simulate a work situation close to
Cognyx's world, as part of a role-play representative of its projects. Any plausible figure,
metric or detail about Cognyx or the client may be invented for the purposes of this fictional
exercise.

The deliverable takes the form of 1 email and 1 in-person meeting of 1 hour (40 minutes on the
case, 20 minutes of questions about the role and Cognyx). The demo segment is a role-played
client meeting; the shipped-work and repo/AI-setup segments are out of role.

The case includes home preparation, part of which is something to build ("unapologetic vibe
coding"), recommended at **no more than 4 hours**: the exercise is about extracting maximum
value within a tight timebox using AI-assisted coding tools. An imperfect but working,
well-prioritized result beats a theoretically "complete" one.

## Context

You are a Forward Deployed Engineer at Cognyx. Alstom is starting a 3-week pilot of the Cognyx
platform at its Valenciennes site (regional trains). The pilot scope: help engineering teams
reuse existing sub-assemblies across train variants instead of re-designing (and re-costing)
from scratch at every tender.

The client's data team has sent an "as-is" export from their PLM/ERP environment: a
multi-variant Bill of Materials (BOM) CSV and free-text technical notes about components.
Kaïs, a Cognyx Deployment Strategist, owns the client relationship; the FDE is the technical
firepower of the pilot.

Next week's session with the client must demonstrate, with proof, that Cognyx can make sense
of their real data.

## What the situation doesn't tell you

- The data is dirtier than advertised: duplicated references with typos, mixed units,
  free-text fields switching between French and English.
- The site's lead data engineer is demanding about the quality and maintainability of what
  gets shipped — including when it's written with AI.
- The pilot sponsor will have very little time and expects a value story, not a technical demo.
- Eventually, nothing will be allowed to leave Alstom's network: the "how would you deploy this
  for real" question will come.
- A 3-week pilot is short: not everything can be done — choices must be made.

## Objectives — the build

Using the AI tools of your choice, build a small working tool that:

- ingests the pilot data — generate your own plausible synthetic dataset (multi-variant BOM +
  free-text notes);
- normalizes it into a simple entity model (components, sub-assemblies, variants,
  suppliers… up to you);
- can answer the client's question: "which sub-assemblies are reused — or reusable — across
  variants, and where are the inconsistencies?"

Format is free: CLI + report, small web app, agent… Deliver a git repo with a short README and,
above all, the trace of how you worked with AI (commit history, prompts, CLAUDE.md, skills…).

## Stakeholders

- **Thomas Lindqvist** — the site's lead data engineer. Technically excellent, knows the data
  inside out, scrutinizes the quality and maintainability of anything that gets shipped.
- **Bruno Maréchal** — the site's Engineering Director, pilot sponsor. Secured the pilot
  budget, expects demonstrable results; short on time, allergic to jargon.
