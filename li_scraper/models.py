from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    stopped = "stopped"  # circuit breaker tripped (e.g. login/checkpoint detected)


class ScrapeRequest(BaseModel):
    profile_urls: list[str] = Field(..., description="List of LinkedIn profile URLs to scrape")
    min_wait_seconds: int = Field(15, ge=1, description="Min delay between profile requests")
    max_wait_seconds: int = Field(60, ge=1, description="Max delay between profile requests")


class Experience(BaseModel):
    title: Optional[str] = None
    company: Optional[str] = None
    duration: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None


class Education(BaseModel):
    school: Optional[str] = None
    degree: Optional[str] = None
    field: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Honor(BaseModel):
    title: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class Project(BaseModel):
    title: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Publication(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None


class Certification(BaseModel):
    title: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None


class Volunteer(BaseModel):
    role: Optional[str] = None
    organization: Optional[str] = None
    duration: Optional[str] = None
    description: Optional[str] = None


class Recommendation(BaseModel):
    recommender: Optional[str] = None
    relationship: Optional[str] = None
    text: Optional[str] = None


class SkillItem(BaseModel):
    name: str
    endorsements: Optional[str] = None
    positions: list[str] = []


class Patent(BaseModel):
    title: Optional[str] = None
    issuer: Optional[str] = None
    date: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None


class TrajectoryAnalysis(BaseModel):
    total_experience_years: Optional[float] = None
    average_tenure_years: Optional[float] = None
    role_count: int = 0
    flagged_gaps: list[str] = []
    flagged_title_inflation: list[str] = []
    general_flags: list[str] = []


class ProfileData(BaseModel):
    url: str
    name: Optional[str] = None
    headline: Optional[str] = None
    location: Optional[str] = None
    follower_count: Optional[str] = None
    connection_count: Optional[str] = None
    has_profile_picture: Optional[bool] = None
    about: Optional[str] = None
    experience: list[Experience] = []
    skills: list[str] = []
    skill_details: list[SkillItem] = []
    education: list[Education] = []
    honors: list[Honor] = []
    projects: list[Project] = []
    publications: list[Publication] = []
    certifications: list[Certification] = []
    patents: list[Patent] = []
    volunteer: list[Volunteer] = []
    recommendations: list[Recommendation] = []
    languages: list[str] = []
    trajectory_analysis: Optional[TrajectoryAnalysis] = None
    error: Optional[str] = None



class JobResponse(BaseModel):
    job_id: str
    status: JobStatus


class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    total_requested: int
    completed: int
    results: list[ProfileData] = []
    message: Optional[str] = None
