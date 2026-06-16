"""Liens affiliés RÉELS de ChannelOS. N'ajouter qu'un lien réellement obtenu."""

AFFILIATE_LINKS = {
    "Make.com": "https://www.make.com/en/register?pc=founderiahub",
    "Make":     "https://www.make.com/en/register?pc=founderiahub",
}

AFFILIATE_DISCLOSURE = "Some links above are affiliate links — using them supports the channel at no extra cost to you."


def build_affiliate_block(text_fields):
    haystack = " ".join(t for t in text_fields if t).lower()
    seen_urls, lines = set(), []
    for tool, url in AFFILIATE_LINKS.items():
        if tool.lower() in haystack and url not in seen_urls:
            seen_urls.add(url)
            lines.append(f"🔗 {tool}: {url}")
    if not lines:
        return ""
    return "\n".join(lines) + "\n\n" + AFFILIATE_DISCLOSURE
