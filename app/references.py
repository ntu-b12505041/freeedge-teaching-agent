from __future__ import annotations


REFERENCE_SETS = {
    "physics": [
        "OpenStax Physics: https://openstax.org/details/books/physics",
        "College Board AP Physics: https://apstudents.collegeboard.org/courses/ap-physics-1",
    ],
    "biology": [
        "OpenStax Biology 2e: https://openstax.org/details/books/biology-2e",
        "College Board AP Biology: https://apstudents.collegeboard.org/courses/ap-biology",
    ],
    "computer_science": [
        "College Board AP Computer Science A: https://apstudents.collegeboard.org/courses/ap-computer-science-a",
        "Princeton Introduction to Programming: https://introcs.cs.princeton.edu/java/home/",
    ],
    "mathematics": [
        "OpenStax Algebra and Trigonometry 2e: https://openstax.org/details/books/algebra-and-trigonometry-2e",
        "OpenStax Precalculus 2e: https://openstax.org/details/books/precalculus-2e",
        "College Board AP Calculus AB: https://apstudents.collegeboard.org/courses/ap-calculus-ab",
    ],
}


def infer_domain(course_requirement: str) -> str:
    text = course_requirement.lower()
    if any(word in text for word in ["force", "motion", "energy", "wave", "electric", "magnet", "physics"]):
        return "physics"
    if any(word in text for word in ["cell", "gene", "dna", "evolution", "enzyme", "biology"]):
        return "biology"
    if any(word in text for word in ["algorithm", "code", "program", "computer", "recursion", "data structure"]):
        return "computer_science"
    return "mathematics"


def default_references(course_requirement: str) -> list[str]:
    domain = infer_domain(course_requirement)
    return REFERENCE_SETS[domain]
