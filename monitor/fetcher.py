"""Downloads store pages."""

import requests

# Identifies the program honestly, as the scraping rules require.
HEADERS = {
    "User-Agent": "MonitorDePrecos/0.1 (projeto pessoal de estudo)",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9",
}
TIMEOUT_SECONDS = (5, 20)  # (connect, read)


class FetchError(Exception):
    """The page could not be downloaded. The message is shown on the site."""


def fetch_html(url: str) -> str:
    try:
        response = requests.get(url, headers=HEADERS, timeout=TIMEOUT_SECONDS)
    except requests.Timeout:
        raise FetchError("A loja demorou demais para responder.") from None
    except requests.RequestException as error:
        raise FetchError(f"Erro de conexão: {error.__class__.__name__}.") from None

    if response.status_code in (403, 429):
        raise FetchError(f"A loja bloqueou o acesso automático (HTTP {response.status_code}).")
    if response.status_code != 200:
        raise FetchError(f"A loja respondeu com erro HTTP {response.status_code}.")

    return response.text
