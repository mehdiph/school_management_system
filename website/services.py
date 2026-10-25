"""
Writes and rules of the public contact form: who the sender's device
is, whether they have sent too much, and saving the message.
"""

import ipaddress
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from django.utils.crypto import salted_hmac

from .models import ContactMessage


def _meta_key(header):
    """'CF-Connecting-IP' -> 'HTTP_CF_CONNECTING_IP'; META keys pass through."""
    header = header.strip()
    if header.upper().startswith("HTTP_") or header == "REMOTE_ADDR":
        return header.upper()
    return "HTTP_" + header.upper().replace("-", "_")


def _parse_ip(value):
    # A proxy chain ("client, proxy1") starts with the client.
    value = (value or "").split(",")[0].strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return ""


def client_ip(request):
    """
    The visitor's IP, from ``settings.CLIENT_IP_HEADER`` (the CDN's or
    nginx's client-IP header), falling back to ``REMOTE_ADDR``.
    """

    header = getattr(settings, "CLIENT_IP_HEADER", "")
    if header:
        ip = _parse_ip(request.META.get(_meta_key(header)))
        if ip:
            return ip
    return _parse_ip(request.META.get("REMOTE_ADDR"))


def client_ip_hash(request):
    """An HMAC of the IP (keyed with SECRET_KEY): the raw IP is never stored."""
    return salted_hmac("website.contact.ip", client_ip(request), algorithm="sha256").hexdigest()


def rate_limited(ip_hash, mobile):
    """
    True when this device or this mobile number has reached the short
    window (``CONTACT_RATE_LIMIT``), or this device the 24-hour cap
    (``CONTACT_DAILY_LIMIT``). One query.
    """

    limit, seconds = settings.CONTACT_RATE_LIMIT
    now = timezone.now()
    short_since = now - timedelta(seconds=seconds)
    counts = ContactMessage.objects.filter(
        Q(ip_hash=ip_hash) | Q(mobile=mobile),
        created_at__gte=now - timedelta(days=1),
    ).aggregate(
        ip_short=Count("pk", filter=Q(ip_hash=ip_hash, created_at__gte=short_since)),
        mobile_short=Count("pk", filter=Q(mobile=mobile, created_at__gte=short_since)),
        ip_day=Count("pk", filter=Q(ip_hash=ip_hash)),
    )
    return (
        counts["ip_short"] >= limit
        or counts["mobile_short"] >= limit
        or counts["ip_day"] >= settings.CONTACT_DAILY_LIMIT
    )


def submit_contact_message(cleaned_data, ip_hash):
    topic = cleaned_data.get("topic")
    location = cleaned_data.get("location")
    return ContactMessage.objects.create(
        name=cleaned_data["name"],
        mobile=cleaned_data["mobile"],
        topic=topic.title if topic else "",
        location=location.display_title if location else "",
        message=cleaned_data["message"],
        ip_hash=ip_hash,
    )
