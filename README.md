# pdc

**Plausible Domain Check** is a small Postfix policy daemon for submission/MSA
servers. It checks recipient domains during `RCPT TO`, before a message enters
the queue, and returns readable SMTP errors for obvious domain mistakes.

The goal is deliberately narrow: catch clearly broken recipient domains early
and, when possible, suggest a plausible correction without second-guessing
valid mail domains.

## Behaviour

- usable MX -> `DUNNO`
- RFC 7505 Null MX (`MX 0 .`) -> `550`
- MX target `localhost` / `*.localhost` -> `550`
- MX targets resolving only to loopback (`127.0.0.0/8`, `::1`) -> `550`
- MX target with no A/AAAA -> `550`
- no MX, but usable A/AAAA implicit-MX fallback -> `DUNNO`
- no usable mail route -> `550`
- NXDOMAIN -> `550`
- DNS temporary failure / SERVFAIL / timeout -> `450`
- internal PDC failure -> fail open (`DUNNO`)

A domain with a usable MX or implicit MX is **never rejected merely because it
looks similar to another domain**.

Typo suggestions are based on the external `domains.txt` reference list and an
optional `typo-map.txt`. Matching is intentionally conservative:

- one substituted character
- one inserted character
- one deleted character
- one adjacent transposition

This also catches simple TLD mistakes such as `kabelmail.co` ->
`kabelmail.com`, provided the entered destination itself is not mail-capable.

## Logging

PDC does not log successful/allowed recipients. It logs only when it acts
(`reject` or `defer`), plus configuration/internal errors.

Example:

```text
pdc: action="reject" sasl="user@example.org" recipient="x@gimail.com" domain="gimail.com" reason="unusable_mx" suggestion="gmail.com"
```

Temporary DNS failure:

```text
pdc: action="defer" sasl="user@example.org" recipient="x@example.invalid" domain="example.invalid" reason="dns_tempfail"
```

## Requirements

- Python 3
- `dnspython`
- Postfix policy delegation (`check_policy_service`)

Debian/Ubuntu:

```sh
apt install python3-dnspython
```

## Installation

```sh
mkdir -p /opt/pdc
install -m 0755 pdc.py /opt/pdc/
install -m 0644 domains.txt typo-map.txt /opt/pdc/
```

Add the service from [`examples/master.cf`](examples/master.cf) to the
submission Postfix instance.

The important restriction order is:

```text
reject_non_fqdn_recipient,
check_policy_service unix:private/pdc,
permit_mynetworks,
permit_sasl_authenticated,
...
```

PDC must be before `permit_mynetworks` and `permit_sasl_authenticated`, because
Postfix restriction lists stop at the first decisive result.

For this MSA path, `reject_unknown_recipient_domain` can be omitted because PDC
performs the relevant DNS checks itself and can return a more useful reply.

After configuration:

```sh
postfix check
postfix reload
```

## Manual policy test

```sh
/opt/pdc/pdc.py
```

Then enter a policy request followed by an empty line:

```text
protocol_state=RCPT
sasl_username=testuser
recipient=someone@gimail.com

```

An unusable domain close to a known reference domain may return:

```text
action=550 5.1.2 The recipient domain "gimail.com" does not have a usable mail exchanger. Did you mean "gmail.com"?
```

A valid mail-capable domain returns:

```text
action=DUNNO
```

## `domains.txt`

A plain external list of canonical mail domains. There is no weighting. Edit
the file as needed; PDC reloads it automatically when its mtime changes.

## `typo-map.txt`

Optional explicit high-confidence mappings:

```text
gamil.com gmail.com
gimail.com gmail.com
```

Mappings are consulted only after the entered destination is already known not
to have a usable mail route. They never override a valid MX or implicit MX.

## Environment variables

- `PDC_CONFIG_DIR` (default `/opt/pdc`)
- `PDC_CACHE_TTL` (default `300` seconds)
- `PDC_DNS_TIMEOUT` (default `2.0` seconds)
- `PDC_DNS_LIFETIME` (default `4.0` seconds)

## Tests

```sh
python3 -m unittest discover -s tests -v
```

## Non-goals

PDC deliberately does not:

- probe remote SMTP recipients
- automatically rewrite recipient addresses
- reject working domains because they resemble another domain
- parse Postfix queues or logs
- maintain local-host/IP exception lists

## License

MIT. See [`LICENSE`](LICENSE).


## DNS query behavior and Postfix configuration

PDC performs the recipient-domain DNS checks itself. On an MSA/submission
instance, do **not** also use `reject_unknown_recipient_domain` unless you
intentionally want duplicate checks.

Recommended:

```text
smtpd_recipient_restrictions =
    reject_non_fqdn_recipient,
    check_policy_service unix:private/pdc,
    permit_mynetworks,
    permit_sasl_authenticated,
    ...
```

Avoid:

```text
smtpd_recipient_restrictions =
    reject_non_fqdn_recipient,
    reject_unknown_recipient_domain,
    check_policy_service unix:private/pdc,
    ...
```

PDC already covers the relevant recipient-domain cases and can return clearer
user-facing SMTP replies. Keeping both checks normally adds no value and may
cause duplicate DNS lookups.

PDC queries MX first. A/AAAA lookups are only performed when no MX RRset
exists, to support the RFC 5321 implicit-MX fallback. A valid MX or Null MX
therefore normally needs only one resolver lookup.

For best efficiency, configure PDC and Postfix to use the same local caching
resolver, for example Unbound or BIND on localhost. Repeated lookups by PDC,
Postfix, or later `smtp(8)` delivery attempts will then usually be satisfied
from the resolver cache instead of causing additional external DNS traffic.

The Postfix policy protocol does not expose the DNS result of
`reject_unknown_recipient_domain` to PDC, so PDC cannot directly reuse that
internal Postfix lookup result without a Postfix code change.
