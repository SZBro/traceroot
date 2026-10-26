"""Books, ISBNs and a small title search index."""
import csv
import re
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = {"the", "a", "an", "of", "to", "and", "in"}


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    year: int
    copies: int

    def short(self) -> str:
        return f"{self.title} ({self.year})"


def normalize_isbn(text: str) -> str | None:
    digits = re.sub(r"[^0-9X]", "", text.upper())
    if len(digits) not in (10, 13):
        return None
    return digits


def load_books(path: Path) -> dict[str, Book]:
    books = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            isbn = normalize_isbn(row["isbn"])
            if isbn is None:
                raise ValueError(f"bad ISBN {row['isbn']!r}")
            books[isbn] = Book(
                isbn=isbn,
                title=row["title"].strip(),
                author=row["author"].strip(),
                year=int(row["year"]),
                copies=int(row["copies"]),
            )
    return books


def tokens(text: str) -> list[str]:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]
    pairs = []
    for i in range(len(words) - 1):
        pairs.append(f"{words[i]} {words[i + 1]}")
    return words + pairs


def build_index(books: dict[str, Book]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for isbn, book in books.items():
        for tok in tokens(book.title) + tokens(book.author):
            index.setdefault(tok, set()).add(isbn)
    return index


def search(index: dict[str, set[str]], books: dict[str, Book], query: str) -> list[Book]:
    hits: dict[str, int] = {}
    for tok in tokens(query):
        for isbn in index.get(tok, ()):
            hits[isbn] = hits.get(isbn, 0) + 1
    ranked = sorted(hits, key=lambda i: (-hits[i], books[i].title))
    return [books[i] for i in ranked]
