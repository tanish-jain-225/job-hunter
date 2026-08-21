"""Flask Blueprints for Job Hunter Web Dashboard and REST API."""
from .views import views_bp
from .jobs import jobs_bp
from .profile import profile_bp
from .pipeline import pipeline_bp

__all__ = ["views_bp", "jobs_bp", "profile_bp", "pipeline_bp"]
