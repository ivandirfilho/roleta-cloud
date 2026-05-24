# Roleta Cloud - Configuração de Logging Estruturado

import logging
import sys

import structlog


def setup_logging(log_file: str = "roleta.log", level: int = logging.INFO):
    """
    Configura logging estruturado com structlog.
    
    Em produção: JSON para arquivo (machine-readable)
    Em console: formato colorido e legível
    """
    # Processors compartilhados
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # Configurar structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Console handler — formato legível
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
            foreign_pre_chain=shared_processors,
        )
    )

    # File handler — JSON para análise
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    )

    # Configurar root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(level)

    # Silenciar loggers verbosos de terceiros
    logging.getLogger("websockets").setLevel(logging.WARNING)

    return structlog.get_logger()


def bind_strategy_version(version: str, git_tag: str | None = None) -> None:
    """S3: bind context vars de strategia/git_tag em TODOS os logs subsequentes.

    Usar no startup do app, lendo VERSION + strategy_versions.git_tag.
    """
    structlog.contextvars.bind_contextvars(
        strategy_version=version,
        git_tag=git_tag or version,
    )
