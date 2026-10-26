def average(scores):
    total = 0
    for s in scores:
        total += s
    return totl / len(scores)


if __name__ == "__main__":
    print(average([90, 85, 77]))
