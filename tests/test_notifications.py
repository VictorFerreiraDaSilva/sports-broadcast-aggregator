"""Testes do sistema de notificação de erros (ADR 0007).

Nada aqui toca rede nem banco: `requests.post` é sempre substituído e o
notificador é chamado direto. O objetivo é fixar as três garantias em que o
resto do código confia — o coletor pega o que deve e só o que deve, a
notificação nunca propaga exceção, e a tabela de severidade não muda por
acidente.
"""

from __future__ import annotations

import logging
import threading

import pytest

from app.core import notify as notify_mod
from app.core.errors import APP_LOGGER_NAME, collect_errors


# --------------------------------------------------------------------------
# Coletor (app/core/errors.py)
# --------------------------------------------------------------------------


def test_agrupa_erros_pela_assinatura_e_nao_pela_mensagem_formatada():
    """As 16 falhas de "erro ao buscar %s %s" viram um grupo, não 16 linhas."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for sport in ("futebol", "basquete"):
            for day in ("2026-08-27", "2026-08-28"):
                log.error("erro ao buscar %s %s: %s", sport, day, "HTTP 503")

    assert collected
    assert collected.total == 4
    assert len(collected.groups) == 1

    (group,) = collected.groups.values()
    assert group.count == 4
    assert group.first_message == "erro ao buscar futebol 2026-08-27: HTTP 503"

    summary = collected.summary()
    # sem exc_info, o cabeçalho é o módulo sem o prefixo "app."
    assert "sources.fake ×4" in summary
    assert "(+3 iguais)" in summary


def test_separa_grupos_por_tipo_de_excecao():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        try:
            raise KeyError("time")
        except KeyError:
            log.exception("jogo descartado")
        try:
            raise ValueError("horário")
        except ValueError:
            log.exception("jogo descartado")

    assert len(collected.groups) == 2
    assert {g.exc_type for g in collected.groups.values()} == {"KeyError", "ValueError"}


def test_ignora_niveis_abaixo_de_error():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        log.info("coletando")
        log.warning("canal não casou")

    assert not collected
    assert collected.total == 0


def test_ignora_loggers_fora_da_arvore_da_aplicacao():
    """Um log.error de urllib3 ou do SQLAlchemy não é falha de coleta."""
    with collect_errors() as collected:
        logging.getLogger("urllib3.connectionpool").error("Retrying after connection broken")
        logging.getLogger("sqlalchemy.engine").error("algo genérico")

    assert not collected


def test_ignora_erros_de_outra_thread():
    """O APScheduler roda jobs num pool — os erros de um job não podem vazar
    para a notificação de outro."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    started = threading.Event()

    def outra_coleta():
        started.wait(timeout=5)
        log.error("erro de outro job")

    thread = threading.Thread(target=outra_coleta)

    with collect_errors() as collected:
        thread.start()
        started.set()
        thread.join(timeout=5)
        log.error("erro deste job")

    assert collected.total == 1
    (group,) = collected.groups.values()
    assert group.first_message == "erro deste job"


def test_handler_e_removido_ao_sair_do_bloco():
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    antes = len(app_logger.handlers)

    with collect_errors():
        assert len(app_logger.handlers) == antes + 1

    assert len(app_logger.handlers) == antes


def test_summary_resume_quando_ha_grupos_demais():
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for i in range(8):
            log.error("erro tipo %d ocorrido" % i)  # noqa: UP031 - template distinto de propósito

    assert len(collected.groups) == 8
    assert "(+3 outro(s) tipo(s) de erro)" in collected.summary()


# --------------------------------------------------------------------------
# Notificador (app/core/notify.py)
# --------------------------------------------------------------------------


@pytest.fixture()
def pushover_configurado(monkeypatch):
    """Credenciais falsas + captura do POST, sem tocar a rede."""
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "token-de-teste")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "user-de-teste")
    monkeypatch.setattr(notify_mod, "PUSHOVER_APP_NAME", "fut-test")

    enviados = []

    class FakeResponse:
        status_code = 200
        text = '{"status":1}'

    def fake_post(url, data=None, timeout=None):
        enviados.append(data)
        return FakeResponse()

    monkeypatch.setattr(notify_mod.requests, "post", fake_post)
    return enviados


def test_sem_credencial_vira_no_op(monkeypatch):
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "")

    def explode(*args, **kwargs):
        raise AssertionError("não deveria tocar a rede sem credencial")

    monkeypatch.setattr(notify_mod.requests, "post", explode)

    assert notify_mod.notify("título", "corpo") is False


def test_envia_com_prefixo_e_prioridade(pushover_configurado):
    assert notify_mod.notify("futnatv/games falhou", "corpo", priority=1) is True

    (payload,) = pushover_configurado
    assert payload["title"] == "fut-test · futnatv/games falhou"
    assert payload["message"] == "corpo"
    assert payload["priority"] == 1


def test_trunca_nos_limites_da_api(pushover_configurado):
    notify_mod.notify("t" * 500, "m" * 5000)

    (payload,) = pushover_configurado
    assert len(payload["title"]) == 250
    assert len(payload["message"]) == 1024
    assert payload["message"].endswith("…")


def test_falha_de_envio_nunca_propaga(monkeypatch):
    monkeypatch.setattr(notify_mod, "PUSHOVER_TOKEN", "token-de-teste")
    monkeypatch.setattr(notify_mod, "PUSHOVER_USER_KEY", "user-de-teste")

    def explode(*args, **kwargs):
        raise ConnectionError("rede fora")

    monkeypatch.setattr(notify_mod.requests, "post", explode)

    assert notify_mod.notify("título", "corpo") is False


def test_resposta_nao_200_devolve_false(monkeypatch, pushover_configurado):
    class Recusa:
        status_code = 400
        text = '{"errors":["application token is invalid"]}'

    monkeypatch.setattr(notify_mod.requests, "post", lambda *a, **k: Recusa())

    assert notify_mod.notify("título", "corpo") is False


# --------------------------------------------------------------------------
# Tabela de severidade (app/core/jobs.py::_notify_result)
# --------------------------------------------------------------------------


class FakeSource:
    code = "fonte-teste"
    name = "Fonte de Teste"


@pytest.fixture()
def notificacoes(monkeypatch):
    """Captura o que `jobs` mandaria notificar, sem passar pelo Pushover."""
    from app.core import jobs

    capturadas = []
    monkeypatch.setattr(
        jobs,
        "notify",
        lambda title, message, priority=0: capturadas.append((title, message, priority)),
    )
    return jobs, capturadas


def _collected(*mensagens):
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    with collect_errors() as collected:
        for msg in mensagens:
            log.error(msg)
    return collected


def test_execucao_limpa_nao_notifica(notificacoes):
    jobs, capturadas = notificacoes
    jobs._notify_result(
        "games", FakeSource(), "success", {"games_count": 142}, None, _collected(), 7
    )
    assert capturadas == []


def test_job_que_falhou_notifica_em_prioridade_normal(notificacoes):
    jobs, capturadas = notificacoes
    jobs._notify_result(
        "games", FakeSource(), "error", {}, "ConnectionError: rede fora", _collected(), 7
    )

    (title, message, priority) = capturadas[0]
    assert title == "fonte-teste/games falhou"
    assert priority == notify_mod.PRIORITY_ERROR
    assert "ConnectionError: rede fora" in message
    assert "run #7" in message


def test_erro_parcial_notifica_como_degradado(notificacoes):
    jobs, capturadas = notificacoes
    jobs._notify_result(
        "games",
        FakeSource(),
        "success",
        {"games_count": 142},
        None,
        _collected("falhou a", "falhou b"),
        7,
    )

    (title, message, priority) = capturadas[0]
    assert title == "fonte-teste/games degradado"
    assert priority == notify_mod.PRIORITY_WARNING
    assert "2 erros engolidos" in message
    assert "142 jogo(s) gravado(s)" in message


def test_coleta_vazia_sem_erro_notifica(notificacoes):
    jobs, capturadas = notificacoes
    jobs._notify_result("games", FakeSource(), "success", {"games_count": 0}, None, _collected(), 7)

    (title, _message, priority) = capturadas[0]
    assert title == "fonte-teste/games sem jogos"
    assert priority == notify_mod.PRIORITY_WARNING


def test_catalogo_vazio_nao_dispara_a_regra_de_zero_jogos(notificacoes):
    """A regra de "sem jogos" é do job de games; um catálogo que só pulou
    (versão inalterada) é sucesso legítimo."""
    jobs, capturadas = notificacoes
    jobs._notify_result(
        "catalog", FakeSource(), "success", {"skipped": True}, None, _collected(), 7
    )
    assert capturadas == []


def test_no_maximo_uma_notificacao_por_execucao(notificacoes):
    jobs, capturadas = notificacoes
    jobs._notify_result(
        "games",
        FakeSource(),
        "error",
        {"games_count": 0},
        "boom",
        _collected("parcial a", "parcial b"),
        7,
    )
    assert len(capturadas) == 1


# --------------------------------------------------------------------------
# Espera pelo banco (app/core/wait_for_db.py)
# --------------------------------------------------------------------------


class FakeEngine:
    """Falha `falhas` vezes antes de conectar."""

    def __init__(self, falhas: int):
        self.falhas = falhas
        self.tentativas = 0

    def connect(self):
        self.tentativas += 1
        if self.tentativas <= self.falhas:
            raise OSError("connection refused")
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, _stmt):
        return None


@pytest.fixture()
def wait_mod(monkeypatch):
    from app.core import wait_for_db as mod

    monkeypatch.setattr(mod.time, "sleep", lambda _s: None)
    capturadas = []
    monkeypatch.setattr(
        mod, "notify", lambda title, message, priority=0: capturadas.append((title, priority))
    )
    return mod, capturadas


def test_banco_disponivel_de_primeira_nao_notifica(wait_mod):
    mod, capturadas = wait_mod
    mod.wait_for_db(FakeEngine(falhas=0))
    assert capturadas == []


def test_falha_curta_nao_notifica(wait_mod, monkeypatch):
    """Um restart rotineiro do Postgres não deve virar push."""
    mod, capturadas = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 3600)
    mod.wait_for_db(FakeEngine(falhas=3))
    assert capturadas == []


def test_falha_prolongada_notifica_uma_vez_e_avisa_da_recuperacao(wait_mod, monkeypatch):
    mod, capturadas = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 0)

    engine = FakeEngine(falhas=5)
    mod.wait_for_db(engine)

    assert engine.tentativas == 6
    assert [t for t, _p in capturadas] == ["banco inacessível", "banco recuperado"]
    assert capturadas[0][1] == notify_mod.PRIORITY_CRITICAL
    assert capturadas[1][1] == notify_mod.PRIORITY_WARNING


def test_teto_de_espera_levanta(wait_mod, monkeypatch):
    mod, _capturadas = wait_mod
    monkeypatch.setattr(mod, "DB_WAIT_MAX_SECONDS", 0.0001)
    monkeypatch.setattr(mod, "DB_WAIT_NOTIFY_AFTER_SECONDS", 3600)

    with pytest.raises(RuntimeError, match="banco inacessível"):
        mod.wait_for_db(FakeEngine(falhas=99))


# --------------------------------------------------------------------------
# Persistência do estado degradado (app/core/jobs.py::_run + scrape_run)
# --------------------------------------------------------------------------


def test_as_records_leva_todos_os_grupos_estruturados():
    """`summary()` é texto cortado para caber no Pushover; `as_records()` é o
    que vai para o banco e não corta nada."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        for i in range(8):
            log.error("erro tipo %d ocorrido" % i)  # noqa: UP031
        log.error("erro tipo %d ocorrido" % 0)  # noqa: UP031 - repete o primeiro

    assert "(+3 outro(s) tipo(s) de erro)" in collected.summary()

    registros = collected.as_records()
    assert len(registros) == 8, "as_records não corta em MAX_GROUPS_IN_SUMMARY"
    assert sum(r["count"] for r in registros) == collected.total == 9
    assert registros[0] == {
        "label": "sources.fake",
        "logger": "app.sources.fake",
        "template": "erro tipo 0 ocorrido",
        "exc_type": None,
        "count": 2,
        "example": "erro tipo 0 ocorrido",
    }


def test_as_records_distingue_tipos_de_erro_do_mesmo_modulo():
    """`label` cai no nome do módulo quando não há exc_info, então dois erros
    diferentes da mesma fonte colidiriam numa agregação. `template` é o campo
    que os separa."""
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")

    with collect_errors() as collected:
        log.error("erro ao buscar %s %s: %s", "futebol", "2026-08-27", "HTTP 503")
        log.error("jogo descartado (%s %s): %s", "volei", "2026-08-27", "KeyError")

    registros = collected.as_records()
    assert len({r["label"] for r in registros}) == 1, "label sozinho não distingue"
    assert {r["template"] for r in registros} == {
        "erro ao buscar %s %s: %s",
        "jogo descartado (%s %s): %s",
    }


def _example_source_que_loga(mensagens, explode=None):
    """ExampleSource com `fetch_games` instrumentado para logar erros (e,
    opcionalmente, estourar) antes de devolver os jogos hardcoded."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    original = source.fetch_games
    log = logging.getLogger("app.sources._example.source")

    def fetch_games(session, dates):
        for sport, dia in mensagens:
            log.error("erro ao buscar %s %s: %s", sport, dia, "HTTP 503")
        if explode is not None:
            raise explode
        return original(session, dates)

    source.fetch_games = fetch_games
    return source


@pytest.fixture()
def jobs_sem_push(monkeypatch):
    """`jobs` real contra o banco real, só com o Pushover desligado."""
    from app.core import jobs

    monkeypatch.setattr(jobs, "notify", lambda *a, **k: None)
    return jobs


def _ultimo_run(db_session):
    from app.core.models import ScrapeRun

    return db_session.query(ScrapeRun).order_by(ScrapeRun.id.desc()).first()


def test_execucao_limpa_grava_success_sem_ruido(db_session, jobs_sem_push):
    resultado = jobs_sem_push.run_games_scrape(_example_source_que_loga([]))

    assert resultado["status"] == "success"

    run = _ultimo_run(db_session)
    assert run.status == "success"
    assert run.error_message is None
    assert run.details["games_count"] > 0
    assert "errors_collected" not in run.details
    assert "error_groups" not in run.details


def test_erro_engolido_grava_degraded_com_os_grupos(db_session, jobs_sem_push):
    """O ponto do item: uma execução que só notificava não podia continuar
    sendo contada como sucesso limpo por quem consultasse `scrape_run`."""
    source = _example_source_que_loga(
        [("futebol", "2026-08-27"), ("futebol", "2026-08-28"), ("basquete", "2026-08-27")]
    )
    resultado = jobs_sem_push.run_games_scrape(source)

    assert resultado["status"] == "degraded"

    run = _ultimo_run(db_session)
    assert run.status == "degraded"
    # a falha fatal continua sendo a única dona de error_message
    assert run.error_message is None
    # gravou o que deu: degradado não é o mesmo que perdido
    assert run.details["games_count"] > 0
    assert run.details["errors_collected"] == 3

    (grupo,) = run.details["error_groups"]
    assert grupo["count"] == 3
    assert grupo["label"] == "sources._example.source"
    assert grupo["logger"] == "app.sources._example.source"
    assert grupo["example"] == "erro ao buscar futebol 2026-08-27: HTTP 503"


def test_falha_fatal_continua_error_mas_preserva_os_parciais(db_session, jobs_sem_push):
    """Um run que engoliu erros e depois morreu é `error` — a falha fatal é a
    mais grave —, mas os parciais deixam de se perder."""
    source = _example_source_que_loga(
        [("futebol", "2026-08-27"), ("volei", "2026-08-27")],
        explode=ConnectionError("rede fora"),
    )
    resultado = jobs_sem_push.run_games_scrape(source)

    assert resultado["status"] == "error"

    run = _ultimo_run(db_session)
    assert run.status == "error"
    assert run.error_message == "ConnectionError: rede fora"
    assert run.details["errors_collected"] == 2
    assert len(run.details["error_groups"]) == 1


def test_coleta_vazia_sem_erro_continua_success(db_session, jobs_sem_push):
    """"Sem jogos" notifica, mas não é degradação: nenhum erro aconteceu. O
    sinal fica em games_count, não num quarto valor de status."""
    from app.sources._example.source import ExampleSource

    source = ExampleSource()
    source.fetch_games = lambda session, dates: []

    resultado = jobs_sem_push.run_games_scrape(source)
    assert resultado["status"] == "success"

    run = _ultimo_run(db_session)
    assert run.status == "success"
    assert run.details["games_count"] == 0
    assert "errors_collected" not in run.details


def test_coletor_nao_emudece_com_nivel_de_log_alto():
    """Um `basicConfig(level=CRITICAL)` não pode desligar a notificação em
    silêncio: `log.error` nem chega a criar o registro se o nível efetivo
    estiver acima de ERROR."""
    app_logger = logging.getLogger(APP_LOGGER_NAME)
    log = logging.getLogger(f"{APP_LOGGER_NAME}.sources.fake")
    nivel_original = app_logger.level
    app_logger.setLevel(logging.CRITICAL)
    try:
        with collect_errors() as collected:
            log.error("erro que seria engolido pelo nível de log")
        assert collected.total == 1
        # e o nível é restaurado ao sair
        assert app_logger.level == logging.CRITICAL
    finally:
        app_logger.setLevel(nivel_original)
