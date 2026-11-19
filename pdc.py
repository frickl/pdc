#!/usr/bin/env python3

import ipaddress
import os
import sys
import time
from pathlib import Path

import dns.exception
import dns.resolver


VERSION = "0.3.0"
BASE_DIR = Path(os.environ.get("PDC_CONFIG_DIR", "/opt/pdc"))
KNOWN_DOMAINS_FILE = BASE_DIR / "domains.txt"
TYPO_MAP_FILE = BASE_DIR / "typo-map.txt"

CACHE_TTL = int(os.environ.get("PDC_CACHE_TTL", "300"))

resolver = dns.resolver.Resolver(configure=True)
resolver.timeout = float(os.environ.get("PDC_DNS_TIMEOUT", "2.0"))
resolver.lifetime = float(os.environ.get("PDC_DNS_LIFETIME", "4.0"))

_cache = {}
_known_domains = set()
_typo_map = {}
_known_domains_mtime = None
_typo_map_mtime = None


def log_event(**fields):
    parts = []
    for key, value in fields.items():
        if value is None or value == "":
            continue
        value = str(value).replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'{key}="{value}"')
    print("pdc: " + " ".join(parts), file=sys.stderr, flush=True)


def _file_mtime(path: Path):
    try:
        return path.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def load_known_domains():
    result = set()
    if not KNOWN_DOMAINS_FILE.exists():
        return result

    with KNOWN_DOMAINS_FILE.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.split("#", 1)[0].strip().lower()
            if line:
                result.add(line.rstrip("."))
    return result


def load_typo_map():
    result = {}
    if not TYPO_MAP_FILE.exists():
        return result

    with TYPO_MAP_FILE.open("r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue

            parts = line.split()
            if len(parts) != 2:
                log_event(action="config_error", file=TYPO_MAP_FILE, line=lineno,
                          error="expected '<wrong> <correct>'")
                continue

            wrong, correct = (p.lower().rstrip(".") for p in parts)
            result[wrong] = correct
    return result


def refresh_lists():
    global _known_domains, _typo_map
    global _known_domains_mtime, _typo_map_mtime

    known_mtime = _file_mtime(KNOWN_DOMAINS_FILE)
    typo_mtime = _file_mtime(TYPO_MAP_FILE)

    if known_mtime != _known_domains_mtime:
        _known_domains = load_known_domains()
        _known_domains_mtime = known_mtime

    if typo_mtime != _typo_map_mtime:
        _typo_map = load_typo_map()
        _typo_map_mtime = typo_mtime


def edit_distance_one(a: str, b: str) -> bool:
    """One substitution/insertion/deletion or one adjacent transposition."""
    if a == b:
        return False

    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        if len(diffs) == 2:
            i, j = diffs
            return j == i + 1 and a[i] == b[j] and a[j] == b[i]
        return False

    if abs(len(a) - len(b)) != 1:
        return False

    short, long = (a, b) if len(a) < len(b) else (b, a)
    i = j = errors = 0

    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        else:
            errors += 1
            j += 1
            if errors > 1:
                return False

    return True


def typo_suggestion(domain: str):
    refresh_lists()

    explicit = _typo_map.get(domain)
    if explicit:
        return explicit

    matches = [known for known in _known_domains if edit_distance_one(domain, known)]
    return matches[0] if len(matches) == 1 else None


def resolve_rr(name: str, rrtype: str):
    return resolver.resolve(name, rrtype, raise_on_no_answer=False)


def is_loopback_ip(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def host_addresses(host: str):
    addresses = []
    for rrtype in ("A", "AAAA"):
        try:
            answer = resolve_rr(host, rrtype)
            if answer.rrset:
                addresses.extend(str(rr) for rr in answer)
        except dns.resolver.NoAnswer:
            pass
    return addresses


def hostname_is_localhost(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == "localhost" or host.endswith(".localhost") or host == "localhost.localdomain"


def mx_is_usable(host: str) -> bool:
    host = host.lower().rstrip(".")
    if hostname_is_localhost(host):
        return False

    addresses = host_addresses(host)
    if not addresses:
        return False

    return any(not is_loopback_ip(addr) for addr in addresses)


def implicit_mx_is_usable(domain: str) -> bool:
    addresses = host_addresses(domain)
    return bool(addresses) and any(not is_loopback_ip(addr) for addr in addresses)


def failure(domain: str, reason_code: str, phrase: str):
    suggestion = typo_suggestion(domain)
    if suggestion:
        text = f'The recipient domain "{domain}" {phrase}. Did you mean "{suggestion}"?'
    else:
        text = f'The recipient domain "{domain}" {phrase}. Please check the recipient address.'
    return "reject", text, reason_code, suggestion


def check_domain(domain: str):
    now = time.time()
    cached = _cache.get(domain)
    if cached and cached[0] > now:
        return cached[1]

    try:
        mx = resolve_rr(domain, "MX")

        if mx.rrset:
            records = list(mx)
            null_mx = any(int(rr.preference) == 0 and str(rr.exchange) == "." for rr in records)

            if null_mx:
                result = failure(domain, "null_mx", "explicitly does not accept email")
            else:
                mx_hosts = [str(rr.exchange).rstrip(".") for rr in records]
                usable = any(mx_is_usable(host) for host in mx_hosts)
                if usable:
                    result = ("ok", None, "valid_mx", None)
                else:
                    result = failure(domain, "unusable_mx", "does not have a usable mail exchanger")

        else:
            if implicit_mx_is_usable(domain):
                result = ("ok", None, "implicit_mx", None)
            else:
                result = failure(domain, "no_mail_route", "does not accept email")

    except dns.resolver.NXDOMAIN:
        result = failure(domain, "nxdomain", "does not exist")

    except (dns.resolver.NoNameservers, dns.resolver.LifetimeTimeout, dns.exception.Timeout):
        result = (
            "defer",
            f'The recipient domain "{domain}" cannot currently be resolved. Please try again later.',
            "dns_tempfail",
            None,
        )

    except dns.resolver.YXDOMAIN:
        result = (
            "reject",
            f'The recipient domain "{domain}" is invalid. Please check the recipient address.',
            "invalid_domain",
            None,
        )

    _cache[domain] = (now + CACHE_TTL, result)
    return result


def normalize_domain(recipient: str):
    if "@" not in recipient:
        return None

    domain = recipient.rsplit("@", 1)[1].strip().lower().rstrip(".")
    if not domain:
        return None

    return domain.encode("idna").decode("ascii")


def handle(req):
    if req.get("protocol_state") != "RCPT":
        return "DUNNO"

    # Intended for authenticated submission/MSA traffic only.
    if not req.get("sasl_username"):
        return "DUNNO"

    recipient = req.get("recipient", "")

    try:
        domain = normalize_domain(recipient)
    except UnicodeError:
        log_event(action="reject", sasl=req.get("sasl_username"), recipient=recipient,
                  reason="invalid_domain")
        return "550 5.1.2 Invalid recipient domain. Please check the recipient address."

    if not domain:
        return "DUNNO"

    status, text, reason, suggestion = check_domain(domain)

    if status == "ok":
        return "DUNNO"

    log_event(
        action=status,
        sasl=req.get("sasl_username"),
        recipient=recipient,
        domain=domain,
        reason=reason,
        suggestion=suggestion,
    )

    if status == "reject":
        return f"550 5.1.2 {text}"

    if status == "defer":
        return f"450 4.1.2 {text}"

    return "DUNNO"


def main():
    refresh_lists()
    req = {}

    for raw in sys.stdin:
        line = raw.rstrip("\n")

        if line:
            if "=" in line:
                key, value = line.split("=", 1)
                req[key] = value
            continue

        try:
            action = handle(req)
        except Exception as exc:
            log_event(action="internal_error", error=repr(exc))
            action = "DUNNO"

        print(f"action={action}")
        print()
        sys.stdout.flush()
        req = {}


if __name__ == "__main__":
    main()
