"""The words the build joins with seat numbers, names and counts.

A page fragment holds every fixed text of the interface ("Staff version",
"No.", "Paired with", "You", "+1", "[name]" and so on).  The texts here are
the ones the build has to put together with numbers or names before they
reach a fragment: "Seats 8 & 9", "Olga and your guest", "If chosen by seat 3
(no nuts) - ...", "14 guests".  One place for all of them, so that the
wording of the menu is easy to change.

Seat numbers are always listed in ascending order.  Standard library only.
"""

from __future__ import annotations

from typing import Iterable, Sequence

SEAT = "Seat"
SEATS = "Seats"
#: The same inside a sentence.
SEAT_INLINE = "seat"
SEATS_INLINE = "seats"

#: Between the items of a list, and before its last item.
LIST_SEPARATOR = ", "
LAST_SEPARATOR = " & "
#: Before the last item of a list in running text ("8 and 9").
AND = " and "
#: Between seats and what to do for them.
DASH = " — "
#: Between the parts of a line ("vegan · gluten-free").
DOT = " · "

#: After the name of a guest who brings a companion.
YOUR_GUEST = "and your guest"
YOUR_GUESTS = "and your guests"

#: The first and the next swap lines of a set.
IF_CHOSEN_BY = "If chosen by"
BY = "By"

#: The default titles of the section with the seating widget.
YOUR_SEAT = "Your seat"
YOUR_SEATS = "Your seats"
STAFF_SEATING = "Seating and dietary notes"

#: The counters of the staff page.
GUEST = "guest"
GUESTS = "guests"
NOTE = "dietary note"
NOTES = "dietary notes"

#: A line that ends with one of these gets no full stop of its own.
_FINAL_MARKS = (".", "!", "?")


def number_list(numbers: Iterable[int], last: str = LAST_SEPARATOR) -> str:
    """`[9, 8]` -> "8 & 9"; `[10, 8, 9]` -> "8, 9 & 10"; `[8]` -> "8"."""
    texts = [str(number) for number in sorted(numbers)]
    if len(texts) < 2:
        return "".join(texts)
    return LIST_SEPARATOR.join(texts[:-1]) + last + texts[-1]


def seat_label(numbers: Sequence[int]) -> str:
    """"Seat 8", "Seats 8 & 9", "Seats 8, 9 & 10"."""
    word = SEAT if len(numbers) == 1 else SEATS
    return f"{word} {number_list(numbers)}"


def seats_inline(numbers: Sequence[int]) -> str:
    """"seat 3", "seats 10 & 14": the seats inside a sentence."""
    word = SEAT_INLINE if len(numbers) == 1 else SEATS_INLINE
    return f"{word} {number_list(numbers)}"


def mine_text(numbers: Sequence[int]) -> str:
    """The seats of a guest for the text of the table plan: "8", "8 and 9",
    "8, 9 and 10"."""
    return number_list(numbers, AND)


def who_label(name: str, companions: int) -> str:
    """"Olga", "Olga and your guest", "Olga and your guests": the name of
    the record and how many companions (`plusOne` seats) come with it.  The
    names of the companions are never shown to the guest."""
    if companions <= 0:
        return name
    return f"{name} {YOUR_GUEST if companions == 1 else YOUR_GUESTS}"


def section_title(seats: int) -> str:
    """The default title of the seating section of a guest: by the number of seats."""
    return YOUR_SEAT if seats == 1 else YOUR_SEATS


def counted(count: int, one: str, many: str) -> str:
    """"1 guest", "14 guests"."""
    return f"{count} {one if count == 1 else many}"


def guests_text(count: int) -> str:
    """The number of taken seats on the staff page: "14 guests"."""
    return counted(count, GUEST, GUESTS)


def notes_text(count: int) -> str:
    """The number of seats with a dietary note: "5 dietary notes"; empty for none."""
    return counted(count, NOTE, NOTES) if count else ""


def joined(parts: Iterable[str]) -> str:
    """The non-empty parts joined by DOT: "with the starters · 6 bottles"."""
    return DOT.join(part for part in parts if part)


def listed(parts: Iterable[str]) -> str:
    """The parts as one line: "Water, lemonade, juice"."""
    return LIST_SEPARATOR.join(parts)


def dish_swap_line(numbers: Sequence[int], text: str) -> str:
    """"Seat 3 — serve the nut-free version", "Seats 10 & 14 — ..."."""
    return f"{seat_label(numbers)}{DASH}{text}"


def set_swap_line(numbers: Sequence[int], label: str, text: str, *, first: bool) -> str:
    """"If chosen by seat 3 (no nuts) — serve it without the crust." for the
    first swap of a set, "By seats 10 & 14 (no lactose) — ..." for the next."""
    lead = IF_CHOSEN_BY if first else BY
    stop = "" if text.endswith(_FINAL_MARKS) else "."
    return f"{lead} {seats_inline(numbers)} ({label}){DASH}{text}{stop}"


def drink_reminder(numbers: Sequence[int], text: str) -> str:
    """"seat 1 — no alcohol": the end of the line of a drink."""
    return f"{seats_inline(numbers)}{DASH}{text}"


__all__ = [
    "number_list",
    "seat_label",
    "seats_inline",
    "mine_text",
    "who_label",
    "section_title",
    "counted",
    "guests_text",
    "notes_text",
    "joined",
    "listed",
    "dish_swap_line",
    "set_swap_line",
    "drink_reminder",
]
