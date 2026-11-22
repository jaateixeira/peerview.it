"""Composition root: the only place that wires adapters to ports."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI
from loguru import logger

from peerview.adapters.ai.catalog import Catalogue, LocalModels, Service, load_catalogue
from peerview.adapters.ai.jobs import ThreadedAiJobs
from peerview.adapters.ai.keys import load_house_keys
from peerview.adapters.ai.writers import HttpAiWriter
from peerview.adapters.auth.passwords import Argon2Hasher
from peerview.adapters.auth.registry import build_providers
from peerview.adapters.cache import ValkeyCache, make_cache
from peerview.adapters.console import show_startup, startup_panel
from peerview.adapters.entitlements import UnlimitedEntitlements
from peerview.adapters.logs import configure_logging
from peerview.adapters.mail import LogMailer, SmtpMailer
from peerview.adapters.persistence.cached_users import DEFAULT_TTL_SECONDS, CachedUserRepository
from peerview.adapters.persistence.engine import make_engine
from peerview.adapters.persistence.migrate import upgrade
from peerview.adapters.persistence.sql import (
    SqlEmailTokenRepository,
    SqlTenancyRepository,
    SqlUserRepository,
)
from peerview.adapters.persistence.sql_ai_reviews import SqlAiReviewRepository
from peerview.adapters.persistence.sql_calls import SqlCallRepository
from peerview.adapters.persistence.sql_credits import SqlCreditRepository
from peerview.adapters.persistence.sql_prepared import SqlPreparedRequestRepository
from peerview.adapters.persistence.sql_reviews import SqlReviewRepository
from peerview.adapters.persistence.sql_rounds import SqlRoundRepository
from peerview.adapters.persistence.sql_rubrics import SqlRubricRepository
from peerview.adapters.plugins import (
    discover_allocation_strategies,
    discover_artifact_types,
    discover_criterion_types,
)
from peerview.adapters.settings import Settings, load_settings
from peerview.adapters.web.app import build_app
from peerview.adapters.web_pages import HttpPageChecker, RecentChecks
from peerview.application.ai_reviews import AiReviewsService, AiWriter, ModelCatalog
from peerview.application.allocation import StrategyRegistry
from peerview.application.artifacts import ArtifactRegistry, PluginServices, connect_plugins
from peerview.application.auth import AuthService
from peerview.application.calls import CallsService
from peerview.application.credits import CreditsService
from peerview.application.criteria import CriterionRegistry
from peerview.application.feedback import FeedbackService
from peerview.application.invitations import InvitationsService
from peerview.application.ports import Mailer
from peerview.application.prepared_requests import PreparedRequestsService
from peerview.application.quick_review import QuickReviewService
from peerview.application.reviews import ReviewsService
from peerview.application.rounds import RoundsService
from peerview.application.rubrics import RubricsService
from peerview.application.tenancy import TenancyService
from peerview.application.verification import VerificationService
from peerview.application.web_pages import PageChecker, PageReader
from peerview.domain.credits import CreditPack, CreditPricing


def create_app() -> FastAPI:
    settings = load_settings(os.environ)
    configure_logging(settings.log_level)
    cache = make_cache(settings.cache_url)
    if settings.cache_url is None and int(os.environ.get("WEB_CONCURRENCY", "1") or 1) > 1:
        logger.warning(
            "several workers without a [cache] url: each keeps its own cache, so changes can "
            "take up to {}s to show in other workers. Configure Valkey.",
            DEFAULT_TTL_SECONDS,
        )
    # Dev convenience: SQLite is migrated automatically. PostgreSQL is migrated explicitly.
    if settings.database_url.startswith("sqlite"):
        upgrade(settings.database_url)
    engine = make_engine(settings.database_url)
    users = CachedUserRepository(SqlUserRepository(engine), cache)
    auth = AuthService(
        users,
        Argon2Hasher(),
        lambda: uuid.uuid4().hex,
    )
    providers = build_providers(settings)
    mailer = build_mailer(settings)
    artifact_types = discover_artifact_types()
    pages = build_page_checker(settings)
    reader = pages if isinstance(pages, PageReader) else None
    connect_plugins(artifact_types, PluginServices(pages=pages, reader=reader))
    verification = VerificationService(
        users,
        SqlEmailTokenRepository(engine),
        mailer,
        settings.base_url,
        lambda: datetime.now(UTC),
    )
    tenancy_repo = SqlTenancyRepository(engine)
    tenancy = TenancyService(
        tenancy_repo,
        users,
        lambda: uuid.uuid4().hex,
        lambda: datetime.now(UTC),
        policy=settings.verification_policy,
    )
    call_repo = SqlCallRepository(engine)
    calls = CallsService(
        call_repo,
        tenancy,
        tenancy_repo,
        users,
        ArtifactRegistry(artifact_types),
        UnlimitedEntitlements(),
        lambda: uuid.uuid4().hex,
        lambda: datetime.now(UTC),
        policy=settings.verification_policy,
    )
    criterion_types = CriterionRegistry(discover_criterion_types())
    rubric_repo = SqlRubricRepository(engine)
    rubrics = RubricsService(
        rubric_repo,
        call_repo,
        tenancy,
        criterion_types,
        lambda: uuid.uuid4().hex,
    )
    strategies = StrategyRegistry(discover_allocation_strategies())
    round_repo = SqlRoundRepository(engine)
    review_repo = SqlReviewRepository(engine)
    rounds = RoundsService(
        round_repo,
        review_repo,
        call_repo,
        tenancy,
        tenancy_repo,
        users,
        strategies,
        lambda: uuid.uuid4().hex,
        lambda: datetime.now(UTC),
    )
    invitations = InvitationsService(
        round_repo,
        call_repo,
        tenancy,
        tenancy_repo,
        users,
        UnlimitedEntitlements(),
        lambda: uuid.uuid4().hex,
        lambda: datetime.now(UTC),
        mailer=mailer,
        base_url=settings.base_url,
        policy=settings.verification_policy,
    )
    registry = ArtifactRegistry(artifact_types)
    quick = QuickReviewService(
        tenancy,
        calls,
        rounds,
        invitations,
        registry,
        users,
        lambda: datetime.now(UTC),
    )
    reviews = ReviewsService(
        review_repo,
        round_repo,
        call_repo,
        rubric_repo,
        tenancy,
        tenancy_repo,
        users,
        criterion_types,
        registry,
        lambda: uuid.uuid4().hex,
        lambda: datetime.now(UTC),
    )
    feedback = FeedbackService(  # ADR 0028: authors read their reviews when released
        round_repo,
        review_repo,
        call_repo,
        rubric_repo,
        tenancy,
        tenancy_repo,
        users,
        criterion_types,
        mailer,
        settings.base_url,
        lambda: datetime.now(UTC),
    )
    reviews.when_handed_in(feedback.handed_in)
    ai = None
    credits = CreditsService(  # ADR 0026: bought through Paddle, spent on AI reviews
        SqlCreditRepository(engine),
        users,
        [CreditPack(price, whole_euros) for price, whole_euros in settings.paddle_packs],
        ids=lambda: uuid.uuid4().hex,
        now=lambda: datetime.now(UTC),
    )
    if settings.paddle_client_token and settings.paddle_webhook_secret:
        logger.info(
            "Credit: sold through Paddle ({}), {} packs",
            settings.paddle_environment,
            len(settings.paddle_packs),
        )
        if not (settings.seller_legal_name and settings.seller_address and settings.seller_email):
            logger.warning("Fill in [seller]: Paddle's review reads the seller on /terms")
    if settings.ai_enabled:
        services, catalogue = build_ai_catalogue(settings)
        jobs = ThreadedAiJobs()
        ai = AiReviewsService(
            SqlAiReviewRepository(engine),
            catalogue,
            build_ai_writer(settings, services),
            jobs,
            calls,
            registry,
            users,
            UnlimitedEntitlements(),
            mailer,
            base_url=settings.base_url,
            ids=lambda: uuid.uuid4().hex,
            now=lambda: datetime.now(UTC),
            pricing=CreditPricing(
                usd_to_eur=Decimal(settings.ai_usd_to_eur),
                margin=Decimal(settings.ai_margin_percent) / 100,
                fees_and_tax=Decimal(settings.ai_fees_and_tax_percent) / 100,
            ),
            credits=credits,
            house_keys=load_house_keys(settings.ai_keys_file, set(services)),
        )
        jobs.bind(ai.run)
        ai.recover()  # what was queued when peerview.it stopped
        logger.info(
            "AI reviews: models from {}; free models from {}",
            ", ".join(s.name for s in services.values()),
            settings.ai_ollama_url or "nowhere (no [ai] ollama_url)",
        )
    mailer_mode = "SMTP" if isinstance(mailer, SmtpMailer) else "written to the log (development)"
    show_startup(
        startup_panel(
            settings,
            version=_version(),
            cache_kind="Valkey" if isinstance(cache, ValkeyCache) else "in-process",
            mail_mode=mailer_mode,
            providers=[p.value for p in providers],
            artifact_types=[t.key for t in registry.all()],
            log_level=settings.log_level,
        )
    )
    return build_app(
        settings,
        auth,
        verification,
        tenancy,
        calls,
        rubrics,
        rounds,
        reviews,
        invitations,
        quick,
        providers,
        pages=pages,
        prepared=PreparedRequestsService(
            SqlPreparedRequestRepository(engine),
            lambda: secrets.token_urlsafe(32),
            lambda: datetime.now(UTC),
        ),
        version=_version(),
        ai=ai,
        credits=credits,
        feedback=feedback,
    )


def build_ai_catalogue(settings: Settings) -> tuple[dict[str, Service], ModelCatalog]:
    """The models on offer (ADR 0025): the catalogue file, and the free models on peerview.it's
    own Ollama server when one is configured."""
    services, cards = load_catalogue()
    local = None
    if settings.ai_ollama_url:
        local = LocalModels(
            settings.ai_ollama_url,
            place=settings.ai_local_place,
            country=settings.ai_local_country,
            context=settings.ai_local_context,
            only=settings.ai_local_models,
        )
    return services, Catalogue(cards, local)


def build_ai_writer(settings: Settings, services: dict[str, Service]) -> AiWriter:
    return HttpAiWriter(
        services,
        ollama_url=settings.ai_ollama_url,
        user_agent=f"peerview.it-ai-review/1.0 (+{settings.origin})",
    )


def build_page_checker(settings: Settings) -> PageChecker:
    """Checks web pages before they go to reviewers (ADR 0022), remembering recent answers."""
    agent = f"peerview.it-page-check/1.0 (+{settings.origin})"
    return RecentChecks(HttpPageChecker(user_agent=agent))


def _version() -> str:
    try:
        return version("peerview")
    except PackageNotFoundError:
        return "dev"


def build_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host:
        if not settings.mail_from:
            raise RuntimeError("PEERVIEW_MAIL_FROM is required when PEERVIEW_SMTP_HOST is set")
        return SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.mail_from,
            settings.smtp_security,
        )
    if settings.https:
        raise RuntimeError("Set PEERVIEW_SMTP_HOST: verification emails need a mail server")
    return LogMailer()  # development: the link appears in the server log
