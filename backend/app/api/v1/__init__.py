from fastapi import APIRouter

from app.api.v1 import (
    admin_daily_challenge,
    admin_org_settings,
    admin_translations,
    analytics,
    announcements,
    assignments,
    audit,
    auth,
    blocks,
    calendar_ical,
    certificates,
    cohorts,
    courses,
    daily_challenge,
    daily_challenge_archive,
    grades,
    health,
    internal_daily_challenge_worker,
    internal_translation_worker,
    invitations,
    legal,
    notifications,
    prerequisites,
    progress,
    quizzes,
    reviews,
    rubrics,
    users,
    verse_of_the_day,
)
from app.api.v1 import calendar as calendar_mod

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(courses.router)
api_router.include_router(users.router)
api_router.include_router(health.router)
api_router.include_router(announcements.router)
api_router.include_router(grades.router)
api_router.include_router(analytics.router)
api_router.include_router(quizzes.router)
api_router.include_router(assignments.router)
api_router.include_router(certificates.router)
api_router.include_router(reviews.router)
api_router.include_router(rubrics.router)
api_router.include_router(prerequisites.router)
api_router.include_router(progress.router)
api_router.include_router(blocks.router)
api_router.include_router(cohorts.router)
api_router.include_router(notifications.router)
api_router.include_router(audit.router)
api_router.include_router(legal.router)
api_router.include_router(calendar_mod.router)
api_router.include_router(calendar_mod.event_router)
api_router.include_router(calendar_ical.router)
api_router.include_router(verse_of_the_day.router)
api_router.include_router(admin_org_settings.router)
api_router.include_router(admin_translations.router)
api_router.include_router(internal_translation_worker.router)
api_router.include_router(internal_daily_challenge_worker.router)
api_router.include_router(daily_challenge.router)
api_router.include_router(daily_challenge_archive.router)
api_router.include_router(admin_daily_challenge.router)
api_router.include_router(invitations.router)
