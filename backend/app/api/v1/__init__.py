from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    announcements,
    assignments,
    audit,
    auth,
    blocks,
    certificates,
    cohorts,
    courses,
    grades,
    health,
    notifications,
    prerequisites,
    progress,
    quizzes,
    reviews,
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
api_router.include_router(prerequisites.router)
api_router.include_router(progress.router)
api_router.include_router(blocks.router)
api_router.include_router(cohorts.router)
api_router.include_router(notifications.router)
api_router.include_router(audit.router)
api_router.include_router(calendar_mod.router)
api_router.include_router(calendar_mod.event_router)
api_router.include_router(verse_of_the_day.router)
