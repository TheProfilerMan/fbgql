# Legal & compliance notes

This project is released under the [MIT License](LICENSE). You may use, modify, and
distribute the software under those terms. This document adds **operator and publisher
guidance** — it is not legal advice, and it does not change the license. Consult
counsel for your specific use case.

## 1. Software license (MIT)

- Source code in this repository is licensed under MIT. Keep the copyright and
  permission notice in copies and substantial portions you distribute.
- The MIT license covers **copyright in this codebase**. It does **not** grant rights
  to Facebook/Meta content, trademarks, or APIs, and it does not make scraping lawful
  where it would otherwise be restricted.

## 2. Clean-room / copyright

- This package is a **clean-room rewrite**. It was implemented from a description of
  Facebook's GraphQL protocol behavior (endpoint, `doc_id`s, request/response field
  paths, pagination semantics). Those are facts of interoperability.
- It shares **no source** with the upstream `mohdtalal3/facebook_post_comment_scraper`
  clone (which is "educational only" with **no OSS license**). Do not copy that code,
  its module/function names, or its git history into this repo.
- Prior experiment outputs may be used only as **test fixtures**.

## 3. Meta / Facebook Terms of Service

- Automated scraping may violate Facebook's Terms of Service regardless of how the
  software is licensed.
- Operational risk (account bans, rate limits, checkpoints) falls on whoever runs it
  with their own accounts/cookies. Users **bring their own cookies**.
- The authors and copyright holders disclaim liability for your use of the software
  against third-party terms, as permitted by the MIT License.

## 4. Personal data / GDPR (critical for public actors)

- Facebook comments contain **personal data** (author names, opinions).
- Publishing or operating a public actor that scrapes personal data creates
  data-protection obligations (GDPR and equivalents). Apify requires publishers to
  comply.
- If you distribute or run this software against live Facebook data, you are
  responsible for having a lawful basis, providing required notices, and honoring
  data-subject requests.
- The Apify Store README should disclose what is collected and the legal basis
  expected of the user, and provide a contact for data-subject requests.

## 5. No warranty

The software is provided **"AS IS"** under the MIT License, without warranty of any
kind. There is no guarantee that Facebook's GraphQL endpoints, `doc_id`s, or response
shapes will remain stable, that scraping will stay permitted, or that a run will
complete without blocks or data loss.
