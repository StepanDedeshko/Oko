import html
import re


def plain_text_to_safe_html_with_links(text: str) -> str:
    """Safely render plain notes as HTML with clickable http(s) links."""
    escaped = html.escape(str(text or ""), quote=True)
    url_re = re.compile(r"(https?://[^\s<]+)")

    def repl(match):
        url = match.group(1)
        trailing = ""
        while url and url[-1] in ".,;:)!?]}":
            trailing = url[-1] + trailing
            url = url[:-1]
        return f'<a href="{url}">{url}</a>{trailing}'

    return url_re.sub(repl, escaped).replace("\n", "<br>")
