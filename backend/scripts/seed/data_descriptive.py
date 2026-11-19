"""Descriptive (manual-graded) question bank.

Twenty open-ended questions give the bank a non-objective component for
written communication and design reasoning. They are never auto-graded:
``correct_answer`` is ``None`` and the attempt is flagged for manual review.
The ``explanation`` field is used as model-answer guidance for the reviewer.

Difficulty split is 12 easy / 8 medium, which keeps the project-wide quota at
exactly 150 easy / 225 medium / 125 hard once every generator is combined.
"""
from __future__ import annotations

from typing import Any

Question = dict[str, Any]


def _q(text: str, category: str, skill: str, difficulty: str, guidance: str) -> Question:
    return {
        "text": text,
        "category": category,
        "skill": skill,
        "difficulty": difficulty,
        "explanation": guidance,
        "topic": "Written Response",
    }


DESCRIPTIVE: list[Question] = [
    # ---------------------------------------------------------------- easy (12)
    _q(
        "Explain the difference between a process and a thread. Give one scenario "
        "where using threads is clearly better than using separate processes.",
        "Operating Systems",
        "Operating Systems",
        "easy",
        "A process has its own address space; threads share one inside a process. "
        "Threads win for I/O-bound work that shares memory, e.g. handling many "
        "concurrent client connections in one server.",
    ),
    _q(
        "Describe what a primary key is and why a table should have one. Mention "
        "two properties a valid primary key must satisfy.",
        "DBMS & SQL",
        "DBMS",
        "easy",
        "Uniquely identifies each row; must be unique and non-null. It anchors "
        "foreign keys and prevents duplicate records.",
    ),
    _q(
        "What is the purpose of a foreign key? Explain what referential integrity "
        "means in one or two sentences.",
        "DBMS & SQL",
        "DBMS",
        "easy",
        "A foreign key references another table's primary key; referential "
        "integrity means the referenced row must exist (or the key is null), so "
        "orphan rows cannot be created.",
    ),
    _q(
        "Explain the difference between == and === in JavaScript, with a short "
        "example of a comparison that behaves differently.",
        "JavaScript & Web Development",
        "JavaScript",
        "easy",
        "== performs type coercion, === does not. For example 0 == '0' is true "
        "but 0 === '0' is false.",
    ),
    _q(
        "Describe the four pillars of object-oriented programming and give a "
        "one-line example of each.",
        "Object-Oriented Programming",
        "Object-Oriented Programming",
        "easy",
        "Encapsulation (private fields), inheritance (Dog extends Animal), "
        "polymorphism (draw() on different shapes), abstraction (an interface "
        "exposing only essential methods).",
    ),
    _q(
        "What is the difference between a list and a tuple in Python? When would "
        "you choose a tuple?",
        "Python Programming",
        "Python",
        "easy",
        "Lists are mutable, tuples are immutable. Use a tuple for fixed records, "
        "dictionary keys, or to signal that data must not change.",
    ),
    _q(
        "Explain what an index does in a database and name one cost of adding "
        "too many indexes to a table.",
        "DBMS & SQL",
        "Query Optimization",
        "easy",
        "An index speeds up lookups and range scans; every additional index "
        "slows down inserts, updates and deletes and consumes storage.",
    ),
    _q(
        "What is the difference between TCP and UDP? Name one application that "
        "prefers each and explain why.",
        "Computer Networks",
        "TCP/IP",
        "easy",
        "TCP is reliable and ordered (web, file transfer); UDP is connectionless "
        "and low-latency (live video, DNS), where retransmitting a late packet is "
        "less useful than sending the next one.",
    ),
    _q(
        "Explain what version control is and describe one benefit of using "
        "feature branches instead of committing directly to main.",
        "Software Engineering",
        "Version Control",
        "easy",
        "Version control records file history. Feature branches isolate "
        "unfinished work, keep main releasable, and make review and rollback "
        "safer.",
    ),
    _q(
        "What is a unit test? Explain why unit tests make refactoring safer.",
        "Software Engineering",
        "Unit Testing",
        "easy",
        "A unit test exercises one small piece of behaviour in isolation. Tests "
        "pin the expected behaviour, so a refactor that changes it fails loudly "
        "instead of silently breaking production.",
    ),
    _q(
        "Describe what a hash table is and what a collision is. Name one way to "
        "resolve collisions.",
        "Data Structures & Algorithms",
        "Data Structures",
        "easy",
        "A hash table maps keys to values through a hash function. A collision "
        "happens when two keys hash to the same slot; chaining (a list per "
        "bucket) or open addressing resolves it.",
    ),
    _q(
        "Explain the difference between supervised and unsupervised learning, "
        "giving one example task for each.",
        "Machine Learning & AI",
        "Machine Learning",
        "easy",
        "Supervised learning uses labelled data (spam classification); "
        "unsupervised learning finds structure without labels (customer "
        "clustering).",
    ),
    # -------------------------------------------------------------- medium (8)
    _q(
        "A query on a large orders table is slow. Describe the steps you would "
        "take to diagnose and improve it. Mention at least one tool or command.",
        "DBMS & SQL",
        "Query Optimization",
        "medium",
        "Read the execution plan (EXPLAIN), check for full scans, add or fix an "
        "index on the filter/join columns, avoid selecting unnecessary columns, "
        "and consider rewriting subqueries as joins. Verify with the plan again.",
    ),
    _q(
        "Explain how a deadlock can occur between two threads and describe one "
        "strategy to prevent it.",
        "Operating Systems",
        "Concurrency",
        "medium",
        "Two threads each hold one lock and wait for the other. Prevention: "
        "acquire locks in a globally consistent order, use timeouts, or use a "
        "single coarse lock where contention is low.",
    ),
    _q(
        "Describe how you would design a rate limiter for a public REST API. "
        "State the algorithm, where the counter lives, and what the API returns "
        "when the limit is exceeded.",
        "Software Engineering",
        "System Design",
        "medium",
        "Use a token-bucket or sliding-window counter keyed by user/IP in Redis "
        "so it works across instances. Reject excess requests with HTTP 429 and "
        "a Retry-After header.",
    ),
    _q(
        "Explain what SQL injection is and describe two defences a backend "
        "developer can apply.",
        "Cybersecurity",
        "Application Security",
        "medium",
        "Untrusted input changes the SQL grammar. Defences: parameterised "
        "queries/prepared statements, input validation, least-privilege database "
        "accounts, and an ORM that escapes values.",
    ),
    _q(
        "Describe how a container differs from a virtual machine. Give one "
        "practical consequence for deployment speed and one for isolation.",
        "Cloud & DevOps",
        "Docker",
        "medium",
        "Containers share the host kernel and package only the app and its "
        "dependencies, so they start in seconds; VMs run a full guest OS and "
        "give stronger isolation at the cost of size and boot time.",
    ),
    _q(
        "A model performs very well on training data but poorly on unseen data. "
        "Name the problem and describe three techniques that could address it.",
        "Machine Learning & AI",
        "Model Evaluation",
        "medium",
        "Overfitting. Use more data or augmentation, regularisation (L1/L2, "
        "dropout), simpler models, early stopping, and cross-validation to "
        "detect it.",
    ),
    _q(
        "Explain the difference between authentication and authorisation, and "
        "give one concrete example of each in a web application.",
        "Cybersecurity",
        "Identity Management",
        "medium",
        "Authentication proves identity (logging in with email and password); "
        "authorisation decides what that identity may do (a student cannot open "
        "the admin question bank).",
    ),
    _q(
        "Describe how you would test a function that depends on the current date. "
        "Explain why calling the real clock directly makes tests fragile.",
        "Software Engineering",
        "Unit Testing",
        "medium",
        "Inject a clock or freeze time (dependency injection / a fake clock) so "
        "the test controls 'now'. Real time makes results change with the "
        "calendar and can fail at midnight, month-end or in different time "
        "zones.",
    ),
]


def descriptive_questions() -> list[Question]:
    counts = {"easy": 0, "medium": 0, "hard": 0}
    for item in DESCRIPTIVE:
        counts[item["difficulty"]] += 1
    assert counts == {"easy": 12, "medium": 8, "hard": 0}, counts
    assert len({item["text"] for item in DESCRIPTIVE}) == len(DESCRIPTIVE)
    return DESCRIPTIVE
