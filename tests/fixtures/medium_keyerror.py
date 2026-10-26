def build_profile(raw):
    return {
        "user_name": raw["name"].strip().lower(),
        "joined": raw["joined"],
    }


def greeting(profile):
    return f"Welcome back, {profile['username']}!"


def main():
    raw = {"name": "  Grace ", "joined": "2026-01-04"}
    profile = build_profile(raw)
    print(greeting(profile))


if __name__ == "__main__":
    main()
