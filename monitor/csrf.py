"""Proteção CSRF: cada formulário leva um segredo que só as páginas do site conhecem.

Sem isso, outro site pode fazer o seu navegador enviar um POST para cá (apagar um
produto, por exemplo). O navegador manda o cookie da sessão junto e o servidor obedece,
porque do lado dele o pedido parece normal. Esse ataque se chama CSRF.

A defesa: guardar um valor aleatório na sessão, repetir esse valor escondido dentro de
todo formulário nosso e recusar qualquer POST que não traga o mesmo valor. O site
atacante não consegue ler a nossa página (o navegador não deixa), então não sabe o valor.
"""

import secrets

from markupsafe import Markup, escape

FIELD_NAME = "csrf_token"  # nome do campo escondido no formulário
SESSION_KEY = "csrf_token"  # onde o valor fica guardado na sessão
TOKEN_BYTES = 32


def token_for(session) -> str:
    """O token desta sessão, criado na primeira vez e mantido enquanto ela durar."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(TOKEN_BYTES)
        session[SESSION_KEY] = token
    return token


def is_valid(session, sent: str | None) -> bool:
    """O que veio no formulário é mesmo o token da sessão?"""
    expected = session.get(SESSION_KEY)
    if not expected or not sent:
        return False
    # compare_digest compara sempre no mesmo tempo, para não entregar o token
    # aos poucos a quem cronometra as respostas (timing attack).
    return secrets.compare_digest(str(expected), str(sent))


def hidden_field(session) -> Markup:
    """O `<input type="hidden">` que os templates colocam dentro de cada formulário."""
    return Markup(f'<input type="hidden" name="{FIELD_NAME}" value="{escape(token_for(session))}">')
