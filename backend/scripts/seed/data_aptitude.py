"""Deterministic aptitude, logical-reasoning and verbal question bank.

Every question is generated from a small, hand-checked template rather than
scraped, so the answer key is always correct and the text is unique. The
templates are parameterised: changing a variant's numbers produces a genuinely
different question, not a reworded duplicate.

Difficulty is assigned per section to hit the project-wide quota exactly
(34 easy / 57 medium / 29 hard across the 120 questions). The item order is
roughly increasing in complexity, so the easy/medium/hard labels stay
believable.
"""
from __future__ import annotations

from typing import Any

Question = dict[str, Any]


def _q(
    text: str,
    options: list[str],
    answer: str,
    explanation: str,
    topic: str,
    skill: str,
) -> Question:
    # Defensive: a typo in an option list must never reach the database.
    if answer not in options:
        raise ValueError(f"Answer {answer!r} is not among options for: {text}")
    if len({option.strip().lower() for option in options}) != len(options):
        raise ValueError(f"Duplicate options for: {text}")
    return {
        "text": text,
        "options": options,
        "answer": answer,
        "explanation": explanation,
        "topic": topic,
        "skill": skill,
    }


def _assign_difficulty(items: list[Question], easy: int, medium: int, hard: int) -> list[Question]:
    if easy + medium + hard != len(items):
        raise ValueError(f"Difficulty quota {easy}/{medium}/{hard} does not cover {len(items)} items")
    for index, item in enumerate(items):
        if index < easy:
            item["difficulty"] = "easy"
        elif index < easy + medium:
            item["difficulty"] = "medium"
        else:
            item["difficulty"] = "hard"
    return items


# ---------------------------------------------------------------------------
# Quantitative aptitude — 40 questions
# ---------------------------------------------------------------------------
def quantitative() -> list[Question]:
    items: list[Question] = []

    # 1. Successive percentage change.
    for x in (10, 20, 25, 40):
        value = x * x / 100
        text = (
            f"A number is first increased by {x}% and then decreased by {x}%. "
            "What is the net percentage change?"
        )
        answer = f"{value:g}% decrease"
        items.append(
            _q(
                text,
                [answer, f"{value:g}% increase", "No change", f"{2 * x}% decrease"],
                answer,
                f"Net change = -x^2/100 = -{x * x}/100 = -{value:g}%.",
                "Percentage",
                "Problem Solving",
            )
        )

    # 2. Profit and loss percentage.
    for cost, selling in ((200, 250), (500, 450), (800, 920), (1200, 1020)):
        change = abs(selling - cost) / cost * 100
        kind = "profit" if selling > cost else "loss"
        opposite = "loss" if kind == "profit" else "profit"
        answer = f"{change:g}% {kind}"
        items.append(
            _q(
                f"An item bought for Rs. {cost} is sold for Rs. {selling}. "
                "What is the profit or loss percentage?",
                [
                    answer,
                    f"{change:g}% {opposite}",
                    f"{change / 2:g}% {kind}",
                    f"{change * 2:g}% {kind}",
                ],
                answer,
                f"Percentage = |{selling} - {cost}| / {cost} x 100 = {change:g}% {kind}.",
                "Profit and Loss",
                "Problem Solving",
            )
        )

    # 3. Average after replacing one value.
    for count, average, old, new in ((5, 20, 30, 50), (8, 15, 10, 26), (10, 25, 40, 20), (6, 18, 12, 30)):
        new_average = average + (new - old) / count
        answer = f"{new_average:g}"
        items.append(
            _q(
                f"The average of {count} numbers is {average}. If the number {old} is "
                f"replaced by {new}, what is the new average?",
                [answer, f"{average:g}", f"{new_average + 1:g}", f"{new_average - 1:g}"],
                answer,
                f"Change in total = {new} - {old} = {new - old}; new average = "
                f"{average} + ({new - old})/{count} = {new_average:g}.",
                "Averages",
                "Problem Solving",
            )
        )

    # 4. Speed, distance and time.
    for distance, hours in ((90, 1.5), (200, 2.5), (315, 4.5), (275, 5)):
        speed = distance / hours
        answer = f"{speed:g} km/h"
        items.append(
            _q(
                f"A vehicle covers {distance} km in {hours} hours. What is its average speed?",
                [answer, f"{speed + 10:g} km/h", f"{speed / 2:g} km/h", f"{speed * 2:g} km/h"],
                answer,
                f"Speed = distance / time = {distance} / {hours} = {speed:g} km/h.",
                "Speed and Distance",
                "Problem Solving",
            )
        )

    # 5. Time and work.
    for a, b in ((6, 12), (10, 15), (12, 18), (8, 24)):
        together = a * b / (a + b)
        answer = f"{together:g} days"
        items.append(
            _q(
                f"Worker A can finish a job in {a} days and worker B in {b} days. "
                "Working together, how long will they take?",
                [answer, f"{a + b:g} days", f"{abs(a - b):g} days", f"{together + 1:g} days"],
                answer,
                f"Combined rate = 1/{a} + 1/{b}; time = {a}x{b}/({a}+{b}) = {together:g} days.",
                "Time and Work",
                "Problem Solving",
            )
        )

    # 6. Simple interest.
    for principal, rate, years in ((5000, 8, 3), (8000, 5, 4), (12000, 6, 2.5), (15000, 7, 3)):
        interest = principal * rate * years / 100
        answer = f"Rs. {interest:g}"
        items.append(
            _q(
                f"Find the simple interest on Rs. {principal} at {rate}% per annum for {years} years.",
                [answer, f"Rs. {interest / 2:g}", f"Rs. {interest * 2:g}", f"Rs. {principal:g}"],
                answer,
                f"SI = P x R x T / 100 = {principal} x {rate} x {years} / 100 = Rs. {interest:g}.",
                "Simple Interest",
                "Problem Solving",
            )
        )

    # 7. Compound interest.
    for principal, rate in ((10000, 10), (8000, 5), (12000, 20), (5000, 8)):
        interest = principal * ((1 + rate / 100) ** 2 - 1)
        answer = f"Rs. {interest:.2f}"
        items.append(
            _q(
                f"Find the compound interest on Rs. {principal} at {rate}% per annum "
                "compounded annually for 2 years.",
                [
                    answer,
                    f"Rs. {principal * rate * 2 / 100:.2f}",
                    f"Rs. {interest / 2:.2f}",
                    f"Rs. {interest * 2:.2f}",
                ],
                answer,
                f"CI = P[(1 + R/100)^2 - 1] = {principal} x [{(1 + rate / 100) ** 2:.4f} - 1] = Rs. {interest:.2f}.",
                "Compound Interest",
                "Problem Solving",
            )
        )

    # 8. Ratio division.
    for amount, a, b in ((1200, 3, 5), (2400, 5, 7), (3600, 4, 5), (5600, 3, 4)):
        share = amount * a / (a + b)
        answer = f"Rs. {share:g}"
        items.append(
            _q(
                f"Rs. {amount} is divided between A and B in the ratio {a}:{b}. "
                "How much does A receive?",
                [answer, f"Rs. {amount * b / (a + b):g}", f"Rs. {amount / 2:g}", f"Rs. {share + 100:g}"],
                answer,
                f"A's share = {amount} x {a}/({a}+{b}) = Rs. {share:g}.",
                "Ratio and Proportion",
                "Problem Solving",
            )
        )

    # 9. Ages.
    for multiple, later_multiple, years in ((4, 3, 6), (5, 3, 10), (4, 2, 10), (5, 4, 12)):
        son = years * (later_multiple - 1) / (multiple - later_multiple)
        answer = f"{son:g} years"
        # Distractors are filtered for uniqueness: some parameter sets make a
        # naive "son + 5" coincide with "son * 2" (e.g. son = 5).
        options: list[str] = []
        for value in (son, son + 2, son + 3, son * 2 + 1):
            label = f"{value:g} years"
            if label not in options:
                options.append(label)
        items.append(
            _q(
                f"A father is {multiple} times as old as his son. After {years} years he "
                f"will be {later_multiple} times as old. What is the son's present age?",
                options,
                answer,
                f"Let son = s. {multiple}s + {years} = {later_multiple}(s + {years}); "
                f"s = {years}({later_multiple}-1)/({multiple}-{later_multiple}) = {son:g}.",
                "Ages",
                "Problem Solving",
            )
        )

    # 10. Probability.
    probability_items = [
        (
            "A fair die is rolled once. What is the probability of getting an even number?",
            ["1/2", "1/3", "1/6", "2/3"],
            "1/2",
            "There are three even faces (2, 4, 6) out of six, so 3/6 = 1/2.",
        ),
        (
            "A fair die is rolled once. What is the probability of getting a number greater than 4?",
            ["1/3", "1/2", "1/6", "2/3"],
            "1/3",
            "Only 5 and 6 qualify, so 2/6 = 1/3.",
        ),
        (
            "A card is drawn from a standard deck of 52 cards. What is the probability that it is a king?",
            ["1/13", "1/4", "1/26", "4/13"],
            "1/13",
            "There are four kings, so 4/52 = 1/13.",
        ),
        (
            "A card is drawn from a standard deck of 52 cards. What is the probability that it is a face card?",
            ["3/13", "1/13", "1/4", "1/2"],
            "3/13",
            "There are 12 face cards (J, Q, K in four suits), so 12/52 = 3/13.",
        ),
    ]
    for text, options, answer, explanation in probability_items:
        items.append(_q(text, options, answer, explanation, "Probability", "Problem Solving"))

    return _assign_difficulty(items, easy=12, medium=19, hard=9)


# ---------------------------------------------------------------------------
# Logical reasoning — 40 questions
# ---------------------------------------------------------------------------
def logical() -> list[Question]:
    items: list[Question] = []

    # 1. Number series.
    for text, answer, explanation in (
        ("Find the next number: 2, 6, 12, 20, 30, ?", "42", "Differences are 4, 6, 8, 10, 12, so 30 + 12 = 42."),
        ("Find the next number: 3, 6, 11, 18, 27, ?", "38", "Differences are 3, 5, 7, 9, 11, so 27 + 11 = 38."),
        ("Find the next number: 1, 4, 9, 16, 25, ?", "36", "These are perfect squares; the next is 6^2 = 36."),
        ("Find the next number: 5, 10, 20, 40, 80, ?", "160", "Each term doubles, so 80 x 2 = 160."),
    ):
        distractors = [str(int(answer) + delta) for delta in (2, 4, -2)]
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Number Series", "Critical Thinking")
        )

    # 2. Alphabet series.
    for text, answer, explanation in (
        ("Find the next letter: A, C, F, J, O, ?", "U", "The gaps are +2, +3, +4, +5, +6; O + 6 = U."),
        ("Find the next letter: B, D, G, K, P, ?", "V", "The gaps are +2, +3, +4, +5, +6; P + 6 = V."),
        ("Find the next letter: Z, X, V, T, ?", "R", "The series moves back two letters each time."),
        ("Find the next letter: A, Z, B, Y, C, ?", "X", "The series alternates forward from the start and backward from the end."),
    ):
        others = [chr(ord(answer) + offset) for offset in (1, 2, -1)]
        items.append(
            _q(text, [answer, *others], answer, explanation, "Alphabet Series", "Critical Thinking")
        )

    # 3. Coding-decoding.
    for text, answer, explanation, distractors in (
        (
            "If CAT is coded as DBU, how is DOG coded?",
            "EPH",
            "Each letter moves one place forward: D->E, O->P, G->H.",
            ["EPG", "FQI", "CNF"],
        ),
        (
            "If PEN is coded as RGP, how is BOOK coded?",
            "DQQM",
            "Each letter moves two places forward: B->D, O->Q, O->Q, K->M.",
            ["DQQN", "CMPL", "EQRN"],
        ),
        (
            "If SUN is coded as RTM, how is MOON coded?",
            "LNNM",
            "Each letter moves one place backward: M->L, O->N, O->N, N->M.",
            ["LNNN", "NPPM", "NPPO"],
        ),
        (
            "If ACE is coded as DFH, how is BAD coded?",
            "EDG",
            "Each letter moves three places forward: B->E, A->D, D->G.",
            ["EDF", "DCF", "FEG"],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Coding-Decoding", "Critical Thinking")
        )

    # 4. Blood relations.
    for text, answer, explanation, distractors in (
        (
            "Pointing to a man, a woman said, 'He is the son of my mother's only daughter.' "
            "How is the man related to the woman?",
            "Son",
            "The woman's mother's only daughter is the woman herself, so the man is her son.",
            ["Brother", "Nephew", "Cousin"],
        ),
        (
            "A is B's father. B is C's sister. How is A related to C?",
            "Father",
            "If B is C's sister, they share parents, so B's father A is also C's father.",
            ["Brother", "Uncle", "Grandfather"],
        ),
        (
            "P is the brother of Q. Q is the daughter of R. How is P related to R?",
            "Son",
            "Q is R's daughter and P is Q's brother, so P is R's son.",
            ["Brother", "Father", "Nephew"],
        ),
        (
            "X is the mother of Y. Y is the husband of Z. How is X related to Z?",
            "Mother-in-law",
            "Y is Z's husband, so Y's mother X is Z's mother-in-law.",
            ["Mother", "Sister-in-law", "Aunt"],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Blood Relations", "Critical Thinking")
        )

    # 5. Direction sense.
    for text, answer, explanation, distractors in (
        (
            "A man walks 5 km north, turns right and walks 3 km, then turns right and walks 5 km. "
            "How far is he from the starting point?",
            "3 km",
            "The two 5 km legs are opposite, so only the 3 km eastward leg remains.",
            ["5 km", "8 km", "13 km"],
        ),
        (
            "A person walks 4 km east, then turns left and walks 3 km. How far is he from the start?",
            "5 km",
            "The path forms a 3-4-5 right triangle, so the straight-line distance is 5 km.",
            ["7 km", "4 km", "3 km"],
        ),
        (
            "She walks 2 km south, turns left and walks 2 km, then turns left and walks 2 km. "
            "Where is she relative to the start?",
            "2 km east",
            "The two southward legs cancel, leaving a 2 km eastward displacement.",
            ["2 km west", "2 km south", "At the start"],
        ),
        (
            "A walks 6 km west, then turns right and walks 8 km. How far is he from the start?",
            "10 km",
            "The legs are perpendicular, so distance = sqrt(6^2 + 8^2) = 10 km.",
            ["14 km", "2 km", "12 km"],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Direction Sense", "Critical Thinking")
        )

    # 6. Syllogism.
    for text, answer, explanation, distractors in (
        (
            "All roses are flowers. Some flowers fade quickly. Which conclusion definitely follows?",
            "No conclusion about roses follows",
            "The flowers that fade quickly need not include any rose, so nothing about roses is certain.",
            ["All roses fade quickly", "Some roses fade quickly", "Some flowers are roses"],
        ),
        (
            "All engineers are graduates. All graduates are educated. Which conclusion definitely follows?",
            "All engineers are educated",
            "The two universal statements chain: engineer -> graduate -> educated.",
            ["Some engineers are not educated", "All educated people are engineers", "No engineers are graduates"],
        ),
        (
            "Some birds can fly. All penguins are birds. Which conclusion definitely follows?",
            "No definite conclusion about penguins flying",
            "The birds that can fly are not guaranteed to include penguins.",
            ["All penguins can fly", "No penguin can fly", "Some penguins can fly"],
        ),
        (
            "No reptiles are mammals. All snakes are reptiles. Which conclusion definitely follows?",
            "No snakes are mammals",
            "Snakes fall entirely inside reptiles, which are disjoint from mammals.",
            ["Some snakes are mammals", "All mammals are snakes", "Some reptiles are mammals"],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Syllogism", "Critical Thinking")
        )

    # 7. Odd one out.
    for text, answer, explanation, distractors in (
        ("Which number is the odd one out: 2, 3, 5, 7, 9?", "9", "9 is composite; the others are prime.", ["2", "5", "7"]),
        ("Which number is the odd one out: 4, 9, 16, 25, 30?", "30", "30 is not a perfect square; the others are 2^2 to 5^2.", ["4", "16", "25"]),
        ("Which item is the odd one out: Apple, Banana, Carrot, Mango?", "Carrot", "Carrot is a vegetable; the others are fruits.", ["Apple", "Banana", "Mango"]),
        ("Which shape is the odd one out: Circle, Square, Triangle, Cube?", "Cube", "Cube is three-dimensional; the others are plane figures.", ["Circle", "Square", "Triangle"]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Odd One Out", "Critical Thinking")
        )

    # 8. Seating arrangement.
    for text, answer, explanation, distractors in (
        (
            "P, Q, R, S and T sit in a row facing north. R is at the extreme left, T at the "
            "extreme right, Q is exactly in the middle and P is immediately to the right of R. "
            "Who is second from the right?",
            "S",
            "The row is R P Q S T, so S is second from the right.",
            ["Q", "T", "P"],
        ),
        (
            "A, B, C, D and E sit in a row. A is at the left end, E at the right end, C is "
            "exactly in the middle and B is immediately to the right of A. Who is second from the left?",
            "B",
            "The row is A B C D E, so B is second from the left.",
            ["C", "D", "A"],
        ),
        (
            "Six people P, Q, R, S, T and U sit in a row. P is third from the left and Q is "
            "third from the right. How many people sit between P and Q?",
            "0",
            "P is in position 3 and Q is in position 4, so nobody sits between them.",
            ["1", "2", "3"],
        ),
        (
            "A, B, C and D sit in a row. A is to the left of B, C is to the right of B and D "
            "is to the left of A. Who is at the extreme left?",
            "D",
            "The only order satisfying all three conditions is D A B C.",
            ["A", "B", "C"],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Seating Arrangement", "Critical Thinking")
        )

    # 9. Analogy.
    for text, answer, explanation, distractors in (
        ("Doctor : Hospital :: Teacher : ?", "School", "A doctor works in a hospital as a teacher works in a school.", ["Book", "Student", "Lesson"]),
        ("Pen : Write :: Knife : ?", "Cut", "A pen is used to write as a knife is used to cut.", ["Sharp", "Metal", "Kitchen"]),
        ("Bird : Nest :: Bee : ?", "Hive", "A bird lives in a nest as a bee lives in a hive.", ["Flower", "Honey", "Wing"]),
        ("Book : Pages :: Ladder : ?", "Rungs", "A book is made of pages as a ladder is made of rungs.", ["Wood", "Height", "Steps"]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Analogy", "Critical Thinking")
        )

    # 10. Clocks and calendars.
    for text, answer, explanation, distractors in (
        ("What is the angle between the hour and minute hands of a clock at 3:00?", "90 degrees", "The hour hand is at 90 degrees and the minute hand at 0.", ["60 degrees", "120 degrees", "180 degrees"]),
        ("What is the angle between the hour and minute hands of a clock at 6:00?", "180 degrees", "The hands point in opposite directions.", ["90 degrees", "120 degrees", "0 degrees"]),
        ("If today is Monday, what day will it be after 61 days?", "Saturday", "61 mod 7 = 5, and Monday + 5 days is Saturday.", ["Friday", "Sunday", "Tuesday"]),
        ("What is the angle between the hour and minute hands of a clock at 4:20?", "10 degrees", "Hour hand = 4x30 + 20x0.5 = 130; minute hand = 120; difference = 10.", ["0 degrees", "20 degrees", "30 degrees"]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Clocks and Calendars", "Critical Thinking")
        )

    return _assign_difficulty(items, easy=11, medium=19, hard=10)


# ---------------------------------------------------------------------------
# Verbal ability — 40 questions
# ---------------------------------------------------------------------------
def verbal() -> list[Question]:
    items: list[Question] = []

    # 1. Synonyms.
    for word, answer, explanation, distractors in (
        ("Abundant", "Plentiful", "Abundant means existing in large quantities.", ["Scarce", "Tiny", "Hidden"]),
        ("Candid", "Frank", "Candid means honest and direct.", ["Secretive", "Rude", "Careful"]),
        ("Diligent", "Hardworking", "Diligent means showing persistent effort.", ["Lazy", "Careless", "Slow"]),
        ("Obsolete", "Outdated", "Obsolete means no longer in use.", ["Modern", "Rare", "Useful"]),
    ):
        items.append(
            _q(f"Choose the word closest in meaning to '{word}'.", [answer, *distractors], answer, explanation, "Synonyms", "Communication")
        )

    # 2. Antonyms.
    for word, answer, explanation, distractors in (
        ("Scarce", "Abundant", "Scarce means in short supply; abundant is its opposite.", ["Rare", "Limited", "Costly"]),
        ("Transparent", "Opaque", "Transparent lets light through; opaque does not.", ["Clear", "Visible", "Thin"]),
        ("Optimistic", "Pessimistic", "Optimism expects good outcomes; pessimism expects bad ones.", ["Hopeful", "Positive", "Cheerful"]),
        ("Expand", "Contract", "To expand is to grow larger; to contract is to shrink.", ["Enlarge", "Stretch", "Widen"]),
    ):
        items.append(
            _q(f"Choose the word most opposite in meaning to '{word}'.", [answer, *distractors], answer, explanation, "Antonyms", "Communication")
        )

    # 3. Prepositions.
    for text, answer, explanation, distractors in (
        ("She is good ___ mathematics.", "at", "The correct collocation is 'good at' a subject.", ["in", "on", "for"]),
        ("He apologized ___ his mistake.", "for", "We apologize for something.", ["of", "about", "on"]),
        ("The book is ___ the table.", "on", "A surface contact uses 'on'.", ["in", "at", "under"]),
        ("They have been waiting ___ noon.", "since", "'Since' marks a starting point in time.", ["for", "from", "at"]),
    ):
        items.append(
            _q(f"Choose the correct preposition: {text}", [answer, *distractors], answer, explanation, "Prepositions", "Communication")
        )

    # 4. Error spotting.
    for text, answer, explanation, distractors in (
        ("Each of the students have submitted the assignment.", "have -> has", "'Each' is singular, so it takes 'has'.", ["students -> student", "submitted -> submit", "the -> a"]),
        ("He do not like coffee.", "do -> does", "Third-person singular takes 'does'.", ["like -> likes", "coffee -> coffees", "not -> no"]),
        ("The news are disturbing.", "are -> is", "'News' is an uncountable singular noun.", ["disturbing -> disturbed", "The -> A", "news -> newses"]),
        ("She is senior than me.", "than -> to", "'Senior' takes 'to', not 'than'.", ["is -> are", "me -> I", "senior -> more senior"]),
    ):
        items.append(
            _q(f"Identify the correction needed: {text}", [answer, *distractors], answer, explanation, "Error Spotting", "Communication")
        )

    # 5. One-word substitution.
    for text, answer, explanation, distractors in (
        ("One who studies the stars and planets is called a ___.", "Astronomer", "Astronomy is the study; an astronomer practises it.", ["Astrologer", "Geologist", "Physicist"]),
        ("A person who speaks many languages is called a ___.", "Polyglot", "Polyglot combines Greek roots for 'many tongues'.", ["Linguist", "Translator", "Orator"]),
        ("A place where books are kept for reading is called a ___.", "Library", "A library stores and lends books.", ["Museum", "Archive", "Bookstore"]),
        ("An extreme fear of heights is called ___.", "Acrophobia", "Acro- means height and -phobia means fear.", ["Claustrophobia", "Agoraphobia", "Hydrophobia"]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "One-word Substitution", "Communication")
        )

    # 6. Idioms.
    for idiom, answer, explanation, distractors in (
        ("What does 'to let the cat out of the bag' mean?", "To reveal a secret", "The idiom describes an accidental disclosure.", ["To free an animal", "To start a fight", "To tell a lie"]),
        ("What does 'once in a blue moon' mean?", "Very rarely", "A blue moon is rare, so the idiom means seldom.", ["Every night", "Very quickly", "At noon"]),
        ("What does 'to hit the nail on the head' mean?", "To do exactly the right thing", "It praises a precise, correct action or remark.", ["To hurt someone", "To make a mistake", "To work hard"]),
        ("What does 'to burn the midnight oil' mean?", "To work late into the night", "The image is of studying or working by lamplight.", ["To waste electricity", "To sleep early", "To celebrate"]),
    ):
        items.append(
            _q(idiom, [answer, *distractors], answer, explanation, "Idioms", "Communication")
        )

    # 7. Active and passive voice.
    for text, answer, explanation, distractors in (
        ("Change to passive voice: The teacher explained the lesson.", "The lesson was explained by the teacher.", "The object becomes the subject and the verb becomes 'was explained'.", ["The lesson is explained by the teacher.", "The teacher was explained the lesson.", "The lesson explained the teacher."]),
        ("Change to passive voice: She writes a letter.", "A letter is written by her.", "Present simple passive uses 'is/are + past participle'.", ["A letter was written by her.", "A letter is wrote by her.", "She is written a letter."]),
        ("Change to passive voice: They are building a bridge.", "A bridge is being built by them.", "Present continuous passive uses 'is being + past participle'.", ["A bridge was being built by them.", "A bridge is built by them.", "A bridge has been built by them."]),
        ("Change to passive voice: He has completed the work.", "The work has been completed by him.", "Present perfect passive uses 'has been + past participle'.", ["The work is completed by him.", "The work was completed by him.", "The work has completed by him."]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Active and Passive Voice", "Communication")
        )

    # 8. Direct and indirect speech.
    for text, answer, explanation, distractors in (
        ("Change to indirect speech: He said, \"I am busy.\"", "He said that he was busy.", "The present tense shifts back to past in reported speech.", ["He said that he is busy.", "He says that he was busy.", "He said that I was busy."]),
        ("Change to indirect speech: She said, \"I will come tomorrow.\"", "She said that she would come the next day.", "'Will' becomes 'would' and 'tomorrow' becomes 'the next day'.", ["She said that she will come tomorrow.", "She said that she would come tomorrow.", "She says that she would come the next day."]),
        ("Change to indirect speech: \"Where do you live?\" he asked.", "He asked where I lived.", "The question becomes a statement and the tense shifts back.", ["He asked where did I live.", "He asked where I live.", "He said where do you live."]),
        ("Change to indirect speech: \"Please help me,\" she said.", "She requested me to help her.", "A request becomes 'requested ... to' plus the infinitive.", ["She said to help me.", "She ordered me to help her.", "She asked that I help me."]),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Direct and Indirect Speech", "Communication")
        )

    # 9. Spelling.
    for sentence, answer, explanation, distractors in (
        (
            "Choose the correctly spelled word to complete the sentence: "
            "\"The sudden ___ of the error surprised everyone.\"",
            "Occurrence",
            "Occurrence has two c's, two r's and two e's.",
            ["Occurence", "Ocurrence", "Occurrance"],
        ),
        (
            "Choose the correctly spelled word to complete the sentence: "
            "\"She will ___ attend the interview.\"",
            "Definitely",
            "Definitely contains 'finite' in the middle.",
            ["Definately", "Definitly", "Defenitely"],
        ),
        (
            "Choose the correctly spelled word to complete the sentence: "
            "\"Please ___ the two piles of paper.\"",
            "Separate",
            "Separate has 'par' in the middle, like 'part'.",
            ["Seperate", "Separete", "Saperate"],
        ),
        (
            "Choose the correctly spelled word to complete the sentence: "
            "\"The hotel can ___ up to 200 guests.\"",
            "Accommodate",
            "Accommodate has double c and double m.",
            ["Accomodate", "Acommodate", "Accommadate"],
        ),
    ):
        items.append(
            _q(sentence, [answer, *distractors], answer, explanation, "Spelling", "Communication")
        )

    # 10. Sentence ordering.
    for text, answer, explanation, distractors in (
        (
            "Arrange the parts into a correct sentence: (every morning / he / to the gym / goes)",
            "He goes to the gym every morning.",
            "Subject + verb + place + time is the natural English order.",
            ["He goes every morning to the gym.", "Every morning goes he to the gym.", "To the gym he every morning goes."],
        ),
        (
            "Arrange the parts into a correct sentence: (was / the meeting / cancelled / because of rain)",
            "The meeting was cancelled because of rain.",
            "Subject + auxiliary + past participle + reason.",
            ["The meeting because of rain was cancelled.", "Cancelled the meeting was because of rain.", "Because of rain the meeting cancelled was."],
        ),
        (
            "Arrange the parts into a correct sentence: (if you study hard / you will / pass the exam / certainly)",
            "If you study hard, you will certainly pass the exam.",
            "Conditional clause first, then subject + modal + adverb + verb.",
            ["You will certainly pass the exam if you study hard.", "If you study hard, certainly you will pass the exam.", "Pass the exam you will if you study hard."],
        ),
        (
            "Arrange the parts into a correct sentence: (the book / that I borrowed / was / from the library / very useful)",
            "The book that I borrowed from the library was very useful.",
            "The relative clause modifies 'the book'; the main verb follows it.",
            ["The book was very useful that I borrowed from the library.", "From the library the book that I borrowed was very useful.", "That I borrowed the book from the library was very useful."],
        ),
    ):
        items.append(
            _q(text, [answer, *distractors], answer, explanation, "Sentence Ordering", "Communication")
        )

    return _assign_difficulty(items, easy=11, medium=19, hard=10)
