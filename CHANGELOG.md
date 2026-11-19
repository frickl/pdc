# Changelog

## 0.3.1

- Document DNS-query strategy for MSA deployments.
- Recommend using PDC instead of `reject_unknown_recipient_domain` on the same
  submission restriction path to avoid duplicate recipient-domain DNS checks.
- Recommend sharing the same local caching resolver between PDC and Postfix.
- Clarify that Postfix policy services cannot reuse the internal DNS result of
  `reject_unknown_recipient_domain`.

## 0.3.0

- renamed project to **pdc** (Plausible Domain Check)
- structured logging for reject/defer decisions only
- no logging for normal `DUNNO`/allow decisions
- external `domains.txt` remains unweighted and reloadable
- optional explicit `typo-map.txt`
- valid MX/implicit MX always wins over typo heuristics
- RFC 7505 Null MX detection
- reject localhost and loopback-only MX targets
- temporary DNS errors return 450
- fail open on internal PDC errors
- added unit tests and clean public Postfix examples

## 0.2

- detect Null MX and unusable localhost/loopback MX targets
- keep valid MX and implicit-MX destinations untouched

## 0.1

- initial Postfix policy-daemon proof of concept
