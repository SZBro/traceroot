def page_bounds(total, page_size):
    pages = []
    for start in range(0, total, page_size):
        end = min(start + page_size, total + 1)
        pages.append((start, end))
    return pages


def page_labels(items, start, end):
    return [items[i].upper() for i in range(start, end)]


def render(items, page_size=3):
    out = []
    for start, end in page_bounds(len(items), page_size):
        out.append(" | ".join(page_labels(items, start, end)))
    return "\n".join(out)


if __name__ == "__main__":
    print(render(["ant", "bee", "cat", "dog", "eel"]))
