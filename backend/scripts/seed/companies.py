"""Seed companies and placement drives through the real ``DriveService``.

Fourteen fictional companies and eighteen drives give the TPO and student
interfaces a realistic, interconnected market. Every drive stores its JD as
``jd_text`` on the drive document (the model the application already uses) and
its required skills in the canonical taxonomy vocabulary.

Drives are created without an assessment; ``assessments.py`` generates the
standardized 20-question paper for each one and links it back.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.departments import normalize_departments
from app.core.skill_taxonomy import canonicalize_skills
from app.models.drive import DriveCreateRequest, EligibilityCriteria
from app.services.drive_service import DriveError, DriveService

from scripts.seed.context import SYNTHETIC

COMPANIES: list[dict] = [
    {
        "name": "Nexus Software Labs",
        "industry": "Product Engineering",
        "website": "https://nexuslabs.example.com",
        "description": (
            "A product engineering company building developer tooling and "
            "workflow platforms for mid-sized engineering teams."
        ),
    },
    {
        "name": "Quantiva Analytics",
        "industry": "Data & Analytics",
        "website": "https://quantiva.example.com",
        "description": (
            "An analytics consultancy that turns operational data into "
            "forecasting and decision-support products."
        ),
    },
    {
        "name": "CloudForge Systems",
        "industry": "Cloud Infrastructure",
        "website": "https://cloudforge.example.com",
        "description": (
            "A cloud platform team that designs, automates and operates "
            "multi-tenant infrastructure for Indian SaaS companies."
        ),
    },
    {
        "name": "FinEdge Technologies",
        "industry": "Financial Technology",
        "website": "https://finedge.example.com",
        "description": (
            "A fintech product house building lending and payments workflows "
            "with strict reliability and audit requirements."
        ),
    },
    {
        "name": "MedixAI",
        "industry": "Healthcare AI",
        "website": "https://medixai.example.com",
        "description": (
            "An applied-AI lab building clinical documentation and imaging "
            "assistants for hospital partners."
        ),
    },
    {
        "name": "AeroByte Robotics",
        "industry": "Robotics & Embedded",
        "website": "https://aerobyte.example.com",
        "description": (
            "A robotics startup shipping autonomous inspection drones and "
            "industrial sensor gateways."
        ),
    },
    {
        "name": "DataHarbor",
        "industry": "Data Platforms",
        "website": "https://dataharbor.example.com",
        "description": (
            "A data platform company operating ingestion, warehousing and "
            "governance pipelines for enterprise customers."
        ),
    },
    {
        "name": "SecureLayer",
        "industry": "Cybersecurity",
        "website": "https://securelayer.example.com",
        "description": (
            "A security services firm delivering application security "
            "reviews, penetration tests and incident response."
        ),
    },
    {
        "name": "PixelWorks Studio",
        "industry": "Design & Frontend",
        "website": "https://pixelworks.example.com",
        "description": (
            "A digital studio building accessible, high-performance web "
            "experiences for consumer brands."
        ),
    },
    {
        "name": "InfraGrid",
        "industry": "Industrial Software",
        "website": "https://infragrid.example.com",
        "description": (
            "An industrial software company connecting energy and utility "
            "assets through IoT telemetry."
        ),
    },
    {
        "name": "TalentBridge Consulting",
        "industry": "Business Consulting",
        "website": "https://talentbridge.example.com",
        "description": (
            "A placement and business consulting firm that helps enterprises "
            "measure and improve operational performance."
        ),
    },
    {
        "name": "GreenVolt Energy",
        "industry": "Renewable Energy",
        "website": "https://greenvolt.example.com",
        "description": (
            "A renewable-energy operator using forecasting and optimisation "
            "to balance solar and wind generation."
        ),
    },
    {
        "name": "Skyline Logistics",
        "industry": "Supply Chain Technology",
        "website": "https://skylinelogistics.example.com",
        "description": (
            "A logistics technology company routing fleets and optimising "
            "last-mile delivery across multiple cities."
        ),
    },
    {
        "name": "ByteCraft Games",
        "industry": "Interactive Entertainment",
        "website": "https://bytecraft.example.com",
        "description": (
            "An independent game studio building real-time multiplayer "
            "experiences for desktop and mobile."
        ),
    },
]

ALL_DEPARTMENTS = [
    "Computer Science",
    "Information Technology",
    "Electronics and Communication",
    "Electrical Engineering",
    "Mathematics and Computing",
    "Statistics",
]

SOFTWARE_DEPARTMENTS = [
    "Computer Science",
    "Information Technology",
    "Mathematics and Computing",
]

DRIVES: list[dict] = [
    {
        "company_name": "Nexus Software Labs",
        "job_title": "Software Development Engineer I",
        "description": "Build and ship features across the Nexus workflow platform.",
        "required_skills": ["Python", "JavaScript", "Data Structures", "Algorithms", "SQL", "Git"],
        "package": "14 LPA",
        "location": "Bengaluru",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "Technical Interview", "HR Interview"],
        "jd_text": (
            "Nexus Software Labs is hiring Software Development Engineer I.\n\n"
            "You will design, implement and test features across our workflow "
            "platform, working with senior engineers on Python services, "
            "JavaScript frontends and SQL-backed data models.\n\n"
            "Required skills: Python, JavaScript, data structures, algorithms, "
            "SQL and Git. Familiarity with REST APIs and automated testing is a "
            "plus.\n\n"
            "You should be able to reason about complexity, write clear code and "
            "debug production issues with guidance. The role includes an online "
            "assessment covering aptitude, technical knowledge and one coding "
            "problem."
        ),
    },
    {
        "company_name": "Nexus Software Labs",
        "job_title": "Backend Engineer - Python",
        "description": "Own Python services and APIs for the workflow platform.",
        "required_skills": ["Python", "FastAPI", "REST API", "SQL", "MongoDB", "Docker"],
        "package": "16 LPA",
        "location": "Bengaluru",
        "min_cgpa": 7.5,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "System Design Round", "HR Interview"],
        "jd_text": (
            "As a Backend Engineer on the platform team you will own Python "
            "services from schema design through deployment.\n\n"
            "The stack is FastAPI, PostgreSQL, MongoDB, Redis and Docker. You "
            "will write tested REST endpoints, review query plans, and improve "
            "latency and reliability.\n\n"
            "Required: strong Python, REST API design, SQL and database "
            "modelling, and comfort with containers. Experience with caching or "
            "message queues is welcome."
        ),
    },
    {
        "company_name": "Quantiva Analytics",
        "job_title": "Data Analyst",
        "description": "Turn operational data into dashboards and forecasts.",
        "required_skills": ["SQL", "Python", "Pandas", "Statistics", "Data Visualisation", "Excel"],
        "package": "10 LPA",
        "location": "Pune",
        "min_cgpa": 7.0,
        "departments": ["Mathematics and Computing", "Statistics", "Computer Science", "Information Technology"],
        "selection_process": ["Aptitude Test", "SQL & Analytics Case Study", "Interview"],
        "jd_text": (
            "Quantiva Analytics is looking for a Data Analyst to join its "
            "decision-support practice.\n\n"
            "You will write SQL against warehouse tables, clean and explore data "
            "in Python and Pandas, and build dashboards that non-technical "
            "stakeholders can act on. You should be comfortable with descriptive "
            "statistics and able to explain an insight clearly.\n\n"
            "Required skills: SQL, Python, Pandas, statistics, data "
            "visualisation and Excel."
        ),
    },
    {
        "company_name": "Quantiva Analytics",
        "job_title": "Machine Learning Engineer",
        "description": "Build and deploy forecasting models for clients.",
        "required_skills": ["Python", "Machine Learning", "Scikit-learn", "Pandas", "NumPy", "Model Evaluation"],
        "package": "18 LPA",
        "location": "Pune",
        "min_cgpa": 8.0,
        "departments": ["Computer Science", "Mathematics and Computing", "Statistics", "Information Technology"],
        "selection_process": ["Online Assessment", "ML Case Study", "Technical Interview", "HR Interview"],
        "jd_text": (
            "Join Quantiva's applied ML team to build demand and revenue "
            "forecasting models.\n\n"
            "You will engineer features from messy operational data, train and "
            "validate models with scikit-learn, and package reproducible "
            "pipelines. Strong Python, Pandas and NumPy are assumed, along with "
            "a solid understanding of cross-validation, leakage and model "
            "evaluation.\n\n"
            "Required: Python, machine learning, scikit-learn, Pandas, NumPy and "
            "model evaluation."
        ),
    },
    {
        "company_name": "CloudForge Systems",
        "job_title": "Cloud Engineer",
        "description": "Operate and automate multi-tenant cloud infrastructure.",
        "required_skills": ["AWS", "Linux", "Docker", "Kubernetes", "Terraform", "CI/CD"],
        "package": "15 LPA",
        "location": "Hyderabad",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "Infrastructure Interview", "HR Interview"],
        "jd_text": (
            "CloudForge is hiring Cloud Engineers to operate the infrastructure "
            "behind our SaaS customers.\n\n"
            "Day to day you will provision AWS resources with Terraform, run "
            "workloads on Kubernetes, harden Linux hosts and improve CI/CD "
            "pipelines. You should be able to debug networking, permissions and "
            "container issues methodically.\n\n"
            "Required: AWS, Linux, Docker, Kubernetes, Terraform and CI/CD."
        ),
    },
    {
        "company_name": "CloudForge Systems",
        "job_title": "DevOps Engineer",
        "description": "Automate build, release and observability pipelines.",
        "required_skills": ["CI/CD", "Docker", "Kubernetes", "Jenkins", "Git", "Monitoring"],
        "package": "14 LPA",
        "location": "Hyderabad",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "Pipeline Debugging Round", "HR Interview"],
        "jd_text": (
            "As a DevOps Engineer you will own the path from commit to "
            "production.\n\n"
            "You will maintain Jenkins pipelines, build container images, "
            "manage Kubernetes deployments and instrument services with "
            "monitoring and alerting. Git workflow discipline and incident "
            "troubleshooting are central to the role.\n\n"
            "Required: CI/CD, Docker, Kubernetes, Jenkins, Git and monitoring."
        ),
    },
    {
        "company_name": "FinEdge Technologies",
        "job_title": "Full Stack Developer",
        "description": "Build lending workflows across React and Node.js.",
        "required_skills": ["JavaScript", "React", "Node.js", "SQL", "REST API", "Git"],
        "package": "13 LPA",
        "location": "Mumbai",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "Pair Programming", "HR Interview"],
        "jd_text": (
            "FinEdge is hiring Full Stack Developers for its lending product.\n\n"
            "You will build React interfaces and Node.js APIs backed by a "
            "relational database, with an emphasis on correctness, auditability "
            "and clear error handling. You should understand HTTP, "
            "authentication and relational modelling.\n\n"
            "Required: JavaScript, React, Node.js, SQL, REST APIs and Git."
        ),
    },
    {
        "company_name": "FinEdge Technologies",
        "job_title": "Java Backend Developer",
        "description": "Develop resilient Java services for payments.",
        "required_skills": ["Java", "Spring Boot", "SQL", "REST API", "Microservices", "Docker"],
        "package": "15 LPA",
        "location": "Mumbai",
        "min_cgpa": 7.5,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "Technical Interview", "HR Interview"],
        "jd_text": (
            "Join the payments platform team to build Java services that move "
            "money safely.\n\n"
            "You will design Spring Boot services, model transactions in SQL, "
            "and expose idempotent REST endpoints. Experience with "
            "microservices, containers and careful error handling matters more "
            "than framework trivia.\n\n"
            "Required: Java, Spring Boot, SQL, REST APIs, microservices and "
            "Docker."
        ),
    },
    {
        "company_name": "MedixAI",
        "job_title": "AI Research Engineer",
        "description": "Prototype clinical NLP and vision models.",
        "required_skills": ["Python", "Deep Learning", "PyTorch", "Natural Language Processing", "Computer Vision", "Model Evaluation"],
        "package": "20 LPA",
        "location": "Bengaluru",
        "min_cgpa": 8.0,
        "departments": ["Computer Science", "Mathematics and Computing", "Statistics"],
        "selection_process": ["Online Assessment", "Research Discussion", "Technical Interview"],
        "jd_text": (
            "MedixAI is looking for an AI Research Engineer to prototype "
            "clinical documentation and imaging models.\n\n"
            "You will work with PyTorch, large text corpora and medical images, "
            "design careful evaluation protocols, and collaborate with clinical "
            "advisors. Strong Python, deep learning fundamentals and an "
            "understanding of NLP or computer vision are required.\n\n"
            "Required: Python, deep learning, PyTorch, NLP, computer vision and "
            "model evaluation."
        ),
    },
    {
        "company_name": "AeroByte Robotics",
        "job_title": "Embedded Software Engineer",
        "description": "Write firmware for autonomous inspection drones.",
        "required_skills": ["C", "C++", "Embedded Systems", "Linux", "Git", "Operating Systems"],
        "package": "12 LPA",
        "location": "Chennai",
        "min_cgpa": 7.0,
        "departments": ["Electronics and Communication", "Electrical Engineering", "Computer Science"],
        "selection_process": ["Online Assessment", "Firmware Interview", "HR Interview"],
        "jd_text": (
            "AeroByte Robotics is hiring Embedded Software Engineers for its "
            "autonomous inspection platforms.\n\n"
            "You will write C and C++ firmware for microcontrollers, integrate "
            "sensors over common buses, and debug timing and memory issues on "
            "Linux-based gateways. Comfort with low-level debugging and version "
            "control is essential.\n\n"
            "Required: C, C++, embedded systems, Linux, Git and operating-system "
            "fundamentals."
        ),
    },
    {
        "company_name": "DataHarbor",
        "job_title": "Data Engineer",
        "description": "Build ingestion and warehousing pipelines.",
        "required_skills": ["Python", "SQL", "Data Warehousing", "PostgreSQL", "Docker", "Linux"],
        "package": "16 LPA",
        "location": "Bengaluru",
        "min_cgpa": 7.5,
        "departments": SOFTWARE_DEPARTMENTS + ["Statistics"],
        "selection_process": ["Online Assessment", "Pipeline Design Round", "HR Interview"],
        "jd_text": (
            "DataHarbor is hiring Data Engineers to build reliable ingestion and "
            "warehouse pipelines.\n\n"
            "You will write Python extract-transform-load jobs, model warehouse "
            "tables in PostgreSQL, and operate jobs on Linux with Docker. You "
            "should care about idempotency, data quality checks and query "
            "performance.\n\n"
            "Required: Python, SQL, data warehousing/ETL, PostgreSQL, Docker and "
            "Linux."
        ),
    },
    {
        "company_name": "SecureLayer",
        "job_title": "Security Analyst",
        "description": "Review applications and investigate security alerts.",
        "required_skills": ["Application Security", "Network Security", "Linux", "Cryptography", "Vulnerability Assessment", "Python"],
        "package": "12 LPA",
        "location": "Gurugram",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS + ["Electronics and Communication"],
        "selection_process": ["Online Assessment", "Security Case Study", "HR Interview"],
        "jd_text": (
            "SecureLayer is hiring Security Analysts to support application "
            "security reviews and incident investigations.\n\n"
            "You will test web applications for common weaknesses, triage "
            "vulnerability reports, read logs on Linux and explain findings "
            "clearly to engineering teams. Scripting in Python is expected.\n\n"
            "Required: application security, network security, Linux, "
            "cryptography, vulnerability assessment and Python."
        ),
    },
    {
        "company_name": "PixelWorks Studio",
        "job_title": "Frontend Developer",
        "description": "Build accessible, high-performance web interfaces.",
        "required_skills": ["JavaScript", "React", "HTML", "CSS", "Tailwind CSS", "Web Accessibility"],
        "package": "11 LPA",
        "location": "Remote",
        "min_cgpa": 6.5,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Portfolio Review", "Frontend Assessment", "Interview"],
        "jd_text": (
            "PixelWorks is looking for a Frontend Developer who cares about "
            "craft and accessibility.\n\n"
            "You will build React interfaces with semantic HTML and modern CSS, "
            "work from design files, and keep pages fast and usable on low-end "
            "devices. Knowledge of responsive design and WCAG basics is "
            "important.\n\n"
            "Required: JavaScript, React, HTML, CSS, Tailwind CSS and web "
            "accessibility."
        ),
    },
    {
        "company_name": "InfraGrid",
        "job_title": "Software Engineer - IoT",
        "description": "Connect industrial assets through telemetry software.",
        "required_skills": ["C++", "Python", "Embedded Systems", "Linux", "Computer Networks", "SQL"],
        "package": "13 LPA",
        "location": "Ahmedabad",
        "min_cgpa": 7.0,
        "departments": ["Electronics and Communication", "Electrical Engineering", "Computer Science"],
        "selection_process": ["Online Assessment", "IoT Design Round", "HR Interview"],
        "jd_text": (
            "InfraGrid is hiring Software Engineers for its industrial IoT "
            "platform.\n\n"
            "You will write C++ device agents and Python services that collect, "
            "validate and forward telemetry from energy assets. You should "
            "understand networking, Linux and basic data modelling.\n\n"
            "Required: C++, Python, embedded systems, Linux, computer networks "
            "and SQL."
        ),
    },
    {
        "company_name": "TalentBridge Consulting",
        "job_title": "Business Analyst",
        "description": "Translate client operations into measurable improvements.",
        "required_skills": ["SQL", "Excel", "Business Analysis", "Communication", "Statistics", "Presentation"],
        "package": "9 LPA",
        "location": "Noida",
        "min_cgpa": 6.5,
        "departments": ALL_DEPARTMENTS,
        "selection_process": ["Aptitude Test", "Case Interview", "HR Interview"],
        "jd_text": (
            "TalentBridge Consulting is hiring Business Analysts for its "
            "operations practice.\n\n"
            "You will gather requirements, query data in SQL, build spreadsheet "
            "models and present recommendations to client stakeholders. Clear "
            "written and verbal communication is as important as analytical "
            "ability.\n\n"
            "Required: SQL, Excel, business analysis, communication, statistics "
            "and presentation."
        ),
    },
    {
        "company_name": "GreenVolt Energy",
        "job_title": "Data Scientist - Energy",
        "description": "Forecast generation and optimise storage dispatch.",
        "required_skills": ["Python", "Machine Learning", "Statistics", "Pandas", "NumPy", "Data Visualisation"],
        "package": "17 LPA",
        "location": "Bengaluru",
        "min_cgpa": 7.5,
        "departments": ["Mathematics and Computing", "Statistics", "Computer Science", "Electrical Engineering"],
        "selection_process": ["Online Assessment", "Forecasting Case Study", "Technical Interview"],
        "jd_text": (
            "GreenVolt Energy is hiring a Data Scientist to forecast renewable "
            "generation and optimise storage dispatch.\n\n"
            "You will work with time-series data, build and validate regression "
            "and ML models, and communicate uncertainty to operations teams. "
            "Python, Pandas, NumPy and statistics are core tools.\n\n"
            "Required: Python, machine learning, statistics, Pandas, NumPy and "
            "data visualisation."
        ),
    },
    {
        "company_name": "Skyline Logistics",
        "job_title": "Backend Engineer - Logistics",
        "description": "Build routing and tracking services for fleet operations.",
        "required_skills": ["Java", "Spring Boot", "PostgreSQL", "REST API", "System Design", "Docker"],
        "package": "15 LPA",
        "location": "Pune",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS,
        "selection_process": ["Online Assessment", "System Design Round", "HR Interview"],
        "jd_text": (
            "Skyline Logistics is hiring Backend Engineers for its routing and "
            "tracking platform.\n\n"
            "You will build Java and Spring Boot services over PostgreSQL, "
            "design APIs that mobile and web clients depend on, and reason about "
            "consistency and failure handling. Container deployment is standard.\n\n"
            "Required: Java, Spring Boot, PostgreSQL, REST APIs, system design "
            "and Docker."
        ),
    },
    {
        "company_name": "ByteCraft Games",
        "job_title": "Gameplay Programmer",
        "description": "Implement real-time multiplayer gameplay systems.",
        "required_skills": ["C++", "Algorithms", "Data Structures", "Concurrency", "Git", "Mathematics"],
        "package": "14 LPA",
        "location": "Bengaluru",
        "min_cgpa": 7.0,
        "departments": SOFTWARE_DEPARTMENTS + ["Electronics and Communication"],
        "selection_process": ["Online Assessment", "Gameplay Programming Round", "HR Interview"],
        "jd_text": (
            "ByteCraft Games is hiring a Gameplay Programmer for a real-time "
            "multiplayer title.\n\n"
            "You will implement gameplay systems in C++, profile frame time, and "
            "reason about concurrency and data layout. Strong algorithms and "
            "data-structure fundamentals matter more than engine-specific "
            "knowledge.\n\n"
            "Required: C++, algorithms, data structures, concurrency, Git and "
            "mathematics."
        ),
    },
]


def _deadline(days: int) -> datetime:
    return datetime.utcnow() + timedelta(days=days)


async def seed_companies_and_drives(
    db: AsyncIOMotorDatabase, tpo_user_id: str, log=print
) -> list[dict]:
    service = DriveService(db)
    drives: list[dict] = []

    for index, spec in enumerate(DRIVES):
        existing = await db.placement_drives.find_one(
            {"job_title": spec["job_title"]}, sort=[("created_at", -1)]
        )
        if existing:
            drives.append(existing)
            log(f"  REUSE  {spec['company_name']:<26} {spec['job_title']}")
            continue

        payload = DriveCreateRequest(
            company_name=spec["company_name"],
            company_description=next(
                c["description"] for c in COMPANIES if c["name"] == spec["company_name"]
            ),
            company_website=next(
                c["website"] for c in COMPANIES if c["name"] == spec["company_name"]
            ),
            company_industry=next(
                c["industry"] for c in COMPANIES if c["name"] == spec["company_name"]
            ),
            job_title=spec["job_title"],
            description=spec["description"],
            jd_text=spec["jd_text"],
            required_skills=canonicalize_skills(spec["required_skills"]),
            experience_required_years=0.0,
            package=spec["package"],
            location=spec["location"],
            eligibility=EligibilityCriteria(
                min_cgpa=spec["min_cgpa"],
                departments=normalize_departments(spec["departments"]),
                batch_years=[2026, 2027],
            ),
            deadline=_deadline(30 + index * 3),
            selection_process=spec["selection_process"],
        )
        try:
            drive = await service.create_drive(tpo_user_id, payload)
        except DriveError as exc:
            raise RuntimeError(
                f"Could not create drive {spec['job_title']!r}: {exc.message}"
            ) from exc

        await db.placement_drives.update_one(
            {"_id": ObjectId(drive.id)}, {"$set": {**SYNTHETIC, "seed_note": "seed/companies.py"}}
        )
        company = await db.companies.find_one({"_id": ObjectId(drive.company_id)})
        if company:
            await db.companies.update_one(
                {"_id": company["_id"]}, {"$set": {**SYNTHETIC, "seed_note": "seed/companies.py"}}
            )
        refreshed = await db.placement_drives.find_one({"_id": ObjectId(drive.id)})
        drives.append(refreshed)
        log(
            f"  CREATE {spec['company_name']:<26} {spec['job_title']:<34} "
            f"{len(payload.required_skills)} skills"
        )

    companies = await db.companies.count_documents({})
    log(f"\nCompanies: {companies}   Drives: {len(drives)}")
    return drives
