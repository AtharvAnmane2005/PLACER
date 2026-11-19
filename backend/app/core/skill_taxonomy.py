"""Single source of truth for the placement skill vocabulary.

Three previously independent vocabularies existed in the project:

* ``app.ml.parsing.skill_normalizer`` — the 65-skill resume vocabulary,
* ``app.core.departments`` — academic departments (not skills), and
* ``ML_Keywords_and_Projects.txt`` — the user-supplied ML / web / data
  keyword reference.

This module merges them into one domain → skill → alias table. Everything
that writes or reads skill tags (resume parsing, drive requirements, question
tags, analytics) should normalise through :func:`normalize_skill` so the same
concept never appears twice under different spellings.

Design rules
------------
* A skill belongs to exactly one domain. Domains are presentation/grouping
  buckets, not a second identity — the canonical skill string is the key.
* Aliases are lowercase. They never overwrite a canonical name.
* Unknown free text is preserved (only whitespace-normalised) so real
  information is never destroyed; it simply has no domain.
* The module has no imports from the rest of the app, so it can be used by
  models, services, scripts and tests without creating import cycles.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Domain catalogue
# ---------------------------------------------------------------------------
# ``skills`` maps canonical skill -> list of aliases. Keep canonical names
# exactly as they should appear in the UI and in MongoDB.
DOMAINS: dict[str, dict] = {
    "Programming Languages": {
        "description": "General-purpose and domain-specific programming languages.",
        "skills": {
            "Python": ["py", "python3"],
            "Java": ["java8", "java 8", "core java"],
            "JavaScript": ["js", "ecmascript", "es6"],
            "TypeScript": ["ts"],
            "C": ["ansi c"],
            "C++": ["cpp", "c plus plus"],
            "C#": ["csharp", "c sharp", ".net c#"],
            "Go": ["golang"],
            "Rust": ["rustlang"],
            "PHP": ["php7", "php8"],
            "R": ["r language", "rlang"],
            "Dart": [],
            "Kotlin": [],
            "Swift": [],
            "Scala": [],
            "MATLAB": ["matlab programming"],
            "Bash": ["shell scripting", "shell script", "bash scripting"],
        },
    },
    "Data Structures & Algorithms": {
        "description": "Core computer-science problem solving and complexity.",
        "skills": {
            "Data Structures": ["dsa", "data structure"],
            "Algorithms": ["algo", "algorithm design"],
            "Dynamic Programming": ["dp"],
            "Graph Theory": ["graph algorithms"],
            "Recursion": ["recursive programming"],
            "Sorting": ["sort algorithms"],
            "Searching": ["search algorithms", "binary search"],
            "Complexity Analysis": ["big o", "time complexity", "space complexity"],
        },
    },
    "Databases & Data": {
        "description": "Relational and non-relational data stores, modelling and querying.",
        "skills": {
            "SQL": ["structured query language"],
            "DBMS": ["database management system", "database management"],
            "MongoDB": ["mongo"],
            "PostgreSQL": ["postgres", "psql"],
            "MySQL": ["my sql"],
            "Oracle": ["oracle db", "oracle database"],
            "SQLite": ["sqlite3"],
            "Redis": ["redis cache"],
            "Firebase": ["firestore"],
            "Database Design": ["schema design", "normalization", "normalisation"],
            "Data Warehousing": ["data warehouse", "etl"],
            "Query Optimization": ["query tuning", "indexing"],
        },
    },
    "Web & Frontend": {
        "description": "Browser, UI and client-side application engineering.",
        "skills": {
            "HTML": ["html5"],
            "CSS": ["css3"],
            "Tailwind CSS": ["tailwind"],
            "Bootstrap": [],
            "React": ["reactjs", "react.js"],
            "Next.js": ["nextjs", "next js"],
            "Angular": ["angularjs", "angular.js"],
            "Vue": ["vuejs", "vue.js"],
            "Redux": ["redux toolkit"],
            "Responsive Design": ["mobile first", "responsive ui"],
            "Web Accessibility": ["a11y", "wcag"],
        },
    },
    "Backend & APIs": {
        "description": "Server-side application frameworks, protocols and integration.",
        "skills": {
            "Node.js": ["node", "nodejs"],
            "Express": ["expressjs", "express.js"],
            "Django": ["django rest framework", "drf"],
            "Flask": [],
            "FastAPI": ["fast api"],
            "Spring Boot": ["spring", "springboot"],
            "REST API": ["rest", "restful api", "rest apis"],
            "GraphQL": [],
            "Microservices": ["microservice architecture"],
            "WebSockets": ["websocket"],
            "Authentication": ["oauth", "jwt", "auth"],
            "Caching": ["cache", "redis caching"],
            "Message Queues": ["kafka", "rabbitmq", "pub sub"],
        },
    },
    "Mobile Development": {
        "description": "Native and cross-platform mobile application development.",
        "skills": {
            "Android": ["android development"],
            "Flutter": ["flutter dart"],
            "React Native": ["reactnative"],
            "iOS": ["ios development"],
            "Mobile UI": ["mobile ux"],
        },
    },
    "Cloud & DevOps": {
        "description": "Infrastructure, deployment, automation and operations.",
        "skills": {
            "AWS": ["amazon web services", "ec2", "s3", "lambda"],
            "Azure": ["microsoft azure"],
            "GCP": ["google cloud", "google cloud platform"],
            "Docker": ["containerization", "containerisation"],
            "Kubernetes": ["k8s"],
            "CI/CD": ["cicd", "continuous integration", "continuous delivery"],
            "Linux": ["unix", "ubuntu", "bash linux"],
            "Git": ["github", "gitlab", "version control"],
            "Terraform": ["infrastructure as code", "iac"],
            "Jenkins": ["jenkins pipeline"],
            "Nginx": ["reverse proxy"],
            "Monitoring": ["prometheus", "grafana", "observability"],
            "Cloud Security": ["cloud security posture"],
        },
    },
    "Cybersecurity": {
        "description": "Application, network and systems security.",
        "skills": {
            "Network Security": ["firewall", "ids", "ips"],
            "Application Security": ["appsec", "owasp", "secure coding"],
            "Penetration Testing": ["pentesting", "ethical hacking", "pen test"],
            "Cryptography": ["encryption", "hashing", "tls"],
            "Vulnerability Assessment": ["vulnerability scanning", "cve"],
            "Incident Response": ["soc", "forensics"],
            "Identity Management": ["iam", "sso", "oauth security"],
        },
    },
    "Operating Systems & Networks": {
        "description": "Systems programming, OS internals and networking fundamentals.",
        "skills": {
            "Operating Systems": ["os", "operating system"],
            "Computer Networks": ["cn", "networking", "computer network"],
            "TCP/IP": ["tcp ip", "tcpip"],
            "Concurrency": ["multithreading", "threads", "parallelism"],
            "Memory Management": ["virtual memory", "paging"],
            "System Design": ["distributed systems", "scalability"],
            "Embedded Systems": ["embedded c", "microcontrollers", "firmware"],
        },
    },
    "Machine Learning & AI": {
        "description": "Data science, machine learning, deep learning and NLP.",
        "skills": {
            "Machine Learning": ["ml", "machine-learning"],
            "Deep Learning": ["dl", "deep-learning"],
            "Artificial Intelligence": ["ai"],
            "Supervised Learning": ["classification", "regression"],
            "Unsupervised Learning": ["clustering", "dimensionality reduction"],
            "Reinforcement Learning": ["rl"],
            "Transfer Learning": ["fine tuning", "fine-tuning"],
            "Natural Language Processing": ["nlp", "text mining"],
            "Computer Vision": ["cv", "opencv", "image processing"],
            "TensorFlow": ["tf", "keras"],
            "PyTorch": ["torch"],
            "Scikit-learn": ["sklearn", "scikit learn"],
            "Pandas": ["python pandas"],
            "NumPy": ["numpy"],
            "Data Visualisation": ["data visualization", "matplotlib", "seaborn", "power bi", "tableau"],
            "Statistics": ["statistical analysis", "probability"],
            "Feature Engineering": ["feature selection"],
            "Model Evaluation": ["cross validation", "model metrics"],
            "MLOps": ["model deployment", "ml pipeline"],
        },
    },
    "Software Engineering": {
        "description": "Design, testing, process and delivery practices.",
        "skills": {
            "Object-Oriented Programming": ["oop", "oops", "object oriented"],
            "Software Engineering": ["sdlc", "software development lifecycle"],
            "Agile": ["scrum", "kanban"],
            "Jira": ["atlassian jira"],
            "Unit Testing": ["pytest", "jest", "junit"],
            "Test Automation": ["selenium", "cypress", "automation testing"],
            "Design Patterns": ["gof patterns", "software design patterns"],
            "Code Review": ["peer review"],
            "Debugging": ["troubleshooting"],
            "Documentation": ["technical writing"],
            "Version Control": ["git workflow", "branching strategy"],
        },
    },
    "Professional & Business": {
        "description": "Communication, collaboration and placement-readiness skills.",
        "skills": {
            "Communication": ["verbal communication", "written communication"],
            "Problem Solving": ["analytical thinking"],
            "Teamwork": ["collaboration", "team player"],
            "Leadership": ["team lead"],
            "Presentation": ["public speaking"],
            "Time Management": ["prioritisation", "prioritization"],
            "Critical Thinking": ["reasoning"],
            "Business Analysis": ["requirements gathering", "stakeholder management"],
            "Product Management": ["roadmapping"],
            "Excel": ["ms excel", "spreadsheets"],
            "Accounting": ["finance fundamentals"],
            "Marketing": ["digital marketing"],
        },
    },
}

# Question-bank category -> taxonomy domain. Used by the seeder and by
# analytics that need to roll question performance up to a domain.
CATEGORY_DOMAIN: dict[str, str] = {
    "Data Structures & Algorithms": "Data Structures & Algorithms",
    "DBMS & SQL": "Databases & Data",
    "Operating Systems": "Operating Systems & Networks",
    "Computer Networks": "Operating Systems & Networks",
    "Object-Oriented Programming": "Software Engineering",
    "Python Programming": "Programming Languages",
    "JavaScript & Web Development": "Web & Frontend",
    "Aptitude & Logical Reasoning": "Professional & Business",
    "Machine Learning & AI": "Machine Learning & AI",
    "Cybersecurity": "Cybersecurity",
    "Cloud & DevOps": "Cloud & DevOps",
    "Software Engineering": "Software Engineering",
    "Verbal Ability": "Professional & Business",
}

# ---------------------------------------------------------------------------
# Derived lookup tables
# ---------------------------------------------------------------------------
_CANONICAL_ORDER: list[str] = []
_SKILL_TO_DOMAIN: dict[str, str] = {}
_ALIAS_TO_SKILL: dict[str, str] = {}

for _domain, _config in DOMAINS.items():
    for _skill, _aliases in _config["skills"].items():
        if _skill in _SKILL_TO_DOMAIN:
            raise RuntimeError(f"Duplicate canonical skill in taxonomy: {_skill}")
        _CANONICAL_ORDER.append(_skill)
        _SKILL_TO_DOMAIN[_skill] = _domain
        _ALIAS_TO_SKILL[_skill.lower()] = _skill
        for _alias in _aliases:
            _key = _alias.strip().lower()
            if not _key:
                continue
            existing = _ALIAS_TO_SKILL.get(_key)
            if existing and existing != _skill:
                raise RuntimeError(
                    f"Alias {_alias!r} maps to both {existing!r} and {_skill!r}"
                )
            _ALIAS_TO_SKILL[_key] = _skill

CANONICAL_SKILLS: tuple[str, ...] = tuple(_CANONICAL_ORDER)
SKILL_DOMAINS: tuple[str, ...] = tuple(DOMAINS)

# Alias -> canonical map for callers that need the raw table. Canonical names
# themselves are excluded (normalize_skill already resolves them by lower-case
# identity), so every key here is a genuine synonym.
ALIASES: dict[str, str] = {
    alias: skill
    for alias, skill in _ALIAS_TO_SKILL.items()
    if alias != skill.lower()
}


def _clean(raw: str) -> str:
    return re.sub(r"\s+", " ", str(raw or "").strip())


def normalize_skill(raw: str) -> str:
    """Return the canonical skill for ``raw``, preserving unknown free text."""
    cleaned = _clean(raw)
    if not cleaned:
        return ""
    return _ALIAS_TO_SKILL.get(cleaned.lower(), cleaned)


def canonicalize_skills(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """Normalise, de-duplicate and order a list of skill strings."""
    if not values:
        return []
    seen: set[str] = set()
    unknown: list[str] = []
    for value in values:
        skill = normalize_skill(value)
        if not skill or skill in seen:
            continue
        seen.add(skill)
        if skill not in _SKILL_TO_DOMAIN:
            unknown.append(skill)
    known = [s for s in CANONICAL_SKILLS if s in seen]
    return known + sorted(unknown, key=str.lower)


def domain_for_skill(skill: str) -> str | None:
    return _SKILL_TO_DOMAIN.get(normalize_skill(skill))


def skills_in_domain(domain: str) -> list[str]:
    config = DOMAINS.get(domain)
    if not config:
        return []
    return list(config["skills"].keys())


def domain_for_category(category_name: str) -> str | None:
    return CATEGORY_DOMAIN.get(category_name)


def aliases_for(skill: str) -> list[str]:
    canonical = normalize_skill(skill)
    config = DOMAINS.get(_SKILL_TO_DOMAIN.get(canonical, ""), {})
    return list(config.get("skills", {}).get(canonical, []))


def _build_pattern() -> re.Pattern:
    terms = set(_ALIAS_TO_SKILL)
    terms.update(s.lower() for s in CANONICAL_SKILLS)
    # Longest first so "react native" wins over "react".
    escaped = sorted((re.escape(t) for t in terms), key=len, reverse=True)
    return re.compile(
        rf"(?<![A-Za-z0-9])({'|'.join(escaped)})(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


SKILL_PATTERN = _build_pattern()


def extract_skills(text: str) -> list[str]:
    """Scan free text (a resume, JD or project description) for known skills."""
    if not text:
        return []
    return canonicalize_skills(SKILL_PATTERN.findall(text))


def taxonomy_snapshot() -> dict:
    """Serialisable summary for docs, tests and admin tooling."""
    return {
        "domains": [
            {
                "name": domain,
                "description": config["description"],
                "skills": list(config["skills"].keys()),
            }
            for domain, config in DOMAINS.items()
        ],
        "total_domains": len(DOMAINS),
        "total_skills": len(CANONICAL_SKILLS),
    }
