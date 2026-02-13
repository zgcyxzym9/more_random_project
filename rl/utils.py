def match_by_caps(dict: list[str], key: str):
    key = key.upper()
    matches = []
    for s in dict:
        uppercase_sequence = ''.join(c for c in s if c.isupper())
        if uppercase_sequence == key:
            matches.append(s)
    if len(matches) == 0:
        print(f"Cannot find any match for {key}!")
        return None
    if len(matches) == 1:
        print(f"Found {matches[0]}")
        return matches[0]
    for i in range(len(matches)):
        print(f"[{i+1}] {matches[i]}")
    while True:
        try:
            choice = int(input(f"Multiple matches found for {key}, please select one by entering the corresponding number: "))
            if 1 <= choice <= len(matches):
                print(f"Found {matches[choice-1]}")
                return matches[choice-1]
            else:
                print("Invalid choice, please try again.")
        except ValueError:
            print("Invalid input, please enter a number.")