# Legal & compliance notes

These must be resolved **before** public distribution (especially publishing a
public Apify Store actor). This document is engineering guidance, not legal advice —
get a review from counsel.

## 1. Clean-room / copyright

- This package is a **clean-room rewrite**. It was implemented from a description of
  Facebook's GraphQL protocol behavior (endpoint, `doc_id`s, request/response field
  paths, pagination semantics). Those are facts of interoperability.
- It shares **no source** with the upstream `mohdtalal3/facebook_post_comment_scraper`
  clone (which is "educational only" with **no OSS license**). Do not copy that code,
  its module/function names, or its git history into this repo.
- Prior experiment outputs may be used only as **test fixtures**.

## 2. Meta / Facebook Terms of Service

- Automated scraping may violate Facebook's Terms of Service regardless of copyright.
- Operational risk (account bans, rate limits, checkpoints) falls on whoever runs it
  with their own accounts/cookies. Users **bring their own cookies**.

## 3. Personal data / GDPR (critical for a PUBLIC actor)

- Facebook comments contain **personal data** (author names, opinions).
- Publishing a public actor that scrapes personal data creates data-protection
  obligations (GDPR and equivalents). Apify requires publishers to comply.
- The Store README must disclose what is collected and the legal basis expected of
  the user, and provide a contact for data-subject requests.

## 4. Before publishing to the Apify Store

- [ ] Replace the placeholder `LICENSE`.
- [ ] Legal review of ToS + data-protection posture.
- [ ] README disclaimers (personal data, ToS, BYO cookies).
- [ ] Confirm monetization model (pay-per-event vs rental) and pricing.
