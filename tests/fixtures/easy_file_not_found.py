import json


def load_settings(path="settings/config.json"):
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    print(load_settings())
